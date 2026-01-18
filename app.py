import streamlit as st
import wikipediaapi
import wikiquote
import requests
import pandas as pd
from groq import Groq
import re
import json
from datetime import datetime
from streamlit_js_eval import streamlit_js_eval

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

# Wikipedia client with REQUIRED User-Agent
wiki = wikipediaapi.Wikipedia(
    language="en",
    extract_format=wikipediaapi.ExtractFormat.WIKI,
    user_agent="LegendsLuminaries/1.0 (contact: your_email@example.com)"
)

# Groq client
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# ---------------------------------------------------------
# CACHING DECORATORS
# ---------------------------------------------------------

@st.cache_data(ttl=3600)
def fetch_wikipedia_summary(name):
    page = wiki.page(name)
    if page.exists():
        return page.summary, page.fullurl
    return None, None

@st.cache_data(ttl=3600)
def fetch_wikiquote_quotes(name):
    try:
        quotes = wikiquote.quotes(name, max_quotes=20)
        return quotes
    except Exception:
        return []

@st.cache_data(ttl=3600)
def fetch_image_url(name):
    """Fetch image from Wikipedia via Wikidata"""
    search_url = f"https://en.wikipedia.org/w/api.php?action=query&titles={name}&prop=pageimages&pithumbsize=600&format=json"
    resp = requests.get(search_url).json()
    pages = resp.get("query", {}).get("pages", {})
    for page in pages.values():
        if "thumbnail" in page:
            return page["thumbnail"]["source"]
    return None

@st.cache_data(ttl=3600)
def sparql_query(field):
    """Queries Wikidata for notable people in a specific field."""
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
    response = requests.get(url, params={"query": query}, headers=headers)
    return response.json()["results"]["bindings"]

# ---------------------------------------------------------
# GROQ AI FUNCTIONS
# ---------------------------------------------------------

def ai_generate_lessons(summary):
    """Generate AI key lessons from summary"""
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b",
            messages=[
                {"role": "system", "content": "Extract key life lessons and principles concisely."},
                {"role": "user", "content": summary}
            ],
            max_tokens=400,
            temperature=0.4
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"

def ai_chat_as(name, question, context):
    """Roleplay chat as a person"""
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b",
            messages=[
                {"role": "system", "content": f"Act as {name}. Use their tone and philosophy."},
                {"role": "user", "content": f"Context: {context}"},
                {"role": "user", "content": question}
            ],
            max_tokens=600,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"

def ai_compare(a, b, contextA, contextB):
    """Compare two personalities"""
    prompt = f"""
Compare the following individuals in a structured table:

Person A: {a}
Bio: {contextA}

Person B: {b}
Bio: {contextB}

Include sections: Background, Achievements, Mindset, Habits, Failures, Impact, Legacy.
"""
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.4
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"

def ai_general_chat(question, context):
    """General AI Hub"""
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b",
            messages=[
                {"role": "system", "content": "You are an expert knowledge assistant about influential people."},
                {"role": "user", "content": f"Context: {context}"},
                {"role": "user", "content": question}
            ],
            max_tokens=600,
            temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"

# ---------------------------------------------------------
# FAVORITES MANAGEMENT
# ---------------------------------------------------------

def add_to_favorites(name):
    if name not in st.session_state["favorites"]:
        st.session_state["favorites"].append(name)
        streamlit_js_eval(js_expressions="localStorage.setItem('favorites', JSON.stringify(sessionStorage.getItem('favorites')))")


# ---------------------------------------------------------
# UI SECTIONS
# ---------------------------------------------------------

def home_page():
    st.title("✨ Legends & Luminaries")
    st.subheader("Your AI-powered knowledge hub")

    # Daily quote
    names = ["Albert Einstein", "Steve Jobs", "Marcus Aurelius", "Maya Angelou", "Napoleon Hill"]
    selected = names[datetime.now().day % len(names)]
    quotes = fetch_wikiquote_quotes(selected)

    if quotes:
        st.info(f"**Daily Inspiration:** {quotes[0]}")
    else:
        st.info("No quote available.")

    st.markdown("### Featured Achievers")
    featured = [
        "Sundar Pichai", "Elon Musk", "Marie Curie", "Bill Gates", "APJ Abdul Kalam",
        "Isha Ambani", "Greta Thunberg", "Malala Yousafzai"
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
    field = st.selectbox("Select a field:", fields)

    data = sparql_query(field)
    st.write(f"Results for: **{field}**")

    cols = st.columns(3)
    for i, item in enumerate(data):
        with cols[i % 3]:
            name = item["personLabel"]["value"]
            desc = item.get("description", {}).get("value", "")
            img = item.get("image", {}).get("value", None)

            if img:
                st.image(img, width=180)

            st.markdown(f"**{name}**")
            st.write(desc)

            if st.button(f"View {name}", key=f"fld_{i}"):
                st.session_state["selected_person"] = name
                st.experimental_rerun()

def search_page():
    st.title("Search")
    query = st.text_input("Enter a person's name:")

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
            st.error("Person not found.")

def person_detail_page():
    name = st.session_state.get("selected_person")
    if not name:
        st.error("No person selected.")
        return

    st.title(name)

    img = fetch_image_url(name)
    if img:
        st.image(img, width=240)

    summary, url = fetch_wikipedia_summary(name)
    st.write(summary)

    with st.expander("Full Biography"):
        page = wiki.page(name)
        st.write(page.text)

    quotes = fetch_wikiquote_quotes(name)
    if quotes:
        st.markdown("### Quotes")
        for q in quotes[:10]:
            st.write(f"- {q}")

    st.markdown("### Key Lessons")
    lessons = ai_generate_lessons(summary)
    st.write(lessons)

    st.markdown("### Role-play Chat")
    question = st.text_input("Ask something:")
    if question:
        answer = ai_chat_as(name, question, summary)
        st.write(answer)

def philosophers_page():
    st.title("Philosophers")
    st.write("Deep dives into major philosophical figures.")
    names = ["Plato", "Aristotle", "Socrates", "Confucius", "Nietzsche"]

    for name in names:
        if st.button(f"View {name}"):
            st.session_state["selected_person"] = name
            st.experimental_rerun()

def ai_agent_page():
    st.title("AI Knowledge Agent")
    question = st.text_area("Ask anything about people or ideas:")

    if question:
        context = "General knowledge database from Wikipedia/Wikiquote"
        response = ai_general_chat(question, context)
        st.write(response)

def compare_page():
    st.title("Compare Two People")

    a = st.text_input("Person A")
    b = st.text_input("Person B")

    if a and b:
        summaryA, _ = fetch_wikipedia_summary(a)
        summaryB, _ = fetch_wikipedia_summary(b)

        if summaryA and summaryB:
            result = ai_compare(a, b, summaryA, summaryB)
            st.write(result)
        else:
            st.error("One or both names not found.")

def emerging_stars_page():
    st.title("Emerging Stars")
    stars = [
        "Khaby Lame", "Ishan Kishan", "R Praggnanandhaa", "Gitanjali Rao",
        "Emma Raducanu", "Timnit Gebru", "Ben Francis"
    ]

    for s in stars:
        if st.button(f"View {s}"):
            st.session_state["selected_person"] = s
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
