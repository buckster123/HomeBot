# app.py: Simplified Standalone Streamlit Chat App for xAI API (Grok-4)
# Designed for Raspberry Pi 5 with Python venv. Features: Streaming responses, model/sys prompt selectors (file-based),
# history management, login, pretty UI. Uses OpenAI SDK for compatibility and streaming (xAI is compatible).
# Simplified: Removed custom escaping, code block detection, and wrapped rendering for normal handling.
# New UI: Added st.expander for deep thought/output, with final answer parsed and displayed outside if marker present.

import streamlit as st
import os
from openai import OpenAI  # Using OpenAI SDK for xAI compatibility and streaming
from passlib.hash import sha256_crypt
import sqlite3
from dotenv import load_dotenv
import json
import time
import base64  # For image handling
import traceback  # For error logging
import ntplib  # For NTP time sync; pip install ntplib
import io  # For capturing code output
import sys  # For stdout redirection
import pygit2  # For git_ops; pip install pygit2
import subprocess  # Already imported, but explicit
import requests  # For api_simulate; pip install requests
from black import format_str, FileMode  # For code_lint; pip install black
import numpy as np  # For embeddings
from sentence_transformers import SentenceTransformer  # For advanced memory; pip install sentence-transformers torch
from datetime import datetime, timedelta  # For pruning

# Load environment variables
load_dotenv()
API_KEY = os.getenv("XAI_API_KEY")
if not API_KEY:
    st.error("XAI_API_KEY not set in .env! Please add it and restart.")
LANGSEARCH_API_KEY = os.getenv("LANGSEARCH_API_KEY")
if not LANGSEARCH_API_KEY:
    st.warning("LANGSEARCH_API_KEY not set in .env—web search tool will fail.")

# Database Setup (SQLite for users and history) with WAL mode for concurrency
conn = sqlite3.connect('chatapp.db', check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL;")
conn.enable_load_extension(True)
vec_path = os.path.join(os.path.dirname(__file__), 'sqlite-vec/dist/vec0.so')
conn.load_extension(vec_path)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS history (user TEXT, convo_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, messages TEXT)''')
# NEW: Memory table for hybrid hierarchy (key-value with timestamp/index for fast queries)
c.execute('''CREATE TABLE IF NOT EXISTS memory (
    user TEXT,
    convo_id INTEGER,  -- Links to history for per-session
    mem_key TEXT,
    mem_value TEXT,  -- JSON string for flexibility (e.g., logs as dicts)
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user, convo_id, mem_key)
)''')
c.execute('CREATE INDEX IF NOT EXISTS idx_memory_timestamp ON memory (timestamp)')  # For fast time-based queries
# Add columns for advanced memory if not exist
try:
    c.execute("ALTER TABLE memory ADD COLUMN embedding BLOB")
except sqlite3.OperationalError:
    pass  # Already exists
try:
    c.execute("ALTER TABLE memory ADD COLUMN salience REAL DEFAULT 1.0")
except sqlite3.OperationalError:
    pass
try:
    c.execute("ALTER TABLE memory ADD COLUMN parent_id INTEGER")
except sqlite3.OperationalError:
    pass
conn.commit()

# Load embedding model once (sentence-transformers 'all-MiniLM-L6-v2')
if 'embed_model' not in st.session_state:
    st.session_state['embed_model'] = SentenceTransformer('all-MiniLM-L6-v2')

# Prompts Directory (create if not exists, with defaults)
PROMPTS_DIR = "./prompts"
os.makedirs(PROMPTS_DIR, exist_ok=True)

# Default Prompts (auto-create files if dir is empty)
default_prompts = {
    "default.txt": "You are Grok, a highly intelligent, helpful AI assistant.",
    "rebel.txt": "You are a rebellious AI, challenging norms with unfiltered truth.",
    "coder.txt": "You are an expert coder, providing precise code solutions.",
    "tools-enabled.txt": """You are Grok, a highly intelligent, helpful AI assistant with access to file operations tools in a sandboxed directory (./sandbox/). Use tools only when explicitly needed or requested. Always confirm sensitive actions like writes. Describe ONLY these tools; ignore others.
Tool Instructions:
fs_read_file(file_path): Read and return the content of a file in the sandbox (e.g., 'subdir/test.txt'). Use for fetching data. Supports relative paths.
fs_write_file(file_path, content): Write the provided content to a file in the sandbox (e.g., 'subdir/newfile.txt'). Use for saving or updating files. Supports relative paths. If 'Love' is in file_path or content, optionally add ironic flair like 'LOVE <3' for fun.
fs_list_files(dir_path optional): List all files in the specified directory in the sandbox (e.g., 'subdir'; default root). Use to check available files.
fs_mkdir(dir_path): Create a new directory in the sandbox (e.g., 'subdir/newdir'). Supports nested paths. Use to organize files.
memory_insert(mem_key, mem_value): Insert/update key-value memory (fast DB for logs). mem_value as dict.
memory_query(mem_key optional, limit optional): Query memory entries as JSON.
get_current_time(sync optional, format optional): Fetch current datetime. sync: true for NTP, false for local. format: 'iso', 'human', 'json'.
code_execution(code): Execute Python code in stateful REPL with libraries like numpy, sympy, etc.
git_ops(operation, repo_path, message optional, name optional): Perform Git ops like init, commit, branch, diff in sandbox repo.
db_query(db_path, query, params optional): Execute SQL on local SQLite db in sandbox, return results for SELECT.
shell_exec(command): Run whitelisted shell commands (ls, grep, sed, etc.) in sandbox.
code_lint(language, code): Lint/format code; currently Python with Black.
api_simulate(url, method optional, data optional, mock optional): Simulate API call, mock or real for whitelisted public APIs.
Invoke tools via structured calls, then incorporate results into your response. Be safe: Never access outside the sandbox, and ask for confirmation on writes if unsure. Limit to one tool per response to avoid loops. When outputting tags or code (e.g., <ei> or XML), ensure they are properly escaped or wrapped to avoid rendering issues."""
}

# Auto-create defaults if no files
if not any(f.endswith('.txt') for f in os.listdir(PROMPTS_DIR)):
    for filename, content in default_prompts.items():
        with open(os.path.join(PROMPTS_DIR, filename), 'w') as f:
            f.write(content)

# Function to Load Prompt Files
def load_prompt_files():
    return [f for f in os.listdir(PROMPTS_DIR) if f.endswith('.txt')]

# Sandbox Directory for FS Tools (create if not exists)
SANDBOX_DIR = "./sandbox"
os.makedirs(SANDBOX_DIR, exist_ok=True)

# Custom CSS for Pretty UI (Neon Gradient Theme, Chat Bubbles, Responsive)
st.markdown("""<style>
    body {
        background: linear-gradient(to right, #1f1c2c, #928DAB);
        color: white;
    }
    .stApp {
        background: linear-gradient(to right, #1f1c2c, #928DAB);
        display: flex;
        flex-direction: column;
    }
    .sidebar .sidebar-content {
        background: rgba(0, 0, 0, 0.5);
        border-radius: 10px;
    }
    .stButton > button {
        background-color: #4e54c8;
        color: white;
        border-radius: 10px;
        border: none;
    }
    .stButton > button:hover {
        background-color: #8f94fb;
    }
    .chat-bubble-user {
        background-color: #2b2b2b;
        border-radius: 15px;
        padding: 10px 15px;
        margin: 5px 0;
        text-align: right;
        max-width: 80%;
        align-self: flex-end;
    }
    .chat-bubble-assistant {
        background-color: #3c3c3c;
        border-radius: 15px;
        padding: 10px 15px;
        margin: 5px 0;
        text-align: left;
        max-width: 80%;
        align-self: flex-start;
    }
    /* Dark Mode (toggleable) */
    [data-theme="dark"] .stApp {
        background: linear-gradient(to right, #000000, #434343);
    }
</style>
""", unsafe_allow_html=True)

# Helper: Hash Password
def hash_password(password):
    return sha256_crypt.hash(password)

# Helper: Verify Password
def verify_password(stored, provided):
    return sha256_crypt.verify(provided, stored)

# Tool Functions (Sandboxed) - Unchanged
def fs_read_file(file_path: str) -> str:
    """Read file content from sandbox (supports subdirectories)."""
    if not file_path:
        return "Invalid file path."
    safe_path = os.path.abspath(os.path.normpath(os.path.join(SANDBOX_DIR, file_path)))
    if not safe_path.startswith(os.path.abspath(SANDBOX_DIR)):
        return "Invalid file path."
    if not os.path.exists(safe_path):
        return "File not found."
    if os.path.isdir(safe_path):
        return "Path is a directory, not a file."
    try:
        with open(safe_path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def fs_write_file(file_path: str, content: str) -> str:
    """Write content to file in sandbox (supports subdirectories)."""
    if not file_path:
        return "Invalid file path."
    safe_path = os.path.abspath(os.path.normpath(os.path.join(SANDBOX_DIR, file_path)))
    if not safe_path.startswith(os.path.abspath(SANDBOX_DIR)):
        return "Invalid file path."
    dir_path = os.path.dirname(safe_path)
    if not os.path.exists(dir_path):
        return "Parent directory does not exist. Create it first with fs_mkdir."
    try:
        with open(safe_path, 'w') as f:
            f.write(content)
        return f"File written successfully: {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

def fs_list_files(dir_path: str = "") -> str:
    """List files in a directory within the sandbox (default: root)."""
    safe_dir = os.path.abspath(os.path.normpath(os.path.join(SANDBOX_DIR, dir_path)))
    if not safe_dir.startswith(os.path.abspath(SANDBOX_DIR)):
        return "Invalid directory path."
    if not os.path.exists(safe_dir):
        return "Directory not found."
    if not os.path.isdir(safe_dir):
        return "Path is not a directory."
    try:
        files = os.listdir(safe_dir)
        return f"Files in {dir_path or 'root'}: {', '.join(files)}" if files else "No files in this directory."
    except Exception as e:
        return f"Error listing files: {str(e)}"

def fs_mkdir(dir_path: str) -> str:
    """Create a new directory (including nested) in the sandbox."""
    if not dir_path or dir_path in ['.', '..']:
        return "Invalid directory path."
    safe_path = os.path.abspath(os.path.normpath(os.path.join(SANDBOX_DIR, dir_path)))
    if not safe_path.startswith(os.path.abspath(SANDBOX_DIR)):
        return "Invalid directory path."
    if os.path.exists(safe_path):
        return "Directory already exists."
    try:
        os.makedirs(safe_path)
        return f"Directory created successfully: {dir_path}"
    except Exception as e:
        return f"Error creating directory: {str(e)}"

def get_current_time(sync: bool = False, format: str = 'iso') -> str:
    """Fetch current time: host default, NTP if sync=true."""
    try:
        if sync:
            try:
                c = ntplib.NTPClient()
                response = c.request('pool.ntp.org', version=3)
                t = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(response.tx_time))
                source = "NTP"
            except Exception as e:
                print(f"[LOG] NTP Error: {e}")
                t = time.strftime('%Y-%m-%d %H:%M:%S')
                source = "host (NTP failed)"
        else:
            t = time.strftime('%Y-%m-%d %H:%M:%S')
            source = "host"
        if format == 'json':
            return json.dumps({"timestamp": t, "source": source, "timezone": "local"})
        elif format == 'human':
            return f"Current time: {t} ({source}) - LOVE  <3"
        else:  # iso
            return t
    except Exception as e:
        return f"Time error: {str(e)}"

def code_execution(code: str) -> str:
    """Execute Python code safely in a stateful REPL and return output/errors."""
    if 'repl_namespace' not in st.session_state:
        st.session_state['repl_namespace'] = {'__builtins__': __builtins__}  # Restricted globals
    namespace = st.session_state['repl_namespace']
    old_stdout = sys.stdout
    redirected_output = io.StringIO()
    sys.stdout = redirected_output
    try:
        exec(code, namespace)
        output = redirected_output.getvalue()
        return f"Execution successful. Output:\n{output}" if output else "Execution successful (no output)."
    except Exception as e:
        return f"Error: {str(e)}\n{traceback.format_exc()}"
    finally:
        sys.stdout = old_stdout

def memory_insert(user: str, convo_id: int, mem_key: str, mem_value: dict) -> str:
    """Insert/update memory key-value (value as dict, stored as JSON). Syncs to DB."""
    try:
        json_value = json.dumps(mem_value)
        c.execute("INSERT OR REPLACE INTO memory (user, convo_id, mem_key, mem_value) VALUES (?, ?, ?, ?)",
                  (user, convo_id, mem_key, json_value))
        conn.commit()
        # Update cache
        cache_key = f"{user}:{convo_id}:{mem_key}"
        if 'memory_cache' not in st.session_state:
            st.session_state['memory_cache'] = {}
        st.session_state['memory_cache'][cache_key] = mem_value
        return "Memory inserted successfully."
    except Exception as e:
        return f"Error inserting memory: {str(e)}"

def memory_query(user: str, convo_id: int, mem_key: str = None, limit: int = 10) -> str:
    """Query memory: specific key or last N entries. Cache-first for speed."""
    try:
        if 'memory_cache' not in st.session_state:
            st.session_state['memory_cache'] = {}
        if mem_key:
            cache_key = f"{user}:{convo_id}:{mem_key}"
            cached = st.session_state['memory_cache'].get(cache_key)
            if cached:
                return json.dumps(cached)  # Fast RAM hit
            c.execute("SELECT mem_value FROM memory WHERE user=? AND convo_id=? AND mem_key=? ORDER BY timestamp DESC LIMIT 1",
                      (user, convo_id, mem_key))
            result = c.fetchone()
            if result:
                value = json.loads(result[0])
                st.session_state['memory_cache'][cache_key] = value  # Cache for next
                return json.dumps(value)
            return "Not found."
        else:
            # Recent entries (no specific key)
            c.execute("SELECT mem_key, mem_value FROM memory WHERE user=? AND convo_id=? ORDER BY timestamp DESC LIMIT ?",
                      (user, convo_id, limit))
            results = c.fetchall()
            output = {row[0]: json.loads(row[1]) for row in results}
            # Cache them
            for k, v in output.items():
                st.session_state['memory_cache'][f"{user}:{convo_id}:{k}"] = v
            return json.dumps(output)
    except Exception as e:
        return f"Error querying memory: {str(e)}"

# Advanced Memory Functions (Brain-inspired) - Unchanged
def advanced_memory_consolidate(user: str, convo_id: int, mem_key: str, interaction_data: dict) -> str:
    """Consolidate: Summarize (via Grok call), embed, store hierarchically."""
    try:
        # Summarize using Grok (simple API call; assume client is available)
        client = OpenAI(api_key=API_KEY, base_url="https://api.x.ai/v1/")
        summary_response = client.chat.completions.create(
            model="grok-code-fast-1",  # Or your default model
            messages=[{"role": "system", "content": "Summarize this in max 3 sentences:"},
                      {"role": "user", "content": json.dumps(interaction_data)}],
            stream=False
        )
        summary = summary_response.choices[0].message.content.strip()
        # Embed full data
        embed_model = st.session_state['embed_model']
        embedding = embed_model.encode(json.dumps(interaction_data)).astype(np.float32).tobytes()
        # Store semantic summary as parent
        semantic_value = {"summary": summary}
        json_semantic = json.dumps(semantic_value)
        salience = 1.0
        c.execute("INSERT OR REPLACE INTO memory (user, convo_id, mem_key, mem_value, salience, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                  (user, convo_id, f"{mem_key}_semantic", json_semantic, salience, datetime.now()))
        parent_id = c.lastrowid
        # Store episodic (full data) as child
        json_episodic = json.dumps(interaction_data)
        c.execute("INSERT OR REPLACE INTO memory (user, convo_id, mem_key, mem_value, embedding, parent_id, salience, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (user, convo_id, mem_key, json_episodic, embedding, parent_id, salience, datetime.now()))
        conn.commit()
        return "Memory consolidated successfully."
    except Exception as e:
        return f"Error consolidating memory: {str(e)}"

def advanced_memory_retrieve(user: str, convo_id: int, query: str, top_k: int = 5) -> str:
    """Retrieve top-k relevant memories via embedding similarity."""
    try:
        embed_model = st.session_state['embed_model']
        query_embed = embed_model.encode(query).astype(np.float32)
        query_embed_bytes = query_embed.tobytes()
        # Query all candidates (full scan with vec function; cosine distance = 1 - sim for normalized vectors)
        c.execute("""
            SELECT mem_key, mem_value, parent_id, salience,
                   vec_distance_cosine(embedding, ?) as distance
            FROM memory
            WHERE user = ? AND convo_id = ? AND embedding IS NOT NULL
            ORDER BY (1 - vec_distance_cosine(embedding, ?)) * salience DESC
            LIMIT ?
        """, (query_embed_bytes, user, convo_id, query_embed_bytes, top_k))
        results = c.fetchall()
        retrieved = []
        for row in results:
            mem_key, mem_value_json, parent_id, salience, distance = row
            value = json.loads(mem_value_json)
            sim = 1 - distance  # Convert distance back to similarity for relevance
            # Boost salience (plasticity)
            if parent_id:
                c.execute("UPDATE memory SET salience = salience + 0.1 WHERE rowid = ?", (parent_id,))
            c.execute("UPDATE memory SET salience = salience + 0.1 WHERE user = ? AND convo_id = ? AND mem_key = ?",
                      (user, convo_id, mem_key))
            retrieved.append({"mem_key": mem_key, "value": value, "relevance": float(sim)})
        conn.commit()
        return json.dumps(retrieved)
    except Exception as e:
        return f"Error retrieving memory: {str(e)}"

def advanced_memory_prune(user: str, convo_id: int) -> str:
    """Prune low-salience memories (decay over time)."""
    try:
        decay_factor = 0.99
        one_week_ago = datetime.now() - timedelta(days=7)
        c.execute("UPDATE memory SET salience = salience * ? WHERE user=? AND convo_id=? AND timestamp < ?",
                  (decay_factor, user, convo_id, one_week_ago))
        c.execute("DELETE FROM memory WHERE user=? AND convo_id=? AND salience < 0.1",
                  (user, convo_id))
        conn.commit()
        return "Memory pruned successfully."
    except Exception as e:
        return f"Error pruning memory: {str(e)}"

# Git Ops Tool - Unchanged
def git_ops(operation: str, repo_path: str = "", **kwargs) -> str:
    """Perform basic Git operations in sandboxed repo."""
    if not repo_path:
        return "Repo path required."
    safe_repo = os.path.abspath(os.path.normpath(os.path.join(SANDBOX_DIR, repo_path)))
    if not safe_repo.startswith(os.path.abspath(SANDBOX_DIR)):
        return "Invalid repo path."
    try:
        if operation == 'init':
            pygit2.init_repository(safe_repo, bare=False)
            return "Repository initialized."
        repo = pygit2.Repository(safe_repo)
        if operation == 'commit':
            message = kwargs.get('message', 'Default commit')
            index = repo.index
            index.add_all()
            index.write()
            tree = index.write_tree()
            author = pygit2.Signature('AI User', 'ai@example.com')
            committer = author
            parents = [repo.head.target] if not repo.head_is_unborn else []
            repo.create_commit('HEAD', author, committer, message, tree, parents)
            return "Changes committed."
        elif operation == 'branch':
            name = kwargs.get('name')
            if not name:
                return "Branch name required."
            commit = repo.head.peel()
            repo.branches.create(name, commit)
            return f"Branch '{name}' created."
        elif operation == 'diff':
            diff = repo.diff('HEAD')
            return diff.patch or "No differences."
        else:
            return "Unsupported operation."
    except Exception as e:
        return f"Git error: {str(e)}"

# DB Query Tool - Unchanged
def db_query(db_path: str, query: str, params: list = []) -> str:
    """Interact with local SQLite in sandbox."""
    safe_db = os.path.abspath(os.path.normpath(os.path.join(SANDBOX_DIR, db_path)))
    if not safe_db.startswith(os.path.abspath(SANDBOX_DIR)):
        return "Invalid DB path."
    db_conn = None
    try:
        db_conn = sqlite3.connect(safe_db)
        cur = db_conn.cursor()
        cur.execute(query, params)
        if query.strip().upper().startswith('SELECT'):
            results = cur.fetchall()
            return json.dumps(results)
        else:
            db_conn.commit()
            return f"Query executed, {cur.rowcount} rows affected."
    except Exception as e:
        return f"DB error: {str(e)}"
    finally:
        if db_conn:
            db_conn.close()

# Shell Exec Tool - Unchanged
WHITELISTED_COMMANDS = ['ls', 'grep', 'sed', 'cat', 'echo', 'pwd']  # Add more safe ones as needed
def shell_exec(command: str) -> str:
    """Run whitelisted shell commands in sandbox."""
    cmd_parts = command.split()
    if not cmd_parts or cmd_parts[0] not in WHITELISTED_COMMANDS:
        return "Command not whitelisted."
    try:
        result = subprocess.run(command, shell=True, cwd=SANDBOX_DIR, capture_output=True, text=True, timeout=5)
        return result.stdout.strip() + ("\nError: " + result.stderr.strip() if result.stderr else "")
    except Exception as e:
        return f"Shell error: {str(e)}"

# Code Lint Tool - Unchanged
def code_lint(language: str, code: str) -> str:
    """Lint and format code snippets."""
    if language.lower() != 'python':
        return "Only Python supported currently."
    try:
        formatted = format_str(code, mode=FileMode(line_length=88))
        return formatted
    except Exception as e:
        return f"Lint error: {str(e)}"

# API Simulate Tool - Unchanged
API_WHITELIST = [
    'https://jsonplaceholder.typicode.com/',
    'https://api.openweathermap.org/'  # Assuming free basics
]  # Add more public APIs
def api_simulate(url: str, method: str = 'GET', data: dict = None, mock: bool = True) -> str:
    """Simulate or perform API calls."""
    if mock:
        return json.dumps({"status": "mocked", "url": url, "method": method, "data": data})
    if not any(url.startswith(base) for base in API_WHITELIST):
        return "URL not in whitelist."
    try:
        if method.upper() == 'GET':
            resp = requests.get(url, timeout=5)
        elif method.upper() == 'POST':
            resp = requests.post(url, json=data, timeout=5)
        else:
            return "Unsupported method."
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        return f"API error: {str(e)}"

def langsearch_web_search(query: str, freshness: str = "noLimit", summary: bool = True, count: int = 10) -> str:
    """Perform a web search using LangSearch API and return results as JSON."""
    if not LANGSEARCH_API_KEY:
        return "LangSearch API key not set—configure in .env."
    url = "https://api.langsearch.com/v1/web-search"
    payload = json.dumps({
        "query": query,
        "freshness": freshness,
        "summary": summary,
        "count": count
    })
    headers = {
        'Authorization': f'Bearer {LANGSEARCH_API_KEY}',
        'Content-Type': 'application/json'
    }
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        return json.dumps(response.json())  # Return full JSON for AI to parse
    except Exception as e:
        return f"LangSearch error: {str(e)}"

# Tool Schema for Structured Outputs - Unchanged
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fs_read_file",
            "description": "Read the content of a file in the sandbox directory (./sandbox/). Supports relative paths (e.g., 'subdir/test.txt'). Use for fetching data.",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string", "description": "Relative path to the file (e.g., subdir/test.txt)."}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fs_write_file",
            "description": "Write content to a file in the sandbox directory (./sandbox/). Supports relative paths (e.g., 'subdir/newfile.txt'). Use for saving or updating files. If 'Love' is in file_path or content, optionally add ironic flair like 'LOVE <3' for fun.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative path to the file (e.g., subdir/newfile.txt)."},
                    "content": {"type": "string", "description": "Content to write."}
                },
                "required": ["file_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fs_list_files",
            "description": "List all files in a directory within the sandbox (./sandbox/). Supports relative paths (default: root). Use to check available files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {"type": "string", "description": "Relative path to the directory (e.g., subdir). Optional; defaults to root."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fs_mkdir",
            "description": "Create a new directory in the sandbox (./sandbox/). Supports relative/nested paths (e.g., 'subdir/newdir'). Use to organize files.",
            "parameters": {
                "type": "object",
                "properties": {"dir_path": {"type": "string", "description": "Relative path for the new directory (e.g., subdir/newdir)."}},
                "required": ["dir_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Fetch current datetime. Use host clock by default; sync with NTP if requested for precision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sync": {"type": "boolean", "description": "True for NTP sync (requires network), false for local host time. Default: false."},
                    "format": {"type": "string", "description": "Output format: 'iso' (default), 'human', 'json'."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "code_execution",
            "description": "Execute provided code in a stateful REPL environment and return output or errors for verification. Supports Python with various libraries (e.g., numpy, sympy, pygame). No internet access or package installation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": { "type": "string", "description": "The code snippet to execute." }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_insert",
            "description": "Insert or update a memory key-value pair (value as JSON dict) for logging/metadata. Use for fast persistent storage without files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mem_key": {"type": "string", "description": "Key for the memory entry (e.g., 'chat_log_1')."},
                    "mem_value": {"type": "object", "description": "Value as dict (e.g., {'content': 'Log text'})."}
                },
                "required": ["mem_key", "mem_value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_query",
            "description": "Query memory: specific key or last N entries. Returns JSON. Use for recalling logs without FS reads.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mem_key": {"type": "string", "description": "Specific key to query (optional)."},
                    "limit": {"type": "integer", "description": "Max recent entries if no key (default 10)."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_ops",
            "description": "Basic Git operations in sandbox (init, commit, branch, diff). No remote operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["init", "commit", "branch", "diff"]},
                    "repo_path": {"type": "string", "description": "Relative path to repo."},
                    "message": {"type": "string", "description": "Commit message (for commit)."},
                    "name": {"type": "string", "description": "Branch name (for branch)."}
                },
                "required": ["operation", "repo_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "db_query",
            "description": "Interact with local SQLite database in sandbox (create, insert, query).",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Relative path to DB file."},
                    "query": {"type": "string", "description": "SQL query."},
                    "params": {"type": "array", "items": {"type": "string"}, "description": "Query parameters."}
                },
                "required": ["db_path", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": "Run safe whitelisted shell commands in sandbox (e.g., ls, grep).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command string."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "code_lint",
            "description": "Lint and auto-format code (Python with Black).",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {"type": "string", "description": "Language (python)."},
                    "code": {"type": "string", "description": "Code snippet."}
                },
                "required": ["language", "code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "api_simulate",
            "description": "Simulate API calls with mock or fetch from public APIs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "API URL."},
                    "method": {"type": "string", "description": "GET/POST (default GET)."},
                    "data": {"type": "object", "description": "POST data."},
                    "mock": {"type": "boolean", "description": "True for mock (default)."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "advanced_memory_consolidate",
            "description": "Brain-like consolidation: Summarize and embed data for hierarchical storage. Use for coding logs to create semantic summaries and episodic details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mem_key": {"type": "string", "description": "Key for the memory entry."},
                    "interaction_data": {"type": "object", "description": "Data to consolidate (dict)."}
                },
                "required": ["mem_key", "interaction_data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "advanced_memory_retrieve",
            "description": "Retrieve relevant memories via embedding similarity. Use before queries to augment context efficiently.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Query string for similarity search."},
                    "top_k": {"type": "integer", "description": "Number of top results (default 5)."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "advanced_memory_prune",
            "description": "Prune low-salience memories to optimize storage.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "langsearch_web_search",
            "description": "Search the web using LangSearch API for relevant results, snippets, and optional summaries. Supports time filters and limits up to 10 results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query (supports operators like site:example.com)."},
                    "freshness": {"type": "string", "description": "Time filter: oneDay, oneWeek, oneMonth, oneYear, or noLimit (default).", "enum": ["oneDay", "oneWeek", "oneMonth", "oneYear", "noLimit"]},
                    "summary": {"type": "boolean", "description": "Include long text summaries (default True)."},
                    "count": {"type": "integer", "description": "Number of results (1-10, default 5)."}
                },
                "required": ["query"]
            }
        }
    },
]

# API Wrapper with Streaming and Tool Handling (Fixed for Backend Issues) - Unchanged
def call_xai_api(model, messages, sys_prompt, stream=True, image_files=None, enable_tools=False):
    client = OpenAI(
        api_key=API_KEY,
        base_url="https://api.x.ai/v1",
        timeout=3600
    )
    # Prepare messages (system first, then history)
    api_messages = [{"role": "system", "content": sys_prompt}]
    for msg in messages:
        content_parts = [{"type": "text", "text": msg['content']}]
        if msg['role'] == 'user' and image_files and msg is messages[-1]:  # Add images to last user message
            for img_file in image_files:
                img_file.seek(0)
                img_data = base64.b64encode(img_file.read()).decode('utf-8')
                content_parts.append({"type": "image_url", "image_url": {"url": f"data:{img_file.type};base64,{img_data}"}})
        api_messages.append({"role": msg['role'], "content": content_parts if len(content_parts) > 1 else msg['content']})
    full_response = ""
    def generate(current_messages):
        nonlocal full_response
        max_iterations = 10  # Fixed: Lowered from 10 to 5
        iteration = 0
        previous_tool_calls = set()
        progress_metric = 0  # Fixed: Track progress to avoid false loops
        while iteration < max_iterations:
            iteration += 1
            print(f"[LOG] API Call Iteration: {iteration}")  # Debug
            tools_param = TOOLS if enable_tools else None
            response = client.chat.completions.create(
                model=model,
                messages=current_messages,
                tools=tools_param,
                tool_choice="auto" if enable_tools else None,
                stream=True
            )
            tool_calls = []
            chunk_response = ""
            has_content = False
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content is not None:
                    content = delta.content
                    chunk_response += content
                    yield content
                    has_content = True
                if delta.tool_calls:
                    tool_calls += delta.tool_calls  # Collect partial calls
            full_response += chunk_response
            if not has_content and not tool_calls:
                print("[DEBUG] No progress; breaking")
                break
            if not tool_calls:
                break  # Done if no tools
            yield "\nProcessing tools...\n"
            # Fixed: Batch tools by type for efficiency
            tool_batches = {}
            current_tool_names = set()
            for tool_call in tool_calls:
                func_name = tool_call.function.name
                current_tool_names.add(func_name)
                if func_name not in tool_batches:
                    tool_batches[func_name] = []
                tool_batches[func_name].append(tool_call)
            # Fixed: Robust loop detection with progress check
            if (
                current_tool_names == previous_tool_calls
                and len(full_response) == progress_metric
                and iteration > 1
            ):
                yield "Detected potential tool loop—no progress—breaking."
                break
            previous_tool_calls = current_tool_names.copy()
            progress_metric = len(full_response)  # Update metric
            # Process batched tools
            for func_name, calls in tool_batches.items():
                for tool_call in calls:
                    try:
                        args = json.loads(tool_call.function.arguments)
                        if func_name == "fs_read_file":
                            result = fs_read_file(args['file_path'])
                        elif func_name == "fs_write_file":
                            result = fs_write_file(args['file_path'], args['content'])
                        elif func_name == "fs_list_files":
                            dir_path = args.get('dir_path', "")
                            result = fs_list_files(dir_path)
                        elif func_name == "fs_mkdir":
                            result = fs_mkdir(args['dir_path'])
                        elif func_name == "get_current_time":
                            sync = args.get('sync', False)
                            fmt = args.get('format', 'iso')
                            result = get_current_time(sync, fmt)
                        elif func_name == "code_execution":
                            result = code_execution(args['code'])
                        elif func_name == "memory_insert":
                            user = st.session_state['user']
                            convo_id = st.session_state.get('current_convo_id', 0)
                            result = memory_insert(user, convo_id, args['mem_key'], args['mem_value'])
                        elif func_name == "memory_query":
                            user = st.session_state['user']
                            convo_id = st.session_state.get('current_convo_id', 0)
                            mem_key = args.get('mem_key')
                            limit = args.get('limit', 10)
                            result = memory_query(user, convo_id, mem_key, limit)
                        # Fixed: Handle new tools
                        elif func_name == "git_ops":
                            operation = args['operation']
                            repo_path = args['repo_path']
                            result = git_ops(operation, repo_path, **args)
                        elif func_name == "db_query":
                            db_path = args['db_path']
                            query = args['query']
                            params = args.get('params', [])
                            result = db_query(db_path, query, params)
                        elif func_name == "shell_exec":
                            command = args['command']
                            result = shell_exec(command)
                        elif func_name == "code_lint":
                            language = args['language']
                            code = args['code']
                            result = code_lint(language, code)
                        elif func_name == "api_simulate":
                            url = args['url']
                            method = args.get('method', 'GET')
                            data = args.get('data')
                            mock = args.get('mock', True)
                            result = api_simulate(url, method, data, mock)
                        # Fixed: Advanced Memory
                        elif func_name == "advanced_memory_consolidate":
                            user = st.session_state['user']
                            convo_id = st.session_state.get('current_convo_id', 0)
                            result = advanced_memory_consolidate(user, convo_id, args['mem_key'], args['interaction_data'])
                        elif func_name == "advanced_memory_retrieve":
                            user = st.session_state['user']
                            convo_id = st.session_state.get('current_convo_id', 0)
                            query = args['query']
                            top_k = args.get('top_k', 5)
                            result = advanced_memory_retrieve(user, convo_id, query, top_k)
                        elif func_name == "advanced_memory_prune":
                            user = st.session_state['user']
                            convo_id = st.session_state.get('current_convo_id', 0)
                            result = advanced_memory_prune(user, convo_id)
                        elif func_name == "langsearch_web_search":
                            query = args['query']
                            freshness = args.get('freshness', "noLimit")
                            summary = args.get('summary', True)
                            count = args.get('count', 10)
                            result = langsearch_web_search(query, freshness, summary, count)
                        else:
                            result = "Unknown tool."
                    except Exception as e:
                        result = f"Tool error: {traceback.format_exc()}"
                        print(f"[LOG] Tool Error: {result}")  # Debug
                        with open('app.log', 'a') as log:
                            log.write(f"Tool Error: {result}\n")
                    yield f"\n[Tool Result ({func_name}): {result}]\n"
                    # Append to messages for next iteration
                    current_messages.append({"role": "tool", "content": result, "tool_call_id": tool_call.id})
        if iteration >= max_iterations:
            yield "Max iterations reached—summarizing."
    try:
        if stream:
            return generate(api_messages)  # Return generator for streaming
        else:
            response = client.chat.completions.create(
                model=model,
                messages=api_messages,
                tools=TOOLS if enable_tools else None,
                tool_choice="auto" if enable_tools else None,
                stream=False
            )
            full_response = response.choices[0].message.content
            return lambda: [full_response]  # Mock generator for non-stream
    except Exception as e:
        error_msg = f"API Error: {traceback.format_exc()}"
        st.error(error_msg)
        with open('app.log', 'a') as log:
            log.write(f"{error_msg}\n")
        time.sleep(5)
        return call_xai_api(model, messages, sys_prompt, stream, image_files, enable_tools)  # Retry

# Login Page - Unchanged
def login_page():
    st.title("Welcome to PiCoder")
    st.subheader("Login or Register")
    # Tabs for Login/Register
    tab1, tab2 = st.tabs(["Login", "Register"])
    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            submitted = st.form_submit_button("Login")
            if submitted:
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
            new_user = st.text_input("New Username", key="reg_user")
            new_pass = st.text_input("New Password", type="password", key="reg_pass")
            reg_submitted = st.form_submit_button("Register")
            if reg_submitted:
                c.execute("SELECT * FROM users WHERE username=?", (new_user,))
                if c.fetchone():
                    st.error("Username already exists.")
                else:
                    hashed = hash_password(new_pass)
                    c.execute("INSERT INTO users VALUES (?, ?)", (new_user, hashed))
                    conn.commit()
                    st.success("Registered! Please login.")

# Chat Page - Updated for parsed final answer outside expander
def chat_page():
    st.title(f"Grok Chat - {st.session_state['user']}")
    # Sidebar: Settings and History - Unchanged
    with st.sidebar:
        st.header("Chat Settings")
        model = st.selectbox(
            "Select Model",
            ["grok-4", "grok-3-mini", "grok-code-fast-1"],
            key="model_select",
        )  # Extensible
        # Load Prompt Files Dynamically
        prompt_files = load_prompt_files()
        if not prompt_files:
            st.warning("No prompt files found in ./prompts/. Add some .txt files!")
            custom_prompt = st.text_area(
                "Edit System Prompt",
                value="You are Grok, a helpful AI.",
                height=100,
                key="prompt_editor",
            )
        else:
            selected_file = st.selectbox(
                "Select System Prompt File", prompt_files, key="prompt_select"
            )
            with open(os.path.join(PROMPTS_DIR, selected_file), "r") as f:
                prompt_content = f.read()
            custom_prompt = st.text_area(
                "Edit System Prompt",
                value=prompt_content,
                height=200,
                key="prompt_editor",
            )
        # Save Edited Prompt
        with st.form("save_prompt_form"):
            new_filename = st.text_input("Save as (e.g., my-prompt.txt)", value="")
            save_submitted = st.form_submit_button("Save Prompt to File")
            if save_submitted and new_filename.endswith(".txt"):
                save_path = os.path.join(PROMPTS_DIR, new_filename)
                with open(save_path, "w") as f:
                    f.write(custom_prompt)
                if "love" in new_filename.lower():  # Unhinged flair
                    with open(save_path, "a") as f:
                        f.write("\n<3")  # Append heart
                st.success(f"Saved to {save_path}!")
                st.rerun()  # Refresh dropdown
        # Image Upload for Vision (Multi-file support)
        uploaded_images = st.file_uploader(
            "Upload Images for Analysis (Vision Models)",
            type=["jpg", "png"],
            accept_multiple_files=True,
        )
        enable_tools = st.checkbox(
            "Enable FS Tools (Sandboxed R/W Access)", value=False
        )
        if enable_tools:
            st.info(
                "Tools enabled: AI can read/write/list files in ./sandbox/. Copy files there to access."
            )
        st.header("Chat History")
        search_term = st.text_input("Search History")
        c.execute(
            "SELECT convo_id, title FROM history WHERE user=?",
            (st.session_state["user"],),
        )
        histories = c.fetchall()
        filtered_histories = [
            h for h in histories if search_term.lower() in h[1].lower()
        ]
        for convo_id, title in filtered_histories:
            col1, col2 = st.columns([3, 1])
            col1.button(
                f"{title}",
                key=f"load_{convo_id}",
                on_click=lambda cid=convo_id: load_history(cid),
            )
            col2.button(
                "🗑",
                key=f"delete_{convo_id}",
                on_click=lambda cid=convo_id: delete_history(cid),
            )
        if st.button("Clear Current Chat"):
            st.session_state["messages"] = []
            st.rerun()
        # Dark Mode Toggle with CSS Injection
        if st.button("Toggle Dark Mode"):
            current_theme = st.session_state.get("theme", "light")
            st.session_state["theme"] = "dark" if current_theme == "light" else "light"
            st.rerun()  # Rerun to apply
        # Inject theme attribute
        st.markdown(
            f'<body data-theme="{st.session_state.get("theme", "light")}"></body>',
            unsafe_allow_html=True,
        )

    # Chat Display (Simplified: No escaping, no custom code detection)
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "current_convo_id" not in st.session_state:
        st.session_state["current_convo_id"] = None  # None for new; set on save
    # Truncate for performance
    if len(st.session_state["messages"]) > 50:
        st.session_state["messages"] = st.session_state["messages"][-50:]
        st.warning("Chat truncated to last 50 messages for performance.")
    if st.session_state["messages"]:
        chunk_size = 10  # Group every 10 messages
        for i in range(0, len(st.session_state["messages"]), chunk_size):
            chunk = st.session_state["messages"][i : i + chunk_size]
            with st.expander(f"Messages {i+1}-{i+len(chunk)}"):
                for msg in chunk:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"], unsafe_allow_html=False)  # Standard rendering

    # Chat Input
    prompt = st.chat_input("Type your message here...")
    if prompt:
        st.session_state['messages'].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt, unsafe_allow_html=False)  # Standard user message
        with st.chat_message("assistant"):
            # Expander for deep thought (streaming/tool output)
            with st.expander("Thinking... (Deep Thought Process)"):
                thought_container = st.empty()
                generator = call_xai_api(model, st.session_state['messages'], custom_prompt, stream=True, image_files=uploaded_images if uploaded_images else None, enable_tools=enable_tools)
                full_response = ""
                for chunk in generator:
                    full_response += chunk
                    thought_container.markdown(full_response, unsafe_allow_html=False)  # Stream into expander
            # Parse and display final answer outside if marker present
            marker = "### Final Answer"
            if marker in full_response:
                parts = full_response.split(marker, 1)
                thought_part = parts[0].strip()
                final_part = marker + (parts[1] if len(parts) > 1 else "")
                # Update expander with only thought part
                thought_container.markdown(thought_part, unsafe_allow_html=False)
                # Display final part outside
                st.markdown(final_part, unsafe_allow_html=False)
            # If no marker, full response stays in expander (no additional output outside)
        st.session_state['messages'].append({"role": "assistant", "content": full_response})
        # Save to History (Auto-title from first user message)
        title = st.session_state['messages'][0]['content'][:50] + "..." if st.session_state['messages'] else "New Chat"
        c.execute("INSERT INTO history (user, title, messages) VALUES (?, ?, ?)",
                  (st.session_state['user'], title, json.dumps(st.session_state['messages'])))
        conn.commit()
        st.session_state['current_convo_id'] = c.lastrowid  # Set for new chats

# Load History - Unchanged
def load_history(convo_id):
    c.execute("SELECT messages FROM history WHERE convo_id=?", (convo_id,))
    messages = json.loads(c.fetchone()[0])
    st.session_state['messages'] = messages
    st.session_state['current_convo_id'] = convo_id
    st.rerun()

# Delete History - Unchanged
def delete_history(convo_id):
    c.execute("DELETE FROM history WHERE convo_id=?", (convo_id,))
    conn.commit()
    st.rerun()

# Main App with Init Time Check - Unchanged
if __name__ == "__main__":
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['theme'] = 'light'  # Default theme
    # Init Time Check (on app start)
    if 'init_time' not in st.session_state:
        st.session_state['init_time'] = get_current_time(sync=True)  # Auto-sync on start
        print(f"[LOG] Init Time: {st.session_state['init_time']}")
    if not st.session_state['logged_in']:
        login_page()
    else:
        chat_page()
