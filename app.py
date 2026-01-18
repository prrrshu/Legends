"""
Legends & Luminaries — Streamlit App
AI-powered knowledge hub for influential people, entrepreneurs, achievers, and philosophers.
Uses ONLY free resources:
- Wikipedia API (wikipedia-api)
- Wikiquote API
- Wikidata SPARQL
- Groq API (free tier) with llama3-70b-8192 or mixtral
"""

import streamlit as st
import wikipediaapi
import wikiquote
import requests
import pandas as pd
import re
import json
import random
import time
from typing import List, Dict, Optional

# -------------------------
# PAGE CONFIG
# -------------------------
st.set_page_config(
    page_title="Legends & Luminaries",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------------
# SESSION DEFAULTS
# -------------------------
defaults = {
    "favorites": [],
    "selected_person": None,
    "roleplay_person": None,
    "user_interests": [],
    "theme": "light",
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# -------------------------
# Wikipedia client (with user agent FIX)
# -------------------------
wiki = wikipediaapi.Wikipedia(
    language="en",
    extract_format=wikipediaapi.ExtractFormat.WIKI,
    user_agent="LegendsLuminaries/1.0 (contact: support@example.com)"
)

# -------------------------
# GROQ CLIENT
# -------------------------
try:
    from groq import Groq
except ImportError:
    Groq = None

def get_groq_client():
    if Groq is None:
        return None

    key = None
    try:
        key = st.secrets["GROQ_API_KEY"]
    except:
        import os
        key = os.getenv("GROQ_API_KEY")

    if not key:
        return None

    try:
        return Groq(api_key=key)
    except:
        return None

groq_client = get_groq_client()

# -------------------------
# GROQ TEXT GENERATION (Stable)
# -------------------------
def groq_generate(prompt: str, model="llama3-70b-8192", max_tokens=600, temperature=0.6) -> str:
    if not groq_client:
        return "[AI unavailable] Missing or invalid GROQ_API_KEY."

    if not prompt or prompt.strip() == "":
        return "[AI] No valid input provided."

    try:
        response = groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens
        )

        # Try message["content"]
        try:
            return response.choices[0].message["content"]
        except:
            # Fallback to .text
            return response.choices[0].text

    except Exception as e:
        return f"[AI Error] {str(e)}"

# -------------------------
# CACHED FETCH FUNCTIONS
# -------------------------
@st.cache_data(ttl=3600)
def fetch_wikipedia_page(name: str):
    try:
        page = wiki.page(name)
        if page.exists():
            return page
        alt = name.title()
        page = wiki.page(alt)
        return page if page.exists() else None
    except:
        return None

@st.cache_data(ttl=3600)
def fetch_wikiquote(name, max_quotes=10):
    try:
        quotes = wikiquote.quotes(name, max_quotes=max_quotes)
        return quotes if isinstance(quotes, list) else []
    except:
        return []

@st.cache_data(ttl=3600)
def wikidata_query(query: str):
    endpoint = "https://query.wikidata.org/sparql"
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "LegendsLuminaries/1.0"
    }
    try:
        resp = requests.get(endpoint, params={"query": query}, headers=headers, timeout=25)
        resp.raise_for_status()
        return resp.json().get("results", {}).get("bindings", [])
    except:
        return []

# -------------------------
# FIELD MAPPING
# -------------------------
FIELD_KEYWORDS = {
    "Technology": ["engineer", "developer", "programmer", "computer scientist"],
    "Business": ["entrepreneur", "businessperson", "industrialist"],
    "Science": ["scientist", "physicist", "chemist", "biologist"],
    "Philosophy": ["philosopher"],
    "Arts": ["artist", "author", "poet", "painter", "actor"],
    "Sports": ["athlete", "footballer", "cricketer", "tennis player"],
    "Politics": ["politician", "president", "prime minister"],
    "Young Achievers": ["prodigy", "student", "youngest"]
}

# -------------------------
# BUILD SPARQL QUERY
# -------------------------
def build_sparql_people_by_field(field, limit=30):
    keywords = FIELD_KEYWORDS.get(field, [field.lower()])
    filters = " || ".join([f'CONTAINS(LCASE(STR(?occLabel)), "{kw.lower()}")' for kw in keywords])

    return f"""
    SELECT DISTINCT ?person ?personLabel ?description ?image WHERE {{
      ?person wdt:P31 wd:Q5;
              wdt:P106 ?occ.
      ?occ rdfs:label ?occLabel FILTER (LANG(?occLabel)="en").
      FILTER({filters})
      OPTIONAL {{ ?person wdt:P18 ?image. }}
      OPTIONAL {{ ?person schema:description ?description FILTER(LANG(?description)="en"). }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT {limit}
    """

# -------------------------
# TIMELINE EXTRACTION
# -------------------------
def extract_timeline(text, max_events=8):
    if not text:
        return []

    sentences = re.split(r'(?<=[.!?])\s+', text)
    events = []

    for s in sentences:
        years = re.findall(r"\b(1[89]\d{2}|20\d{2})\b", s)
        if years:
            for y in years:
                events.append({"year": int(y), "event": s.strip()})

    # Deduplicate and sort
    uniq = []
    seen = set()
    for e in sorted(events, key=lambda x: x["year"]):
        if e["event"] not in seen:
            uniq.append(e)
            seen.add(e["event"])
        if len(uniq) >= max_events:
            break

    return uniq

# -------------------------
# FAVORITES
# -------------------------
def add_favorite(name):
    if name not in st.session_state["favorites"]:
        st.session_state["favorites"].append(name)

def remove_favorite(name):
    if name in st.session_state["favorites"]:
        st.session_state["favorites"].remove(name)

# -------------------------
# UI COMPONENT — Person Card
# -------------------------
def render_card(name, desc, img_url=None):
    cols = st.columns([1, 3])
    with cols[0]:
        st.image(img_url or "https://via.placeholder.com/150", width=150)

    with cols[1]:
        st.markdown(f"### {name}")
        st.write(desc[:180] + ("…" if len(desc) > 180 else ""))

        c1, c2, c3 = st.columns(3)
        if c1.button("Open", key=f"open_{name}"):
            st.session_state["selected_person"] = name
            st.experimental_rerun()

        if c2.button("Favorite", key=f"fav_{name}"):
            add_favorite(name)
            st.success("Added to favorites")

        if c3.button("Quotes", key=f"q_{name}"):
            quotes = fetch_wikiquote(name, 5)
            for q in quotes:
                st.write(f"> {q}")

# ---------------------------------------------------------
# PAGES
# ---------------------------------------------------------
def page_home():
    st.title("Legends & Luminaries")
    st.subheader("AI-powered knowledge hub for achievers and thought leaders.")
    st.write("---")

    # Theme selector
    theme = st.selectbox("Theme", ["light", "dark"], index=0 if st.session_state["theme"]=="light" else 1)
    st.session_state["theme"] = theme

    # Daily quote
    st.header("Daily Inspiration")
    sample_names = ["Albert Einstein", "Marie Curie", "Steve Jobs", "Nelson Mandela", "Confucius"]
    person = random.choice(sample_names)
    quotes = fetch_wikiquote(person, 8)
    st.info(f"{person} — “{random.choice(quotes) if quotes else 'Be the best version of yourself.'}”")

    # Featured
    st.write("---")
    st.header("Featured Personalities")

    featured = ["Elon Musk", "Sundar Pichai", "Malala Yousafzai", "Satya Nadella", "Greta Thunberg"]
    cols = st.columns(3)

    for i, person in enumerate(featured):
        with cols[i % 3]:
            p = fetch_wikipedia_page(person)
            summary = p.summary[:150] + "…" if p else ""
            render_card(person, summary, None)

# ---------------------------------------------------------
def page_explore():
    st.title("Explore by Field")
    field = st.selectbox("Select field", list(FIELD_KEYWORDS.keys()))

    sparql = build_sparql_people_by_field(field)
    results = wikidata_query(sparql)

    if not results:
        st.warning("No results found.")
        return

    for i, row in enumerate(results):
        name = row.get("personLabel", {}).get("value", "Unknown")
        desc = row.get("description", {}).get("value", "")
        img = row.get("image", {}).get("value")
        render_card(name, desc, img)

# ---------------------------------------------------------
def page_search():
    st.title("Search Profiles")
    q = st.text_input("Enter name")

    if st.button("Search"):
        if not q:
            st.warning("Please enter a name.")
            return

        page = fetch_wikipedia_page(q)
        if not page:
            st.error("Page not found.")
            return

        st.header(page.title)
        st.write(page.summary)

        if st.button("Open Full Profile"):
            st.session_state["selected_person"] = page.title
            st.experimental_rerun()

# ---------------------------------------------------------
def page_detail():
    name = st.session_state["selected_person"]

    if not name:
        st.warning("Select a person first.")
        return

    page = fetch_wikipedia_page(name)
    if not page:
        st.error("Error loading page.")
        return

    st.title(name)

    # Summary
    st.subheader("Overview")
    st.write(page.summary)

    # Timeline
    st.subheader("Timeline")
    timeline = extract_timeline(page.text)
    if timeline:
        df = pd.DataFrame(timeline)
        st.table(df)
    else:
        st.write("No timeline data.")

    # Quotes
    st.subheader("Quotes")
    quotes = fetch_wikiquote(name, 12)
    for q in quotes[:8]:
        st.write(f"> {q}")

    # AI Key Lessons
    st.subheader("AI-Generated Lessons")
    prompt = f"Summarize the top leadership and success lessons from {name} in bullet points."
    st.write(groq_generate(prompt))

# ---------------------------------------------------------
def page_ai_agent():
    st.title("AI Agent")
    query = st.text_area("Ask anything")

    if st.button("Ask AI"):
        if not query.strip():
            st.warning("Enter a query.")
            return

        result = groq_generate(query)
        st.write(result)

# ---------------------------------------------------------
def page_compare():
    st.title("Compare Two Personalities")

    name1 = st.text_input("Person A")
    name2 = st.text_input("Person B")

    if st.button("Compare"):
        if not name1 or not name2:
            st.warning("Enter both names.")
            return

        text1 = fetch_wikipedia_page(name1).summary if fetch_wikipedia_page(name1) else ""
        text2 = fetch_wikipedia_page(name2).summary if fetch_wikipedia_page(name2) else ""

        prompt = f"""
Compare these two personalities:

1. {name1}: {text1}
2. {name2}: {text2}

Provide a structured table comparing:
- Background
- Achievements
- Failures
- Mindset
- Leadership Style
- Influence
- Life Lessons
"""
        st.write(groq_generate(prompt))

# ---------------------------------------------------------
# SIDEBAR NAVIGATION
# ---------------------------------------------------------
pages = {
    "Home": page_home,
    "Explore by Field": page_explore,
    "Search": page_search,
    "Person Detail": page_detail,
    "AI Agent": page_ai_agent,
    "Compare": page_compare,
}

choice = st.sidebar.radio("Navigate", list(pages.keys()))
pages[choice]()
