# ui.py
# Manages UI components: login, chat page, prompts, history.

import streamlit as st
import os
import json
from tools import hash_password, verify_password
from api import call_xai_api
from db import get_cursor

PROMPTS_DIR = "./prompts"
os.makedirs(PROMPTS_DIR, exist_ok=True)

# Default Prompts (unchanged)
default_prompts = {
    # ... (same as original)
}

if not any(f.endswith('.txt') for f in os.listdir(PROMPTS_DIR)):
    for filename, content in default_prompts.items():
        with open(os.path.join(PROMPTS_DIR, filename), 'w') as f:
            f.write(content)

def load_prompt_files():
    return [f for f in os.listdir(PROMPTS_DIR) if f.endswith('.txt')]

def login_page():
    st.title("Welcome to PiCoder")
    st.subheader("Login or Register")
    tab1, tab2 = st.tabs(["Login", "Register"])
    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                c = get_cursor(st.session_state['db_conn'])
                c.execute("SELECT password FROM users WHERE username=?", (username,))
                result = c.fetchone()
                if result and verify_password(result[0], password):
                    st.session_state['logged_in'] = True
                    st.session_state['user'] = username
                    st.success(f"Logged in as {username}!")
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
    with tab2:
        with st.form("register_form"):
            new_user = st.text_input("New Username")
            new_pass = st.text_input("New Password", type="password")
            if st.form_submit_button("Register"):
                c = get_cursor(st.session_state['db_conn'])
                c.execute("SELECT * FROM users WHERE username=?", (new_user,))
                if c.fetchone():
                    st.error("Username exists.")
                else:
                    hashed = hash_password(new_pass)
                    c.execute("INSERT INTO users VALUES (?, ?)", (new_user, hashed))
                    st.session_state['db_conn'].commit()
                    st.success("Registered! Login.")

def load_history(convo_id):
    c = get_cursor(st.session_state['db_conn'])
    c.execute("SELECT messages FROM history WHERE convo_id=?", (convo_id,))
    messages = json.loads(c.fetchone()[0])
    st.session_state['messages'] = messages
    st.session_state['current_convo_id'] = convo_id
    st.rerun()

def delete_history(convo_id):
    c = get_cursor(st.session_state['db_conn'])
    c.execute("DELETE FROM history WHERE convo_id=?", (convo_id,))
    st.session_state['db_conn'].commit()
    st.rerun()

@st.cache_data(ttl=60)  # Cache for 1 min
def get_histories(user, search_term=""):
    c = get_cursor(st.session_state['db_conn'])
    c.execute("SELECT convo_id, title FROM history WHERE user=?", (user,))
    histories = c.fetchall()
    return [h for h in histories if search_term.lower() in h[1].lower()]

def chat_page():
    st.title(f"Grok Chat - {st.session_state['user']}")
    with st.sidebar:
        st.header("Chat Settings")
        model = st.selectbox("Select Model", ["grok-4", "grok-3-mini", "grok-code-fast-1"])
        prompt_files = load_prompt_files()
        if not prompt_files:
            custom_prompt = st.text_area("Edit System Prompt", value="You are Grok, a helpful AI.", height=100)
        else:
            selected_file = st.selectbox("Select System Prompt File", prompt_files)
            with open(os.path.join(PROMPTS_DIR, selected_file), "r") as f:
                prompt_content = f.read()
            custom_prompt = st.text_area("Edit System Prompt", value=prompt_content, height=200)
        with st.form("save_prompt_form"):
            new_filename = st.text_input("Save as (e.g., my-prompt.txt)")
            if st.form_submit_button("Save Prompt") and new_filename.endswith(".txt"):
                save_path = os.path.join(PROMPTS_DIR, new_filename)
                with open(save_path, "w") as f:
                    f.write(custom_prompt)
                if "love" in new_filename.lower():
                    with open(save_path, "a") as f:
                        f.write("\n<3")
                st.success(f"Saved to {save_path}!")
                st.rerun()
        uploaded_images = st.file_uploader("Upload Images", type=["jpg", "png"], accept_multiple_files=True)
        enable_tools = st.checkbox("Enable Tools", value=False)
        if enable_tools:
            st.info("Tools enabled: Sandboxed access.")
        st.header("Chat History")
        search_term = st.text_input("Search History")
        histories = get_histories(st.session_state['user'], search_term)
        for convo_id, title in histories:
            col1, col2 = st.columns([3, 1])
            col1.button(title, on_click=lambda cid=convo_id: load_history(cid))
            col2.button("🗑", on_click=lambda cid=convo_id: delete_history(cid))
        if st.button("Clear Current Chat"):
            st.session_state["messages"] = []
            st.rerun()
        if st.button("Toggle Dark Mode"):
            st.session_state["theme"] = "dark" if st.session_state.get("theme") == "light" else "light"
            st.rerun()
        st.markdown(f'<body data-theme="{st.session_state["theme"]}"></body>', unsafe_allow_html=True)
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "current_convo_id" not in st.session_state:
        st.session_state["current_convo_id"] = None
    # Truncate messages
    if len(st.session_state["messages"]) > 50:
        st.session_state["messages"] = st.session_state["messages"][-50:]
        st.warning("Truncated to last 50 messages.")
    # Display chat
    chunk_size = 10
    for i in range(0, len(st.session_state["messages"]), chunk_size):
        chunk = st.session_state["messages"][i : i + chunk_size]
        with st.expander(f"Messages {i+1}-{i+len(chunk)}"):
            for msg in chunk:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
    # Input and response
    prompt = st.chat_input("Type your message...")
    if prompt:
        st.session_state['messages'].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.expander("Thinking..."):
                thought_container = st.empty()
                generator = call_xai_api(model, st.session_state['messages'], custom_prompt, stream=True, image_files=uploaded_images, enable_tools=enable_tools)
                full_response = ""
                for chunk in generator:
                    full_response += chunk
                    thought_container.markdown(full_response)
            marker = "### Final Answer"
            if marker in full_response:
                parts = full_response.split(marker, 1)
                thought_container.markdown(parts[0].strip())
                st.markdown(marker + parts[1])
        st.session_state['messages'].append({"role": "assistant", "content": full_response})
        # Auto-save
        title = st.session_state['messages'][0]['content'][:50] + "..." if st.session_state['messages'] else "New Chat"
        c = get_cursor(st.session_state['db_conn'])
        if st.session_state['current_convo_id'] is None:
            c.execute("INSERT INTO history (user, title, messages) VALUES (?, ?, ?)",
                      (st.session_state['user'], title, json.dumps(st.session_state['messages'])))
            st.session_state['current_convo_id'] = c.lastrowid
        else:
            c.execute("UPDATE history SET title=?, messages=? WHERE convo_id=?",
                      (title, json.dumps(st.session_state['messages']), st.session_state['current_convo_id']))
        st.session_state['db_conn'].commit()
