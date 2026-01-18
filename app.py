import streamlit as st
import wikipediaapi
import wikiquote
import requests
import pandas as pd
from groq import Groq
import re
import json
from datetime import datetime

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

st.set_page_config(
    page_title="Legends & Luminaries",
    page_icon="✨",
    layout="wide"
)

# ---------------------------------------------------------
# INITIALIZATION
# ---------------------------------------------------------

if "favorites" not in st.session_state:
    st.session_state["favorites"] = []

if "interest_fields" not in st.session_state:
    st.session_state["interest_fields"] = []

# ---------------------------------------------------------
# API CLIENTS
# ---------------------------------------------------------

wiki = wikipediaapi.Wikipedia(
    language="en",
    extract_format=wikipediaapi.ExtractFormat.WIKI,
    user_agent="LegendsLuminaries/1.0 (contact: admin@example.com)"
)

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# ---------------------------------------------------------
# CACHING + ERROR-SAFE FUNCTIONS
# ---------------------------------------------------------

@st.cache_data(ttl=3600)
def fetch_wikipedia_summary(name):
    try:
        page = wiki.page(name)
        if page.exists():
            return page.summary, page.fullurl
    except Exception:
        pass
    return None, None


@st.cache_data(ttl=3600)
def fetch_wikiquote_quotes(name):
    try:
        return wikiquote.quotes(name, max_quotes=20)
    except Exception:
        return []


@st.cache_data(ttl=3600)
def fetch_image_url(name: str):
    """Robust image fetcher with safe JSON parsing and fallback."""
    try:
        url = (
            "https://en.wikipedia.org/w/api.php"
            "?action=query&prop=pageimages&format=json&piprop=thumbnail&pithumbsize=600"
            f"&titles={requests.utils.quote(name)}"
        )

        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None

        try:
            data = resp.json()
        except ValueError:
            return None

        pages = data.get("query", {}).get("pages", {})

        for _, p in pages.items():
            if "thumbnail" in p and "source" in p["thumbnail"]:
                return p["thumbnail"]["source"]

    except Exception:
        return None

    return None


@st.cache_data(ttl=3600)
def sparql_query(field):
    """Robust Wikidata query with safe fallback."""
    query = f"""
    SELECT ?person ?personLabel ?description ?image WHERE {{
      ?person wdt:P31 wd:Q5 .
      ?person wdt:P106 ?occupation .
      ?occupation rdfs:label ?occLabel .
      FILTER(CONTAINS(LCASE(?occLabel), "{field.lower()}"))
      OPTIONAL {{ ?person wdt:P18 ?image. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 25
    """

    url = "https://query.wikidata.org/sparql"
    headers = {"Accept": "application/sparql-results+json"}

    try:
        response = requests.get(url, params={"query": query}, headers=headers, timeout=10)
        if response.status_code != 200:
            return []
        return response.json().get("results", {}).get("bindings", [])
    except Exception:
        return []

# ---------------------------------------------------------
# GROQ AI FUNCTIONS
# ---------------------------------------------------------

def ai_generate_lessons(summary):
    if not summary:
        return "No summary available."

    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": "Extract key life lessons in short bullet points."},
                {"role": "user", "content": summary}
            ],
            max_tokens=350,
            temperature=0.4
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Processing Error: {e}"


def ai_chat_as(name, question, context):
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": f"Act as {name}. Stay in character."},
                {"role": "user", "content": f"Background: {context}"},
                {"role": "user", "content": question},
            ],
            max_tokens=600,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Processing Error: {e}"


def ai_compare(a, b, contextA, contextB):
    prompt = f"""
Compare these two personalities in a structured table.

Person A: {a}
Bio: {contextA}

Person B: {b}
Bio: {contextB}

Sections:
- Background
- Achievements
- Mindset
- Habits
- Failures
- Impact
- Legacy
"""

    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=900,
            temperature=0.4
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Processing Error: {e}"


def ai_general_chat(question, context):
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": "You are an AI expert on influential people and philosophy."},
                {"role": "user", "content": f"Context: {context}"},
                {"role": "user", "content": question}
            ],
            max_tokens=600,
            temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Processing Error: {e}"

# ---------------------------------------------------------
# UI SECTIONS
# ---------------------------------------------------------

def home_page():
    st.title("✨ Legends & Luminaries")
    st.subheader("Your AI-powered knowledge hub for achievers & thinkers.")

    # Daily Quote
    names = ["Albert Einstein", "Steve Jobs", "Marcus Aurelius", "Maya Angelou", "Napoleon Hill"]
    selected = names[datetime.now().day % len(names)]
    quotes = fetch_wikiquote_quotes(selected)

    if quotes:
        st.info(f"Daily Inspiration: {quotes[0]}")
    else:
        st.info("No quote available today.")

    st.markdown("### Featured Achievers")
    featured = [
        "Sundar Pichai", "Elon Musk", "Marie Curie", "Bill Gates", "APJ Abdul Kalam",
        "Greta Thunberg", "Malala Yousafzai", "Linus Torvalds"
    ]

    cols = st.columns(4)
    for i, name in enumerate(featured):
        with cols[i % 4]:
            img = fetch_image_url(name)
            if img:
                st.image(img, width=150)
            st.write(name)
            if st.button(f"View {name}", key=f"feat_{i}"):
                st.session_state["selected_person"] = name
                st.experimental_rerun()


def explore_by_field():
    st.title("Explore by Field")
    fields = ["Technology", "Business", "Science", "Philosophy", "Arts", "Sports", "Politics", "Young Achievers"]
    field = st.selectbox("Choose a field:", fields)

    results = sparql_query(field)
    st.write(f"Showing results for **{field}**")

    if not results:
        st.warning("No data available.")
        return

    cols = st.columns(3)
    for idx, item in enumerate(results):
        with cols[idx % 3]:
            name = item["personLabel"]["value"]
            desc = item.get("description", {}).get("value", "")
            img = item.get("image", {}).get("value")

            if img:
                st.image(img, width=180)

            st.markdown(f"**{name}**")
            st.write(desc)

            if st.button(f"View {name}", key=f"fld_{idx}"):
                st.session_state["selected_person"] = name
                st.experimental_rerun()


def search_page():
    st.title("Search Achievers")
    query = st.text_input("Enter name:")

    if query:
        summary, url = fetch_wikipedia_summary(query)
        if summary:
            img = fetch_image_url(query)
            if img:
                st.image(img, width=200)
            st.write(summary)

            if st.button("View Details"):
                st.session_state["selected_person"] = query
                st.experimental_rerun()
        else:
            st.error("No person found.")


def person_detail_page():
    name = st.session_state.get("selected_person")
    if not name:
        st.warning("No person selected.")
        return

    st.title(name)

    img = fetch_image_url(name)
    if img:
        st.image(img, width=240)

    summary, url = fetch_wikipedia_summary(name)
    st.write(summary)

    # Full biography
    with st.expander("Full Biography"):
        page = wiki.page(name)
        st.write(page.text)

    # Quotes
    quotes = fetch_wikiquote_quotes(name)
    if quotes:
        st.markdown("### Quotes")
        for q in quotes[:8]:
            st.write(f"- {q}")

    # AI Lessons
    st.markdown("### Key Lessons")
    st.write(ai_generate_lessons(summary))

    # Roleplay Chat
    st.markdown("### Role-play Chat")
    question = st.text_input("Ask something to this person:")
    if question:
        st.write(ai_chat_as(name, question, summary))


def philosophers_page():
    st.title("Philosophers")
    names = ["Plato", "Aristotle", "Confucius", "Socrates", "Nietzsche"]

    for n in names:
        if st.button(f"View {n}"):
            st.session_state["selected_person"] = n
            st.experimental_rerun()


def ai_agent_page():
    st.title("AI Knowledge Agent")

    question = st.text_area("Ask anything:")
    if question:
        st.write(ai_general_chat(question, "General knowledge context"))


def compare_page():
    st.title("Compare Two People")

    a = st.text_input("Person A")
    b = st.text_input("Person B")

    if a and b:
        A, _ = fetch_wikipedia_summary(a)
        B, _ = fetch_wikipedia_summary(b)

        if not A or not B:
            st.error("One or both people not found.")
            return

        st.write(ai_compare(a, b, A, B))


def emerging_stars_page():
    st.title("Emerging Stars")

    stars = [
        "R Praggnanandhaa", "Gitanjali Rao", "Emma Raducanu",
        "Khaby Lame", "Ishan Kishan", "Ben Francis"
    ]

    for name in stars:
        if st.button(f"View {name}"):
            st.session_state["selected_person"] = name
            st.experimental_rerun()

# ---------------------------------------------------------
# SIDEBAR NAVIGATION
# ---------------------------------------------------------

menu = st.sidebar.selectbox(
    "Navigate",
    ["Home", "Explore by Field", "Search", "Person Details", "Philosophers", "AI Agent", "Compare Tool", "Emerging Stars"]
)

if menu == "Home":
    home_page()
elif menu == "Explore by Field":
    explore_by_field()
elif menu == "Search":
    search_page()
elif menu == "Person Details":
    person_detail_page()
elif menu == "Philosophers":
    philosophers_page()
elif menu == "AI Agent":
    ai_agent_page()
elif menu == "Compare Tool":
    compare_page()
elif menu == "Emerging Stars":
    emerging_stars_page()
