# app.py
import streamlit as st
import wikipediaapi
import wikiquote
import requests
import pandas as pd
import re
from datetime import datetime
from groq import Groq

# ---------------------------
# CONFIGURATION
# ---------------------------
st.set_page_config(
    page_title="Legends & Luminaries",
    page_icon="✨",
    layout="wide"
)

# ---------------------------
# SESSION STATE INIT
# ---------------------------
if "favorites" not in st.session_state:
    st.session_state["favorites"] = []

if "selected_person" not in st.session_state:
    st.session_state["selected_person"] = None

if "ai_context" not in st.session_state:
    st.session_state["ai_context"] = {}

# ---------------------------
# CLIENTS
# ---------------------------

# Robust Wikipedia client initialization
wiki = wikipediaapi.Wikipedia(language="en")  # <- Fixed to prevent TypeError

# Groq client
try:
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
except Exception:
    client = None

# ---------------------------
# CACHING AND API FUNCTIONS
# ---------------------------

@st.cache_data(ttl=3600)
def fetch_wikipedia_summary(name: str):
    try:
        page = wiki.page(name)
        if page.exists():
            return page.summary, page.fullurl
    except Exception:
        pass
    return None, None

@st.cache_data(ttl=3600)
def fetch_wikiquote_quotes(name: str, max_quotes=12):
    try:
        return wikiquote.quotes(name, max_quotes=max_quotes)
    except Exception:
        return []

@st.cache_data(ttl=3600)
def fetch_image_url(name: str):
    """Fetch image safely from Wikipedia via API"""
    try:
        url = (
            "https://en.wikipedia.org/w/api.php"
            "?action=query&prop=pageimages&format=json&piprop=thumbnail&pithumbsize=600"
            f"&titles={requests.utils.quote(name)}"
        )
        resp = requests.get(url, timeout=10)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for p in pages.values():
            if "thumbnail" in p and "source" in p["thumbnail"]:
                return p["thumbnail"]["source"]
    except Exception:
        return None
    return None

@st.cache_data(ttl=3600)
def sparql_query(field: str):
    """Query Wikidata for notable people"""
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
    try:
        resp = requests.get(
            "https://query.wikidata.org/sparql",
            params={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("results", {}).get("bindings", [])
    except Exception:
        return []

# ---------------------------
# AI FUNCTIONS
# ---------------------------

def ai_generate_lessons(summary: str):
    if not summary or not client:
        return "AI lessons unavailable."
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": "Extract key life lessons in bullet points."},
                {"role": "user", "content": summary}
            ],
            max_tokens=350,
            temperature=0.4
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI error: {e}"

def ai_chat_as(name: str, question: str, context: str):
    if not client:
        return "AI unavailable."
    try:
        resp = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": f"Act as {name}. Use their tone."},
                {"role": "user", "content": f"Context: {context}"},
                {"role": "user", "content": question}
            ],
            max_tokens=600,
            temperature=0.7
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"AI error: {e}"

def ai_general_search(query: str):
    """AI search combining Wikipedia + Wikiquote + context"""
    summary, _ = fetch_wikipedia_summary(query)
    quotes = fetch_wikiquote_quotes(query, max_quotes=3)
    context_text = summary or ""
    if quotes:
        context_text += "\nQuotes:\n" + "\n".join(quotes)
    if not client:
        return context_text or "No information found."
    return ai_chat_as(query, f"Provide a summary and insights about {query}", context_text)

# ---------------------------
# UI FUNCTIONS
# ---------------------------

def render_person_card(name: str, description: str = "", image_url: str = None):
    cols = st.columns([1,3])
    with cols[0]:
        if image_url:
            st.image(image_url, width=120)
        else:
            st.image("https://via.placeholder.com/120x160?text=No+Image", width=120)
    with cols[1]:
        st.markdown(f"**{name}**")
        if description:
            st.write(description[:200] + ("..." if len(description) > 200 else ""))
        if st.button(f"Open {name}", key=f"open_{name}"):
            st.session_state["selected_person"] = name
            st.experimental_rerun()

def home_page():
    st.title("✨ Legends & Luminaries")
    st.subheader("Your AI-powered knowledge hub")

    # Daily quote
    daily_names = ["Albert Einstein", "Steve Jobs", "Marcus Aurelius", "Maya Angelou"]
    selected = daily_names[datetime.now().day % len(daily_names)]
    quotes = fetch_wikiquote_quotes(selected)
    if quotes:
        st.info(f"Daily Inspiration: {quotes[0]}")
    else:
        st.info("No quote today.")

    # Featured people
    st.markdown("### Featured Achievers")
    featured = ["Elon Musk", "Sundar Pichai", "Marie Curie", "Greta Thunberg"]
    for name in featured:
        render_person_card(name, image_url=fetch_image_url(name))

def explore_page():
    st.title("Explore by Field")
    fields = ["Technology","Business","Science","Philosophy","Arts","Sports","Politics","Young Achievers"]
    field = st.selectbox("Select Field:", fields)
    data = sparql_query(field)
    if not data:
        st.warning("No results found.")
        return
    for item in data:
        render_person_card(
            name=item["personLabel"]["value"],
            description=item.get("description", {}).get("value",""),
            image_url=item.get("image", {}).get("value")
        )

def search_page():
    st.title("Search Achievers / AI Search")
    query = st.text_input("Enter name:")
    ai_mode = st.checkbox("AI-enhanced search")
    if query:
        if ai_mode:
            st.write(ai_general_search(query))
        else:
            summary, _ = fetch_wikipedia_summary(query)
            if summary:
                st.write(summary)
                img = fetch_image_url(query)
                if img:
                    st.image(img, width=200)
            else:
                st.error("No info found.")

def person_detail_page():
    name = st.session_state.get("selected_person")
    if not name:
        st.warning("No person selected.")
        return
    st.title(name)
    img = fetch_image_url(name)
    if img: st.image(img, width=250)
    summary, _ = fetch_wikipedia_summary(name)
    st.write(summary)
    with st.expander("Full Biography"):
        page = wiki.page(name)
        st.write(page.text)
    quotes = fetch_wikiquote_quotes(name)
    if quotes:
        st.markdown("### Quotes")
        for q in quotes[:8]:
            st.write(f"- {q}")
    st.markdown("### Key Lessons")
    st.write(ai_generate_lessons(summary))
    st.markdown("### Ask this person")
    q = st.text_input("Your question to them:")
    if q:
        st.write(ai_chat_as(name, q, summary))

def compare_page():
    st.title("Compare Two People")
    a = st.text_input("Person A")
    b = st.text_input("Person B")
    if a and b:
        summaryA,_ = fetch_wikipedia_summary(a)
        summaryB,_ = fetch_wikipedia_summary(b)
        if summaryA and summaryB:
            st.write(ai_chat_as(f"Compare {a} vs {b}", "", f"{summaryA}\n{summaryB}"))
        else:
            st.error("One or both people not found.")

def emerging_page():
    st.title("Emerging Stars")
    stars = ["R Praggnanandhaa","Gitanjali Rao","Emma Raducanu","Khaby Lame"]
    for s in stars:
        render_person_card(s, image_url=fetch_image_url(s))

def philosophers_page():
    st.title("Philosophers")
    names = ["Plato","Aristotle","Socrates","Confucius","Nietzsche"]
    for n in names:
        render_person_card(n, image_url=fetch_image_url(n))

def ai_agent_page():
    st.title("AI Knowledge Agent")
    question = st.text_area("Ask anything:")
    if question:
        st.write(ai_general_search(question))

# ---------------------------
# SIDEBAR
# ---------------------------
menu = st.sidebar.selectbox("Navigate", [
    "Home","Explore by Field","Search","Person Details","Philosophers","AI Agent","Compare Tool","Emerging Stars"
])

if menu=="Home": home_page()
elif menu=="Explore by Field": explore_page()
elif menu=="Search": search_page()
elif menu=="Person Details": person_detail_page()
elif menu=="Philosophers": philosophers_page()
elif menu=="AI Agent": ai_agent_page()
elif menu=="Compare Tool": compare_page()
elif menu=="Emerging Stars": emerging_page()
