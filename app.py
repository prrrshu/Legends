import streamlit as st
import wikipediaapi
import wikiquote
import requests
from groq import Groq
import urllib.parse
import random

# ========================
# PREMIUM UI STYLING (CSS Injection)
# ========================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Roboto', sans-serif;
    }

    .stApp {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: #e0e0e0;
    }

    h1, h2, h3, h4 {
        color: #ffffff !important;
        font-weight: 700;
    }

    .stMarkdown, .stText {
        color: #e0e0e0;
    }

    /* Card Style */
    .person-card {
        background: rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(12px);
        border-radius: 16px;
        padding: 20px;
        margin: 12px 0;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        transition: all 0.3s ease;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }

    .person-card:hover {
        transform: translateY(-8px);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
    }

    /* Top Header */
    .top-header {
        background: rgba(0, 0, 0, 0.3);
        backdrop-filter: blur(10px);
        padding: 15px 20px;
        border-radius: 12px;
        margin-bottom: 30px;
        text-align: center;
    }

    /* Sidebar */
    .css-1d391kg {  /* Sidebar background */
        background: rgba(0, 0, 0, 0.4);
    }

    /* Buttons */
    .stButton>button {
        background: rgba(255, 255, 255, 0.2);
        color: white;
        border: none;
        border-radius: 10px;
        transition: 0.3s;
    }

    .stButton>button:hover {
        background: rgba(255, 255, 255, 0.4);
        transform: scale(1.05);
    }

    /* Chat messages */
    .stChatMessage {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 12px;
        margin: 8px 0;
    }
</style>
""", unsafe_allow_html=True)

# ========================
# CONFIG & INITIALIZATION
# ========================
st.set_page_config(page_title="Legends & Luminaries", page_icon="✨", layout="wide")

# Wikipedia with required user_agent (fixes the TypeError)
wiki = wikipediaapi.Wikipedia(
    user_agent="LegendsLuminaries/1.0 (your-email@example.com)",  # Replace with your email
    language='en'
)

# Groq client (fixed model name)
client = Groq(api_key=st.secrets["GROQ_API_KEY"])
MODEL = "llama3-70b-8192"  # Valid, fast, high-quality model on Groq

# Session state
if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "selected_person" not in st.session_state:
    st.session_state.selected_person = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}

# ========================
# FIELD TO QID MAPPING (Accurate Wikidata queries)
# ========================
field_to_qids = {
    "Technology": ["Q82594", "Q1709010"],  # Inventor, Software Engineer, etc.
    "Business": ["Q131524", "Q43845"],      # Entrepreneur, Businessperson
    "Science": ["Q901"],                   # Scientist
    "Philosophy": ["Q4964182"],            # Philosopher
    "Arts": ["Q483501", "Q36180"],         # Artist, Writer
    "Sports": ["Q2066131"],                # Athlete
    "Politics": ["Q82955"],                # Politician
}

# Hardcoded emerging/young stars
emerging_stars = [
    "R Praggnanandhaa", "Gitanjali Rao", "Emma Raducanu", "Alexandr Wang",
    "Vitalik Buterin", "Lucy Guo", "Austin Russell"
]

# ========================
# CACHED FUNCTIONS
# ========================
@st.cache_data(ttl=3600)
def get_wiki_page(title):
    return wiki.page(title)

@st.cache_data(ttl=3600)
def get_quotes(person):
    try:
        return wikiquote.quotes(person, lang="en")[:15]
    except:
        return []

@st.cache_data(ttl=3600)
def get_image_url(person):
    try:
        page = get_wiki_page(person)
        images = list(page.images.keys())
        for img in images:
            if "jpg" in img.lower() or "png" in img.lower():
                return img
    except:
        pass
    return None

@st.cache_data(ttl=3600)
def get_people_by_field(qids, limit=20):
    if not qids:
        return []
    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
    SELECT ?person ?personLabel ?desc ?pic WHERE {{
      ?person wdt:P31 wd:Q5 .
      VALUES ?occ {{ {values} }}
      ?person wdt:P106 ?occ .
      OPTIONAL {{ ?person wdt:P18 ?pic }}
      OPTIONAL {{ ?person schema:description ?desc FILTER(LANG(?desc)="en") }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT {limit*5}
    """
    try:
        r = requests.get("https://query.wikidata.org/sparql", params={'query': sparql, 'format': 'json'})
        data = r.json()
        results = []
        seen = set()
        for item in data['results']['bindings']:
            name = item['personLabel']['value']
            if name in seen: continue
            seen.add(name)
            results.append({
                "name": name,
                "desc": item.get('desc', {}).get('value', ''),
                "pic": item.get('pic', {}).get('value')
            })
            if len(results) >= limit: break
        return results
    except:
        return []

def generate_ai(prompt, max_tokens=600):
    try:
        chat = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=max_tokens
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"AI unavailable: {str(e)}"

# ========================
# PERSON CARD COMPONENT
# ========================
def person_card(person_name, desc="", pic=None):
    with st.container():
        st.markdown('<div class="person-card">', unsafe_allow_html=True)
        col1, col2 = st.columns([1, 4])
        with col1:
            if pic:
                st.image(pic, use_column_width=True)
            else:
                st.image("https://via.placeholder.com/150?text=No+Image", use_column_width=True)
        with col2:
            st.markdown(f"### {person_name}")
            if desc:
                st.caption(desc[:180] + "..." if len(desc) > 180 else desc)
            if st.button("View Details ➜", key=f"view_{person_name}_{random.random()}"):
                st.session_state.selected_person = person_name
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# ========================
# TOP HEADER
# ========================
st.markdown('<div class="top-header"><h1>✨ Legends & Luminaries</h1><p>An AI-powered hub for inspiration from extraordinary people</p></div>', unsafe_allow_html=True)

# ========================
# SIDEBAR NAVIGATION + FAVORITES
# ========================
with st.sidebar:
    st.markdown("### Navigation")
    page = st.radio("Go to", [
        "Home", "Explore by Field", "Search", "Emerging Stars",
        "Philosophers", "Compare Tool", "AI Agent"
    ])

    st.markdown("---")
    st.markdown("### ❤️ Favorites")
    if st.session_state.favorites:
        for fav in st.session_state.favorites[:]:
            col1, col2 = st.columns([4,1])
            with col1:
                if st.button(fav, key=f"fav_btn_{fav}"):
                    st.session_state.selected_person = fav
                    st.rerun()
            with col2:
                if st.button("❌", key=f"rem_{fav}"):
                    st.session_state.favorites.remove(fav)
                    st.rerun()
    else:
        st.caption("No favorites yet")

# ========================
# PAGE ROUTING
# ========================
if st.session_state.selected_person:
    # PERSON DETAIL PAGE WITH TABS
    name = st.session_state.selected_person
    st.markdown(f"## {name}")
    if st.button("← Back"):
        st.session_state.selected_person = None
        st.rerun()

    # Favorite toggle
    heart = "❤️" if name in st.session_state.favorites else "🤍"
    if st.button(f"{heart} Favorite", key="fav_toggle"):
        if name in st.session_state.favorites:
            st.session_state.favorites.remove(name)
        else:
            st.session_state.favorites.append(name)
        st.rerun()

    page_obj = get_wiki_page(name)
    summary = page_obj.summary if page_obj.exists() else ""
    full_text = page_obj.text if page_obj.exists() else ""
    image = get_image_url(name)
    quotes = get_quotes(name)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "Biography", "Quotes", "Key Lessons", "Chat as Person"])

    with tab1:
        if image:
            st.image(image, width=300)
        st.write(summary or "No summary available.")

    with tab2:
        st.write(full_text[:15000] or "No full text available.")

    with tab3:
        if quotes:
            for q in quotes:
                st.markdown(f"> {q}")
        else:
            st.info("No quotes found.")

    with tab4:
        if summary:
            with st.spinner("Generating insights..."):
                lessons = generate_ai(f"Extract 10 key life lessons from this biography in bullet points:\n{summary[:4000]}")
                st.markdown(lessons)
        else:
            st.info("No data for lessons.")

    with tab5:
        st.markdown("### Talk to this person (AI role-play)")
        if name not in st.session_state.chat_history:
            st.session_state.chat_history[name] = []
        for msg in st.session_state.chat_history[name]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        if prompt := st.chat_input(f"Ask {name}..."):
            st.session_state.chat_history[name].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = generate_ai(
                        f"You are {name}. Respond in first person based on known facts and biography:\n{summary[:3000]}\nUser: {prompt}"
                    )
                    st.markdown(response)
            st.session_state.chat_history[name].append({"role": "assistant", "content": response})

else:
    # MAIN PAGES
    if page == "Home":
        st.markdown("### ✨ Daily Inspiration")
        daily = random.choice(["Elon Musk", "Albert Einstein", "Marie Curie", "Steve Jobs"])
        q = get_quotes(daily)
        if q:
            st.info(f'"{q[0]}" — {daily}')
        st.markdown("### Featured Legends")
        for p in ["Elon Musk", "Ada Lovelace", "Leonardo da Vinci", "Serena Williams"]:
            person_card(p)

    elif page == "Explore by Field":
        field = st.selectbox("Select Field", list(field_to_qids.keys()))
        people = get_people_by_field(field_to_qids[field])
        for p in people:
            person_card(p["name"], p["desc"], p["pic"])

    elif page == "Search":
        query = st.text_input("Search for a person")
        if query:
            page_obj = get_wiki_page(query)
            if page_obj.exists():
                person_card(query, page_obj.summary[:200], get_image_url(query))
            else:
                st.error("Not found")

    elif page == "Emerging Stars":
        st.markdown("### 🌟 Rising Young Achievers")
        for name in emerging_stars:
            person_card(name, image_url=get_image_url(name))

    elif page == "Philosophers":
        philosophers = ["Aristotle", "Plato", "Socrates", "Nietzsche", "Confucius", "Kant"]
        for name in philosophers:
            person_card(name, image_url=get_image_url(name))

    elif page == "Compare Tool":
        col1, col2 = st.columns(2)
        with col1:
            p1 = st.text_input("Person 1")
        with col2:
            p2 = st.text_input("Person 2")
        if p1 and p2 and st.button("Compare"):
            s1 = get_wiki_page(p1).summary if get_wiki_page(p1).exists() else ""
            s2 = get_wiki_page(p2).summary if get_wiki_page(p2).exists() else ""
            comparison = generate_ai(f"Compare {p1} and {p2} in a beautiful markdown table + similarities/differences:\n{s1[:2000]}\n{s2[:2000]}")
            st.markdown(comparison)

    elif page == "AI Agent":
        st.markdown("### 🤖 AI Knowledge Agent")
        st.caption("Ask anything about people, history, philosophy, etc.")
        if "agent_history" not in st.session_state:
            st.session_state.agent_history = []
        for msg in st.session_state.agent_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        if prompt := st.chat_input("Your question"):
            st.session_state.agent_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    resp = generate_ai(prompt)
                    st.markdown(resp)
            st.session_state.agent_history.append({"role": "assistant", "content": resp})
