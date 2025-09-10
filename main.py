# main.py
# This is the entry point of the refactored application.
# It handles Streamlit setup, session state initialization, and page routing.

import streamlit as st
from db import init_db, get_cursor
from ui import login_page, chat_page
from tools import get_current_time
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("XAI_API_KEY")
if not API_KEY:
    st.error("XAI_API_KEY not set in .env! Please add it and restart.")
LANGSEARCH_API_KEY = os.getenv("LANGSEARCH_API_KEY")
if not LANGSEARCH_API_KEY:
    st.warning("LANGSEARCH_API_KEY not set in .env—web search tool will fail.")

# Initialize DB connection (singleton-like via session state)
if 'db_conn' not in st.session_state:
    st.session_state['db_conn'] = init_db()
    st.session_state['db_cursor'] = get_cursor(st.session_state['db_conn'])

# Custom CSS (unchanged, but moved here for centralization)
st.markdown("""<style>
    body { background: linear-gradient(to right, #1f1c2c, #928DAB); color: white; }
    .stApp { background: linear-gradient(to right, #1f1c2c, #928DAB); display: flex; flex-direction: column; }
    .sidebar .sidebar-content { background: rgba(0, 0, 0, 0.5); border-radius: 10px; }
    .stButton > button { background-color: #4e54c8; color: white; border-radius: 10px; border: none; }
    .stButton > button:hover { background-color: #8f94fb; }
    .chat-bubble-user { background-color: #2b2b2b; border-radius: 15px; padding: 10px 15px; margin: 5px 0; text-align: right; max-width: 80%; align-self: flex-end; }
    .chat-bubble-assistant { background-color: #3c3c3c; border-radius: 15px; padding: 10px 15px; margin: 5px 0; text-align: left; max-width: 80%; align-self: flex-start; }
    [data-theme="dark"] .stApp { background: linear-gradient(to right, #000000, #434343); }
</style>""", unsafe_allow_html=True)

if __name__ == "__main__":
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['theme'] = 'light'  # Default theme
    # Init Time Check (on app start)
    if 'init_time' not in st.session_state:
        st.session_state['init_time'] = get_current_time(sync=True)  # Auto-sync on start
    if not st.session_state['logged_in']:
        login_page()
    else:
        chat_page()
