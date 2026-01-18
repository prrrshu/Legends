"""
Legends & Luminaries
A Streamlit app that is an AI-powered knowledge hub for successful people, entrepreneurs,
young achievers, and philosophers.

Core integrations:
- Wikipedia (wikipedia-api)
- Wikiquote (wikiquote)
- Wikidata SPARQL (requests)
- Groq API (groq) for AI-generated content (use stanza/llama3-70b-8192 or mixtral)
- Favorites via st.session_state (optionally wire localStorage separately)

Author: Generated for user request. Tested for structure; ensure GROQ_API_KEY in secrets.
"""

import streamlit as st
import wikipediaapi
import wikiquote
import requests
import pandas as pd
import re
import json
import time
import random
from typing import List, Dict, Optional

# Groq python client import
try:
    from groq import Groq
except Exception:
    Groq = None  # App will still run but AI features will return friendly error

# -------------------------
# PAGE / APP CONFIG
# -------------------------
st.set_page_config(
    page_title="Legends & Luminaries",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------------
# SESSION STATE DEFAULTS
# -------------------------
if "favorites" not in st.session_state:
    st.session_state["favorites"] = []  # list to preserve order

if "selected_person" not in st.session_state:
    st.session_state["selected_person"] = None

if "roleplay_person" not in st.session_state:
    st.session_state["roleplay_person"] = None

if "user_interests" not in st.session_state:
    st.session_state["user_interests"] = []  # user-selected interest keywords

if "theme" not in st.session_state:
    st.session_state["theme"] = "light"

# -------------------------
# CLIENTS / HELPERS
# -------------------------
wiki = wikipediaapi.Wikipedia(language="en", extract_format=wikipediaapi.ExtractFormat.WIKI)

# Groq client initialize (must be available in secrets)
def get_groq_client():
    if Groq is None:
        return None
    key = None
    # Try Streamlit secrets first
    try:
        key = st.secrets["GROQ_API_KEY"]
    except Exception:
        # fallback to environment (user may set env var)
        import os
        key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    try:
        client = Groq(api_key=key)
        return client
    except Exception:
        return None

groq_client = get_groq_client()

def groq_generate(prompt: str, model: str = "llama3-70b-8192", max_tokens: int = 600, temperature: float = 0.7) -> str:
    """
    Generate text via Groq. Returns user-facing error message if Groq not configured.
    """
    if groq_client is None:
        return ("[AI unavailable] Groq client not configured. Please add GROQ_API_KEY to Streamlit secrets "
                "or check your network/installation.")
    try:
        # Current groq client API may provide chat/completions. Use a safe generic approach.
        resp = groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # The response structure varies; try to extract content safely
        content = ""
        try:
            content = resp.choices[0].message["content"]
        except Exception:
            # Fallback to common field names
            try:
                content = resp.choices[0].text
            except Exception:
                content = str(resp)
        return content
    except Exception as e:
        return f"[AI error] {e}"

# -------------------------
# CACHING / FETCHING
# -------------------------
@st.cache_data(ttl=60 * 60 * 12)  # cache for 12 hours
def fetch_wikipedia_page(person_name: str) -> Optional[wikipediaapi.WikipediaPage]:
    """Return wikipediaapi page object or None"""
    try:
        page = wiki.page(person_name)
        if page and page.exists():
            return page
        # Try capitalizing / common name variants
        alt = person_name.title()
        page = wiki.page(alt)
        if page and page.exists():
            return page
        return None
    except Exception:
        return None

@st.cache_data(ttl=60 * 60 * 12)
def fetch_wikipedia_summary(person_name: str) -> Dict[str, Optional[str]]:
    """Return summary and canonical url if available"""
    p = fetch_wikipedia_page(person_name)
    if not p:
        return {"summary": None, "url": None}
    try:
        return {"summary": p.summary, "url": p.fullurl}
    except Exception:
        return {"summary": p.summary if p else None, "url": None}

@st.cache_data(ttl=60 * 60 * 12)
def fetch_wikiquote(person_name: str, max_quotes: int = 12) -> List[str]:
    """Return list of quotes from Wikiquote. Returns [] on error."""
    try:
        quotes = wikiquote.quotes(person_name, max_quotes=max_quotes)
        if isinstance(quotes, list):
            return quotes
        return []
    except Exception:
        return []

@st.cache_data(ttl=60 * 60 * 24)
def wikidata_query(sparql: str) -> List[Dict]:
    """
    Generic Sparql helper that returns bindings (list of dicts).
    """
    endpoint = "https://query.wikidata.org/sparql"
    headers = {"Accept": "application/sparql-results+json", "User-Agent": "LegendsLuminaries/1.0 (contact)"}
    try:
        res = requests.get(endpoint, params={"query": sparql}, headers=headers, timeout=20)
        res.raise_for_status()
        data = res.json()
        bindings = data.get("results", {}).get("bindings", [])
        return bindings
    except Exception:
        return []

# -------------------------
# FIELD -> occupation keywords mapping (for flexible SPARQL)
# -------------------------
FIELD_KEYWORDS = {
    "Technology": ["engineer", "computer", "programmer", "software", "technologist", "computer scientist", "developer"],
    "Business": ["entrepreneur", "businessperson", "industrialist", "businessman", "businesswoman", "business executive"],
    "Science": ["scientist", "physicist", "chemist", "biologist", "researcher", "mathematician"],
    "Philosophy": ["philosopher", "moral philosopher"],
    "Arts": ["artist", "painter", "composer", "singer", "actor", "sculptor", "writer", "poet"],
    "Sports": ["footballer", "cricketer", "tennis player", "athlete", "sportsperson", "swimmer", "basketball player"],
    "Politics": ["politician", "statesman", "prime minister", "president"],
    "Young Achievers": ["prodigy", "student", "young", "youngest", "teenager"],
}

def build_sparql_people_by_field(field: str, limit: int = 30) -> str:
    """
    SPARQL query that finds people with occupations whose labels contain any of the keywords for the field.
    It returns label, description and image (if available).
    """
    keywords = FIELD_KEYWORDS.get(field, [field.lower()])
    # Build a FILTER that matches occupations by label text
    filters = []
    for kw in keywords:
        kw_escaped = kw.replace('"', '\\"').lower()
        filters.append(f'CONTAINS(LCASE(STR(?occLabel)), "{kw_escaped}")')
    filter_clause = " || ".join(filters)

    sparql = f"""
    SELECT DISTINCT ?person ?personLabel ?description ?image WHERE {{
      ?person wdt:P31 wd:Q5;  # is a human
              wdt:P106 ?occ. # occupation
      ?occ rdfs:label ?occLabel FILTER(LANG(?occLabel) = "en").
      FILTER({filter_clause})
      OPTIONAL {{ ?person wdt:P18 ?image. }}
      OPTIONAL {{ ?person schema:description ?description FILTER (LANG(?description) = "en") . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT {limit}
    """
    return sparql

# -------------------------
# PRESENTATION / SMALL UTILITIES
# -------------------------
def render_person_card(name: str, description: str = "", image_url: Optional[str] = None, key_suffix: str = ""):
    """Renders a simple card for a person with actions"""
    cols = st.columns([1, 3])
    with cols[0]:
        if image_url:
            st.image(image_url, width=150)
        else:
            st.image("https://via.placeholder.com/150x200?text=No+Image", width=150)
    with cols[1]:
        st.markdown(f"### {name}")
        if description:
            st.write(description[:280] + ("…" if len(description) > 280 else ""))
        row_cols = st.columns([1, 1, 1])
        if row_cols[0].button("Open", key=f"open_{name}_{key_suffix}"):
            st.session_state["selected_person"] = name
            # scroll to details - by switching page
            st.experimental_rerun()
        if row_cols[1].button("Add Favorite", key=f"fav_{name}_{key_suffix}"):
            add_favorite(name)
            st.success(f"Added {name} to favorites.")
        if row_cols[2].button("Quotes", key=f"quotes_{name}_{key_suffix}"):
            quotes = fetch_wikiquote(name, max_quotes=5)
            if quotes:
                st.write("\n".join(f"- {q}" for q in quotes))
            else:
                st.info("No quotes found.")

def add_favorite(name: str):
    """Add to session favorites preserving uniqueness and order."""
    if name not in st.session_state["favorites"]:
        st.session_state["favorites"].append(name)

def remove_favorite(name: str):
    if name in st.session_state["favorites"]:
        st.session_state["favorites"].remove(name)

def set_theme_css(theme):
    """Optional lightweight CSS for dark/light theme (keeps minimal)."""
    if theme == "dark":
        css = """
        <style>
        .reportview-container { background: #0e1117; color: #e6eef3; }
        .stButton>button { background-color:#1f6feb; color: white; }
        .css-1d391kg p, .css-1d391kg span { color: #e6eef3; }
        </style>
        """
    else:
        css = "<style>/* default theme */</style>"
    st.markdown(css, unsafe_allow_html=True)

# -------------------------
# PAGES
# -------------------------
def page_home():
    st.title("Legends & Luminaries")
    st.write("AI-powered knowledge hub for successful people, entrepreneurs, brilliant young achievers, and philosophers.")
    st.write("---")

    # Theme toggle
    theme_col1, theme_col2 = st.columns([3, 1])
    with theme_col2:
        new_theme = st.selectbox("Theme", ["light", "dark"], index=0 if st.session_state["theme"] == "light" else 1)
        if new_theme != st.session_state["theme"]:
            st.session_state["theme"] = new_theme
            set_theme_css(new_theme)

    # Daily random quote from a rotating set
    st.header("Daily Inspiration")
    DAILY_NAMES = [
        "Nelson Mandela", "Marie Curie", "Mahatma Gandhi", "Albert Einstein",
        "Ada Lovelace", "Steve Jobs", "Malala Yousafzai", "Simone de Beauvoir",
        "Sundar Pichai", "Ada Yonath", "Tim Berners-Lee", "Angela Merkel"
    ]
    chosen = random.choice(DAILY_NAMES)
    quotes = fetch_wikiquote(chosen, max_quotes=6)
    if quotes:
        st.info(f"**{chosen}** — “{random.choice(quotes)}”")
    else:
        st.info(f"**{chosen}** — Inspiration for your day.")

    st.write("---")
    st.header("Featured / Emerging People")
    # Hardcoded trending names (10-15)
    featured = [
        "Sam Altman", "Elon Musk", "Mira Murati", "R Praggnanandhaa",
        "Gitanjali Rao", "Isha Ambani", "Tanmay Bakshi", "Greta Thunberg",
        "Emma Raducanu", "Sundar Pichai", "Satya Nadella", "Simone Biles",
        "Amanda Gorman", "Rihanna", "Kailash Satyarthi"
    ]
    cols = st.columns(3)
    for idx, person in enumerate(featured):
        with cols[idx % 3]:
            summary = fetch_wikipedia_summary(person)["summary"]
            img_url = None
            page = fetch_wikipedia_page(person)
            # try to find image from Wikidata via SPARQL
            if page:
                # try to grab an image from infobox via page.images (may be heavy); prefer Wikidata query below
                pass
            st.markdown(f"**{person}**")
            if summary:
                st.write(summary[:180] + ("…" if len(summary) > 180 else ""))
            else:
                st.write("No summary available.")
            if st.button("Open profile", key=f"openfeat_{person}"):
                st.session_state["selected_person"] = person
                st.experimental_rerun()

def page_explore_by_field():
    st.title("Explore by Field")
    st.write("Choose a broad field; we search Wikidata for notable people whose occupations match field keywords.")
    field = st.selectbox("Field", list(FIELD_KEYWORDS.keys()))
    limit = st.slider("Max results", 6, 60, 18, step=6)

    if field:
        with st.spinner(f"Querying Wikidata for {field}..."):
            sparql = build_sparql_people_by_field(field, limit=limit)
            bindings = wikidata_query(sparql)
            if not bindings:
                st.error("No results from Wikidata or the query failed. Try a different field or increase the limit.")
                return
            # Render cards
            for i, b in enumerate(bindings):
                name = b.get("personLabel", {}).get("value", "Unknown")
                desc = b.get("description", {}).get("value", "")
                image = b.get("image", {}).get("value", None)
                render_person_card(name, desc, image, key_suffix=f"{field}_{i}")

def page_search():
    st.title("Search")
    q = st.text_input("Search for a person (name)", placeholder="e.g., Marie Curie, Elon Musk")
    if st.button("Search") or (q and st.session_state.get("search_auto", False)):
        if not q:
            st.warning("Please enter a name.")
            return
        with st.spinner("Looking up Wikipedia..."):
            p = fetch_wikipedia_page(q)
            if not p:
                st.error("No Wikipedia page found for that name.")
                return
            # Show compact card
            img_url = None
            # Attempt to find an image via page.images (take first meaningful)
            try:
                imgs = list(p.images.keys())
                if imgs:
                    # p.images is a dict with keys being filenames in some cases; skip thumb
                    img_url = imgs[0]
            except Exception:
                img_url = None
            st.header(p.title)
            cols = st.columns([1, 3])
            with cols[0]:
                if img_url:
                    st.image(img_url, width=220)
                else:
                    st.image("https://via.placeholder.com/220x280?text=No+Image", width=220)
            with cols[1]:
                st.write(p.summary)
                if st.button("Open full profile"):
                    st.session_state["selected_person"] = p.title
                    st.experimental_rerun()

def extract_timeline_from_text(text: str, max_events: int = 8) -> List[Dict]:
    """
    Rough timeline extraction: find sentences that contain 4-digit years and sort by earliest year.
    This is heuristic and meant to give quick 'key events'.
    """
    if not text:
        return []
    # Split into sentences
    sentences = re.split(r'(?<=[\.\?\!])\s+', text)
    events = []
    for s in sentences:
        years = re.findall(r'\b(1[89]\d{2}|20\d{2})\b', s)
        if years:
            for y in years:
                try:
                    yint = int(y)
                    events.append({"year": yint, "text": s.strip()})
                except Exception:
                    continue
    # dedupe by text and sort
    seen = set()
    unique_events = []
    for e in sorted(events, key=lambda x: x["year"]):
        if e["text"] not in seen:
            seen.add(e["text"])
            unique_events.append(e)
        if len(unique_events) >= max_events:
            break
    return unique_events

def page_person_detail():
    name = st.session_state.get("selected_person")
    if not name:
        st.warning("No person selected. Use Search or Explore to select a person.")
        return
    st.title(name)
    page = fetch_wikipedia_page(name)
    if not page:
        st.error("Could not fetch Wikipedia page for this person.")
        return

    # Basic top-row: image + summary
    cols = st.columns([1, 3])
    # Try to fetch a good image via Wikidata SPARQL for this person
    image_url = None
    try:
        # Query Wikidata for image
        sparql = f"""
        SELECT ?image WHERE {{
          ?person rdfs:label "{name}"@en.
          ?person wdt:P18 ?image.
        }}
        LIMIT 1
        """
        out = wikidata_query(sparql)
        if out and out[0].get("image"):
            image_url = out[0]["image"]["value"]
    except Exception:
        image_url = None

    with cols[0]:
        if image_url:
            st.image(image_url, width=260)
        else:
            # fallback to page.images (may be heavy)
            try:
                img_keys = list(page.images.keys())
                if img_keys:
                    st.image(img_keys[0], width=260)
                else:
                    st.image("https://via.placeholder.com/260x340?text=No+Image", width=260)
            except Exception:
                st.image("https://via.placeholder.com/260x340?text=No+Image", width=260)

    with cols[1]:
        st.subheader("Snapshot")
        st.write(page.summary or "No summary available.")
        action_cols = st.columns([1, 1, 1])
        if name not in st.session_state["favorites"]:
            if action_cols[0].button("Add to Favorites"):
                add_favorite(name)
                st.success(f"Added {name} to favorites.")
        else:
            if action_cols[0].button("Remove Favorite"):
                remove_favorite(name)
                st.info(f"Removed {name} from favorites.")
        if action_cols[1].button("Open full Wikipedia"):
            st.write(f"[Open on Wikipedia]({page.fullurl})")
        if action_cols[2].button("Role-play chat"):
            st.session_state["roleplay_person"] = name
            st.experimental_rerun()

    # Expanders: Full biography / timeline / quotes / books / influence / AI lessons
    st.markdown("---")
    with st.expander("Full Biography (Wikipedia)"):
        st.write(page.text[:30000])  # cap for safety

    # Timeline
    st.markdown("### Timeline — extracted (heuristic)")
    timeline = extract_timeline_from_text(page.text, max_events=10)
    if timeline:
        # Show in a tidy table
        df = pd.DataFrame(timeline)
        df = df.sort_values("year")
        st.table(df.rename(columns={"year": "Year", "text": "Event"}).reset_index(drop=True))
    else:
        st.write("No clear date-based events could be extracted. Try a different profile.")

    # Quotes from Wikiquote
    st.markdown("### Quotes & Speeches (Wikiquote)")
    quotes = fetch_wikiquote(name, max_quotes=12)
    if quotes:
        for q in quotes[:8]:
            st.write(f"> {q}")
    else:
        st.write("No quotes found on Wikiquote.")

    # Books / Works / Interviews: Try to extract common 'Works' sections from Wikipedia
    st.markdown("### Notable Works & Links")
    works = []
    try:
        # find sections that look like 'Works', 'Bibliography', 'Books', 'Selected works'
        for s in page.sections:
            if re.search(r'works|books|bibliography|publications|selected works', s.title, flags=re.I
