import streamlit as st
import wikipediaapi
import wikiquote
import requests
from groq import Groq
from datetime import datetime
import json

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(
    page_title="Legends & Luminaries",
    page_icon="✨",
    layout="wide"
)

# Custom CSS for styling (Enhancements A + E)
st.markdown(
    """
    <style>
        body {background: linear-gradient(135deg, #0f0f0f, #1e1e1e); font-family: 'Segoe UI', sans-serif;}
        .main-title {font-size: 45px; font-weight:700; text-align:center; color:white; padding:10px 0;}
        .sub-title {font-size:22px; text-align:center; color:#cccccc; margin-bottom:20px;}
        .card {background-color: rgba(255,255,255,0.08); border-radius:10px; padding:15px; margin-bottom:15px; transition:0.3s;}
        .card:hover {background-color: rgba(255,255,255,0.12);}
    </style>
    """, unsafe_allow_html=True
)

# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "selected_person" not in st.session_state:
    st.session_state.selected_person = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

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
# UTILITY FUNCTIONS
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_wikipedia_summary(name):
    try:
        page = wiki.page(name)
        if page.exists():
            return page.summary, page.fullurl
    except:
        return None, None
    return None, None

@st.cache_data(ttl=3600)
def fetch_wikiquote_quotes(name):
    try:
        return wikiquote.quotes(name, max_quotes=20)
    except:
        return []

@st.cache_data(ttl=3600)
def fetch_image_url(name):
    try:
        url = f"https://en.wikipedia.org/w/api.php?action=query&titles={name}&prop=pageimages&pithumbsize=600&format=json"
        resp = requests.get(url, timeout=8).json()
        pages = resp.get("query", {}).get("pages", {})
        for page in pages.values():
            if "thumbnail" in page:
                return page["thumbnail"]["source"]
    except:
        pass
    return None

def ai_generate_lessons(summary):
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role":"system","content":"Extract key life lessons in bullets."},
                {"role":"user","content":summary}
            ],
            max_tokens=300
        )
        return response.choices[0].message.content
    except:
        return "AI Error"

def ai_chat_as(name, question, context):
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role":"system","content":f"Act as {name}."},
                {"role":"user","content":f"Bio: {context}"},
                {"role":"user","content":question}
            ],
            max_tokens=600
        )
        return response.choices[0].message.content
    except:
        return "AI Error"

def ai_general_chat(msg):
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role":"user","content":msg}],
            max_tokens=600
        )
        return response.choices[0].message.content
    except:
        return "AI Error"

# ---------------------------------------------------------
# UI FUNCTIONS
# ---------------------------------------------------------
def render_person_card(name, description=None, image_url=None, summary=None):
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    if image_url:
        st.image(image_url, width=160)
    st.write(f"**{name}**")
    if description:
        st.write(description)
    if summary:
        st.write(summary)
    if st.button(f"View {name}"):
        st.session_state.selected_person = name
        st.experimental_rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# PAGES
# ---------------------------------------------------------
def home_page():
    st.markdown("<div class='main-title'>✨ Legends & Luminaries</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-title'>AI-powered hub for achievers & thinkers</div>", unsafe_allow_html=True)

    names = ["Albert Einstein","Marcus Aurelius","APJ Abdul Kalam","Marie Curie","Maya Angelou"]
    pick = names[datetime.now().day % len(names)]
    quotes = fetch_wikiquote_quotes(pick)
    if quotes:
        st.info(quotes[0])

    st.subheader("Featured Achievers")
    featured = ["Sundar Pichai","Elon Musk","Marie Curie","Bill Gates","APJ Abdul Kalam","Greta Thunberg","Malala Yousafzai"]
    cols = st.columns(4)
    for i, name in enumerate(featured):
        with cols[i%4]:
            render_person_card(name, image_url=fetch_image_url(name))

def search_page():
    st.title("Search Achievers")
    q = st.text_input("Enter name:")
    if q:
        summary,_ = fetch_wikipedia_summary(q)
        if summary:
            render_person_card(q,image_url=fetch_image_url(q),summary=summary)
            if st.button("View Details"):
                st.session_state.selected_person = q
                st.experimental_rerun()
        else:
            st.error("Person not found")

def person_detail_page():
    name = st.session_state.selected_person
    if not name:
        st.warning("No person selected")
        return
    st.title(name)
    img = fetch_image_url(name)
    summary,_ = fetch_wikipedia_summary(name)
    if img:
        st.image(img, width=250)
    st.write(summary)
    st.subheader("Quotes")
    for q in fetch_wikiquote_quotes(name)[:10]:
        st.write(f"- {q}")
    st.subheader("AI Key Lessons")
    st.write(ai_generate_lessons(summary))
    st.subheader("Chat with Personality")
    question = st.text_input("Ask something:")
    if question:
        st.write(ai_chat_as(name, question, summary))

def ai_agent_page():
    st.title("AI Knowledge Agent")
    user_msg = st.text_area("Ask anything:")
    if user_msg:
        st.write(ai_general_chat(user_msg))

def compare_page():
    st.title("Compare Two Achievers")
    col1,col2 = st.columns(2)
    a = col1.text_input("Person A")
    b = col2.text_input("Person B")
    if a and b:
        A,_ = fetch_wikipedia_summary(a)
        B,_ = fetch_wikipedia_summary(b)
        if A and B:
            st.write(ai_chat_as("Expert Analyst",f"Compare {a} vs {b}",A+B))
        else:
            st.error("One or both not found")

def emerging_stars_page():
    st.title("Emerging Stars")
    stars = ["R Praggnanandhaa","Emma Raducanu","Ben Francis","Gitanjali Rao"]
    for s in stars:
        if st.button(f"View {s}"):
            st.session_state.selected_person = s
            st.experimental_rerun()

# ---------------------------------------------------------
# SIDEBAR NAVIGATION
# ---------------------------------------------------------
menu = st.sidebar.radio(
    "Navigate",
    ["Home","Search","Person Details","AI Agent","Compare Tool","Emerging Stars"]
)

if menu=="Home": home_page()
elif menu=="Search": search_page()
elif menu=="Person Details": person_detail_page()
elif menu=="AI Agent": ai_agent_page()
elif menu=="Compare Tool": compare_page()
elif menu=="Emerging Stars": emerging_stars_page()
