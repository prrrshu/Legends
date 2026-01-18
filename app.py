import streamlit as st
import wikipediaapi
import wikiquote
import requests
import pandas as pd
import re
from datetime import datetime
from groq import Groq
import urllib.parse

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(page_title="Legends & Luminaries",
                   page_icon="✨",
                   layout="wide")

# ---------------------------------------------------------
# SESSION STATE DEFAULTS
# ---------------------------------------------------------
if "selected_person" not in st.session_state:
    st.session_state.selected_person = None
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "ai_search_result" not in st.session_state:
    st.session_state.ai_search_result = ""

# ---------------------------------------------------------
# CLIENTS
# ---------------------------------------------------------
wiki = wikipediaapi.Wikipedia(language="en", extract_format=wikipediaapi.ExtractFormat.WIKI)
groq_client = None
try:
    groq_client = Groq(api_key=st.secrets.get("GROQ_API_KEY"))
except Exception:
    pass

# ---------------------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------------------

@st.cache_data(ttl=3600)
def fetch_wikipedia_summary(name):
    try:
        page = wiki.page(name)
        if page.exists():
            return page.summary[:3000], page.fullurl
    except Exception:
        return None, None
    return None, None

@st.cache_data(ttl=3600)
def fetch_wikiquote_quotes(name):
    try:
        quotes = wikiquote.quotes(name, max_quotes=15)
        return quotes
    except Exception:
        return []

@st.cache_data(ttl=3600)
def fetch_image_url(name):
    try:
        encoded_name = urllib.parse.quote(name)
        url = f"https://en.wikipedia.org/w/api.php?action=query&titles={encoded_name}&prop=pageimages&format=json&pithumbsize=500"
        resp = requests.get(url, timeout=8)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for _, p in pages.items():
            if "thumbnail" in p and "source" in p["thumbnail"]:
                return p["thumbnail"]["source"]
    except Exception:
        return None
    return None

@st.cache_data(ttl=3600)
def sparql_query(field, limit=25):
    query = f"""
    SELECT ?person ?personLabel ?description ?image WHERE {{
      ?person wdt:P31 wd:Q5 .
      ?person wdt:P106 ?occupation .
      ?occupation rdfs:label ?occLabel .
      FILTER(CONTAINS(LCASE(?occLabel), "{field.lower()}"))
      OPTIONAL {{ ?person wdt:P18 ?image. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT {limit}
    """
    try:
        url = "https://query.wikidata.org/sparql"
        headers = {"Accept": "application/sparql-results+json"}
        resp = requests.get(url, params={"query": query}, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
        return resp.json().get("results", {}).get("bindings", [])
    except Exception:
        return []

def ai_generate_lessons(summary):
    if not groq_client or not summary:
        return "[AI unavailable or no summary]"
    try:
        resp = groq_client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role":"system","content":"Extract key life lessons concisely."},
                {"role":"user","content":summary}
            ],
            max_tokens=400,
            temperature=0.5
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[AI Error] {e}"

def ai_search_person(query):
    """AI fallback when Wikipedia fails."""
    if not groq_client:
        return "AI unavailable."
    try:
        resp = groq_client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role":"system","content":"You are an expert summarizer of biographies."},
                {"role":"user","content":f"Give a concise bio for: {query}"}
            ],
            max_tokens=500,
            temperature=0.5
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[AI Error] {e}"

# ---------------------------------------------------------
# RENDER PERSON CARD
# ---------------------------------------------------------
def render_person_card(name, description=None, image_url=None, summary=None):
    st.image(image_url if image_url else "https://via.placeholder.com/160x200?text=No+Image", width=160)
    st.markdown(f"**{name}**")
    if description:
        st.write(description)
    if summary:
        st.write(summary)
    if st.button(f"View {name}", key=name):
        st.session_state.selected_person = name

# ---------------------------------------------------------
# PAGE SECTIONS
# ---------------------------------------------------------
def home_page():
    st.header("✨ Legends & Luminaries - Home")
    names = ["Albert Einstein","Steve Jobs","Marcus Aurelius","Marie Curie","Maya Angelou"]
    pick = names[datetime.now().day % len(names)]
    quotes = fetch_wikiquote_quotes(pick)
    st.info(quotes[0] if quotes else "Be inspired today!")

    st.subheader("Featured Achievers")
    featured = ["Sundar Pichai","Elon Musk","Marie Curie","Bill Gates","APJ Abdul Kalam"]
    cols = st.columns(3)
    for i, name in enumerate(featured):
        with cols[i%3]:
            render_person_card(name, image_url=fetch_image_url(name))

def explore_by_field():
    st.header("Explore by Field")
    fields = ["Technology","Business","Science","Philosophy","Arts","Sports","Politics","Young Achievers"]
    field = st.selectbox("Choose Field:", fields)
    data = sparql_query(field)
    if not data:
        st.warning("No data found for this field.")
        return
    cols = st.columns(3)
    for i, item in enumerate(data):
        with cols[i%3]:
            name = item["personLabel"]["value"]
            desc = item.get("description",{}).get("value","")
            img = item.get("image",{}).get("value")
            render_person_card(name, description=desc, image_url=img)

def search_page():
    st.header("Search Achievers")
    query = st.text_input("Enter Name:")
    if query:
        summary, url = fetch_wikipedia_summary(query)
        if summary:
            img = fetch_image_url(query)
            render_person_card(query, summary=summary, image_url=img)
        else:
            st.warning("Not found on Wikipedia. Using AI to summarize...")
            ai_result = ai_search_person(query)
            st.session_state.ai_search_result = ai_result
            st.info(ai_result)

def person_detail_page():
    name = st.session_state.get("selected_person")
    if not name:
        st.warning("No person selected.")
        return
    st.header(name)
    img = fetch_image_url(name)
    if img:
        st.image(img, width=220)
    summary, url = fetch_wikipedia_summary(name)
    st.write(summary if summary else "[No Wikipedia summary available]")
    with st.expander("Full Biography"):
        try:
            st.write(wiki.page(name).text[:5000])
        except Exception:
            st.write("[Unable to fetch full text]")
    quotes = fetch_wikiquote_quotes(name)
    if quotes:
        st.subheader("Quotes")
        for q in quotes[:8]:
            st.write(f"- {q}")
    st.subheader("Key Lessons")
    st.write(ai_generate_lessons(summary))

def emerging_stars_page():
    st.header("Emerging Stars")
    stars = ["R Praggnanandhaa","Gitanjali Rao","Emma Raducanu"]
    for s in stars:
        render_person_card(s, image_url=fetch_image_url(s))

def ai_agent_page():
    st.header("AI Knowledge Agent")
    question = st.text_area("Ask anything about people or philosophy:")
    if question:
        result = ai_general_chat(question,"General knowledge context")
        st.info(result)

def compare_page():
    st.header("Compare Two People")
    a = st.text_input("Person A")
    b = st.text_input("Person B")
    if a and b:
        sumA,_ = fetch_wikipedia_summary(a)
        sumB,_ = fetch_wikipedia_summary(b)
        if not sumA: sumA = ai_search_person(a)
        if not sumB: sumB = ai_search_person(b)
        result = ai_compare(a,b,sumA,sumB)
        st.info(result)

# ---------------------------------------------------------
# SIDEBAR NAVIGATION
# ---------------------------------------------------------
menu = st.sidebar.selectbox("Navigate", ["Home","Explore by Field","Search","Person Detail","Compare","Emerging Stars","AI Agent"])
if menu=="Home": home_page()
elif menu=="Explore by Field": explore_by_field()
elif menu=="Search": search_page()
elif menu=="Person Detail": person_detail_page()
elif menu=="Compare": compare_page()
elif menu=="Emerging Stars": emerging_stars_page()
elif menu=="AI Agent": ai_agent_page()
