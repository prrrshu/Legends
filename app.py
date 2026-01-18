import streamlit as st
import wikipediaapi
import requests
import pandas as pd
import re
import json
from datetime import datetime
from groq import Groq

# -----------------------------------------------------------------------------
# PAGE CONFIG / THEME
# -----------------------------------------------------------------------------

st.set_page_config(
    page_title="Legends & Luminaries",
    page_icon="⭐",
    layout="wide"
)

# -----------------------------------------------------------------------------
# INIT
# -----------------------------------------------------------------------------

if "favorites" not in st.session_state:
    st.session_state["favorites"] = []

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

wiki = wikipediaapi.Wikipedia(
    language="en",
    user_agent="LegendsLuminariesApp/1.0 (https://example.com)"
)

# Groq client
try:
    groq_api_key = st.secrets["GROQ_API_KEY"]
    client = Groq(api_key=groq_api_key)
except Exception:
    client = None

# -----------------------------------------------------------------------------
# UTILITY FUNCTIONS
# -----------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def fetch_wikipedia_page(person_name: str):
    try:
        page = wiki.page(person_name)
        if page.exists():
            return page
        return None
    except:
        return None


@st.cache_data(show_spinner=False)
def fetch_wikiquote_quotes(name: str):
    try:
        url = f"https://en.wikiquote.org/w/api.php?action=query&format=json&prop=extracts&titles={name}&redirects=1"
        data = requests.get(url, timeout=10).json()
        pages = data.get("query", {}).get("pages", {})
        extract = next(iter(pages.values())).get("extract", "")
        quotes = re.findall(r"<li>(.*?)</li>", extract)
        clean = [re.sub("<.*?>", "", q).strip() for q in quotes]
        return clean[:10]
    except:
        return []


@st.cache_data(show_spinner=False)
def fetch_sparql_people(occupation_qid):
    query = f"""
    SELECT ?person ?personLabel ?photo ?description WHERE {{
      ?person wdt:P31 wd:Q5.
      ?person wdt:P106 wd:{occupation_qid}.
      OPTIONAL {{ ?person wdt:P18 ?photo. }}
      OPTIONAL {{ ?person schema:description ?description FILTER (lang(?description)='en'). }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language 'en'. }}
    }}
    LIMIT 50
    """
    url = "https://query.wikidata.org/sparql"
    headers = {"Accept": "application/json"}
    response = requests.get(url, params={"query": query}, headers=headers)
    json_data = response.json()
    results = json_data["results"]["bindings"]
    people = []

    for r in results:
        people.append({
            "name": r["personLabel"]["value"],
            "description": r.get("description", {}).get("value", ""),
            "photo": r.get("photo", {}).get("value", ""),
            "id": r["person"]["value"].split("/")[-1]
        })

    return people


def groq_ai(prompt: str):
    if client is None:
        return "Groq API key not configured."
    try:
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except:
        return "AI processing error."


# -----------------------------------------------------------------------------
# UI COMPONENTS
# -----------------------------------------------------------------------------

def add_to_favorites(name):
    if name not in st.session_state["favorites"]:
        st.session_state["favorites"].append(name)
        st.success(f"Added to favorites: {name}")


def show_person_detail(person_name):
    page = fetch_wikipedia_page(person_name)
    if not page:
        st.error("Person not found.")
        return

    col1, col2 = st.columns([1, 2])

    with col1:
        # Try Wikidata image
        img_url = None
        try:
            url = f"https://www.wikidata.org/wiki/Special:EntityData/{person_name}.json"
            data = requests.get(url).json()
            entity = data["entities"][person_name]
            img_filename = entity["claims"]["P18"][0]["mainsnak"]["datavalue"]["value"].replace(" ", "_")
            img_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{img_filename}"
        except:
            pass

        if img_url:
            st.image(img_url, width=300)

        st.button("Add to Favorites", on_click=add_to_favorites, args=[person_name])

    with col2:
        st.header(person_name)
        st.write(page.summary[:800] + "...")
        with st.expander("Full Biography"):
            st.write(page.text)

    st.subheader("Timeline / Key Events")
    for section in page.sections:
        if re.search(r"life|career|timeline|early life|history", section.title, flags=re.I):
            st.markdown(f"**{section.title}**")
            st.write(section.text)

    st.subheader("Quotes")
    quotes = fetch_wikiquote_quotes(person_name)
    if quotes:
        for q in quotes:
            st.markdown(f"- {q}")
    else:
        st.info("No quotes found.")

    # ---------------- WORKS SECTION (FULL, FIXED) -------------------

    st.markdown("### Notable Works & Links")

    works = []
    try:
        for s in page.sections:
            if re.search(
                r'(works|books|bibliography|publications|selected works|written works)',
                s.title,
                flags=re.I
            ):
                content = s.text.strip() if s.text else ""
                works.append({"section": s.title, "content": content})

                for sub in s.sections:
                    sub_content = sub.text.strip() if sub.text else ""
                    works.append({"section": f"{s.title} → {sub.title}", "content": sub_content})

        if works:
            for w in works:
                st.markdown(f"**{w['section']}**")
                text = w["content"]
                if len(text) > 600:
                    with st.expander("Show more"):
                        st.write(text)
                else:
                    st.write(text)
                st.write("---")
        else:
            st.info("No notable works found.")
    except Exception as e:
        st.warning(f"Could not extract notable works: {e}")

    # Influence Network via Wikidata
    st.subheader("Influence Network")

    try:
        influence_query = f"""
        SELECT ?influencerLabel WHERE {{
          wd:{person_name} wdt:P737 ?influencer.
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        """
        url = "https://query.wikidata.org/sparql"
        data = requests.get(url, params={"query": influence_query, "format": "json"}).json()
        results = data["results"]["bindings"]
        if results:
            for r in results:
                st.markdown(f"- Influenced by: **{r['influencerLabel']['value']}**")
        else:
            st.info("No influence data found.")
    except:
        st.info("Influence data unavailable.")

    # Role-play
    st.subheader("Role-play Chat")
    user_input = st.text_input("Talk with AI impersonating this person:")
    if user_input:
        reply = groq_ai(f"Role-play as {person_name}. Respond as they would. User says: {user_input}")
        st.write(reply)


# -----------------------------------------------------------------------------
# PAGE ROUTES
# -----------------------------------------------------------------------------

def page_home():
    st.title("Legends & Luminaries")
    st.write("Your AI-powered knowledge hub for achievers, thinkers, creators, and visionaries.")

    st.subheader("Daily Inspiration Quote")
    quote = groq_ai("Provide an inspiring quote for the day.")
    st.info(quote)

    st.subheader("Featured / Trending Personalities")
    trending = [
        "Elon Musk", "Sundar Pichai", "Tim Cook", "Virat Kohli", "Greta Thunberg",
        "Malala Yousafzai", "Lionel Messi", "Satya Nadella", "Narendra Modi",
        "Marie Curie", "Kylian Mbappé", "Sam Altman"
    ]

    cols = st.columns(3)
    for i, name in enumerate(trending):
        with cols[i % 3]:
            st.markdown(f"**{name}**")
            if st.button(f"View {name}", key=f"home_{i}"):
                st.session_state["page"] = "Person"
                st.session_state["current_person"] = name


def page_explore():
    st.title("Explore by Field")

    fields = {
        "Technology": "Q11661",
        "Business": "Q43845",
        "Science": "Q901",
        "Philosophy": "Q4964182",
        "Arts": "Q483501",
        "Sports": "Q2066131",
        "Politics": "Q82955",
        "Young Achievers": "Q340169"
    }

    field = st.selectbox("Choose a Field", list(fields.keys()))

    if field:
        people = fetch_sparql_people(fields[field])
        st.subheader(f"People in {field}")

        cols = st.columns(3)
        for i, p in enumerate(people):
            with cols[i % 3]:
                st.markdown(f"### {p['name']}")
                if p["photo"]:
                    st.image(p["photo"], width=200)
                st.caption(p["description"])
                if st.button(f"View {p['name']}", key=f"explore_{i}"):
                    st.session_state["page"] = "Person"
                    st.session_state["current_person"] = p["name"]


def page_search():
    st.title("Search")

    name = st.text_input("Enter a person's name:")

    if name:
        if st.button("Search"):
            page = fetch_wikipedia_page(name)
            if page:
                st.session_state["page"] = "Person"
                st.session_state["current_person"] = name
            else:
                st.error("Person not found.")


def page_person():
    if "current_person" not in st.session_state:
        st.info("Search or select a person first.")
        return
    show_person_detail(st.session_state["current_person"])


def page_philosophers():
    st.title("Philosophers")
    names = ["Aristotle", "Socrates", "Plato", "Confucius", "Nietzsche", "Kant"]
    for name in names:
        if st.button(f"View {name}", key=f"philo_{name}"):
            st.session_state["page"] = "Person"
            st.session_state["current_person"] = name


def page_ai_agent():
    st.title("AI Agent")
    query = st.text_area("Ask anything...")
    if st.button("Ask"):
        answer = groq_ai(query)
        st.write(answer)


def page_compare():
    st.title("Compare Two People")

    col1, col2 = st.columns(2)
    name1 = col1.text_input("Person 1")
    name2 = col2.text_input("Person 2")

    if st.button("Compare"):
        summary1 = fetch_wikipedia_page(name1).summary[:700] if fetch_wikipedia_page(name1) else "Not found."
        summary2 = fetch_wikipedia_page(name2).summary[:700] if fetch_wikipedia_page(name2) else "Not found."

        prompt = (
            f"Compare these two people:\n\n"
            f"1. {name1}: {summary1}\n"
            f"2. {name2}: {summary2}\n\n"
            f"Generate a table comparing background, achievements, failures, mindset, habits, and long-term impact."
        )

        result = groq_ai(prompt)
        st.markdown(result)


def page_emerging():
    st.title("Emerging Stars")

    young = [
        "Mikayla Nogueira",
        "Emma Chamberlain",
        "Khaby Lame",
        "Ishan Kishan",
        "Gitanjali Rao",
        "Timnit Gebru",
        "Tanmay Bakshi"
    ]

    for name in young:
        st.markdown(f"### {name}")
        if st.button(f"View {name}", key=f"emerging_{name}"):
            st.session_state["page"] = "Person"
            st.session_state["current_person"] = name


# -----------------------------------------------------------------------------
# SIDEBAR NAVIGATION
# -----------------------------------------------------------------------------

st.sidebar.title("Navigation")

pages = {
    "Home": page_home,
    "Explore by Field": page_explore,
    "Search": page_search,
    "Person Detail": page_person,
    "Philosophers": page_philosophers,
    "AI Agent": page_ai_agent,
    "Compare": page_compare,
    "Emerging Stars": page_emerging
}

choice = st.sidebar.radio("Go to:", list(pages.keys()))

st.session_state["page"] = choice

pages[choice]()
