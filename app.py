import streamlit as st
import wikipediaapi
import wikiquote
import requests
import pandas as pd
from groq import Groq
from datetime import datetime
import re
import json
import time
from utils.ai_utils import (
    ai_generate_lessons,
    ai_chat_as,
    ai_compare,
    ai_general_chat
)
from utils.data_utils import (
    fetch_wikipedia_summary,
    fetch_wikiquote_quotes,
    fetch_image_url,
    sparql_query
)
from utils.ui_components import (
    render_header,
    render_footer,
    render_person_card,
    render_section_divider
)

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

st.set_page_config(
    page_title="Legends & Luminaries",
    page_icon="✨",
    layout="wide"
)

# Load Custom CSS
with open("assets/custom.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------
# INITIALIZATION
# ---------------------------------------------------------

if "favorites" not in st.session_state:
    st.session_state["favorites"] = []

if "selected_person" not in st.session_state:
    st.session_state["selected_person"] = None

# ---------------------------------------------------------
# UI PAGES
# ---------------------------------------------------------

def home_page():
    render_header("✨ Legends & Luminaries", "Your AI-powered hub of achievers, thinkers, and visionaries.")
    render_section_divider("Daily Inspiration")

    names = ["Albert Einstein", "Marcus Aurelius", "APJ Abdul Kalam", "Marie Curie", "Maya Angelou"]
    pick = names[datetime.now().day % len(names)]
    quotes = fetch_wikiquote_quotes(pick)

    if quotes:
        st.info(f"{quotes[0]}")
    else:
        st.info("No quote available today.")

    render_section_divider("Featured Personalities")

    featured = [
        "Sundar Pichai", "Elon Musk", "Marie Curie", "Bill Gates", "APJ Abdul Kalam",
        "Greta Thunberg", "Malala Yousafzai", "Linus Torvalds"
    ]

    cols = st.columns(4)
    for idx, name in enumerate(featured):
        with cols[idx % 4]:
            render_person_card(name)

def explore_by_field():
    render_header("Explore by Field", "Discover top personalities from your chosen domain.")

    fields = ["Technology", "Business", "Science", "Philosophy", "Arts", "Sports", "Politics", "Young Achievers"]
    field = st.selectbox("Choose a field:", fields)

    results = sparql_query(field)

    st.subheader(f"Showing results for {field}")

    if not results:
        st.warning("No data available.")
        return

    cols = st.columns(3)
    for idx, item in enumerate(results):
        name = item["personLabel"]["value"]
        desc = item.get("description", {}).get("value", "")
        img = item.get("image", {}).get("value")

        with cols[idx % 3]:
            render_person_card(name, description=desc, image_url=img)

def search_page():
    render_header("Search Achievers")
    query = st.text_input("Enter name:")

    if query:
        with st.spinner("Searching..."):
            summary, _ = fetch_wikipedia_summary(query)

        if summary:
            img = fetch_image_url(query)
            render_person_card(query, image_url=img, summary=summary)

            if st.button("View Details"):
                st.session_state["selected_person"] = query
                st.experimental_rerun()
        else:
            st.error("Person not found.")

def person_detail_page():
    name = st.session_state.get("selected_person")
    if not name:
        st.warning("No person selected.")
        return

    render_header(name)

    img = fetch_image_url(name)
    summary, url = fetch_wikipedia_summary(name)

    cols = st.columns([1, 2])
    with cols[0]:
        if img:
            st.image(img, width=250)

    with cols[1]:
        st.write(summary)

    render_section_divider("Biography")
    page = wikipediaapi.Wikipedia("en").page(name)
    st.write(page.text)

    render_section_divider("Quotes")
    for q in fetch_wikiquote_quotes(name)[:10]:
        st.write(f"- {q}")

    render_section_divider("AI Key Lessons")
    st.success(ai_generate_lessons(summary))

    render_section_divider("Chat with Personality")
    question = st.text_input("Ask something:")
    if question:
        st.info(ai_chat_as(name, question, summary))

def compare_page():
    render_header("Compare Two Personalities")

    a = st.text_input("Person A")
    b = st.text_input("Person B")

    if a and b:
        A, _ = fetch_wikipedia_summary(a)
        B, _ = fetch_wikipedia_summary(b)
        if A and B:
            st.write(ai_compare(a, b, A, B))
        else:
            st.error("One or both entries are invalid.")

def ai_agent_page():
    render_header("AI Knowledge Agent")
    question = st.text_area("Ask anything:")
    if question:
        st.write(ai_general_chat(question, "General context"))

def emerging_stars_page():
    render_header("Emerging Stars")
    stars = ["R Praggnanandhaa", "Emma Raducanu", "Ben Francis", "Gitanjali Rao"]

    for name in stars:
        if st.button(f"View {name}"):
            st.session_state["selected_person"] = name
            st.experimental_rerun()

# ---------------------------------------------------------
# SIDEBAR NAVIGATION
# ---------------------------------------------------------

menu = st.sidebar.radio(
    "Navigate",
    ["Home", "Explore by Field", "Search", "Person Details", "AI Agent", "Compare Tool", "Emerging Stars"]
)

if menu == "Home": home_page()
elif menu == "Explore by Field": explore_by_field()
elif menu == "Search": search_page()
elif menu == "Person Details": person_detail_page()
elif menu == "AI Agent": ai_agent_page()
elif menu == "Compare Tool": compare_page()
elif menu == "Emerging Stars": emerging_stars_page()

render_footer()
