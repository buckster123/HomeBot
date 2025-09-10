# tools.py
# Defines all tool functions and schemas. Optimized for sandboxing and efficiency.

import os
import json
import time
import io
import sys
import traceback
import ntplib
import pygit2
import subprocess
import requests
from black import format_str, FileMode
from passlib.hash import sha256_crypt
from db import memory_insert, memory_query, advanced_memory_consolidate, advanced_memory_retrieve, advanced_memory_prune
import streamlit as st

SANDBOX_DIR = "./sandbox"
os.makedirs(SANDBOX_DIR, exist_ok=True)

WHITELISTED_COMMANDS = ['ls', 'grep', 'sed', 'cat', 'echo', 'pwd']
API_WHITELIST = ['https://jsonplaceholder.typicode.com/', 'https://api.openweathermap.org/']

def hash_password(password):
    return sha256_crypt.hash(password)

def verify_password(stored, provided):
    return sha256_crypt.verify(provided, stored)

# FS Tools
def fs_read_file(file_path: str) -> str:
    safe_path = os.path.normpath(os.path.join(SANDBOX_DIR, file_path))
    if not safe_path.startswith(os.path.abspath(SANDBOX_DIR)) or not os.path.exists(safe_path) or os.path.isdir(safe_path):
        return "Invalid file path or not a file."
    try:
        with open(safe_path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def fs_write_file(file_path: str, content: str) -> str:
    safe_path = os.path.normpath(os.path.join(SANDBOX_DIR, file_path))
    if not safe_path.startswith(os.path.abspath(SANDBOX_DIR)):
        return "Invalid file path."
    dir_path = os.path.dirname(safe_path)
    if not os.path.exists(dir_path):
        return "Parent directory does not exist."
    try:
        with open(safe_path, 'w') as f:
            f.write(content)
        return f"File written successfully: {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

def fs_list_files(dir_path: str = "") -> str:
    safe_dir = os.path.normpath(os.path.join(SANDBOX_DIR, dir_path))
    if not safe_dir.startswith(os.path.abspath(SANDBOX_DIR)) or not os.path.exists(safe_dir) or not os.path.isdir(safe_dir):
        return "Invalid directory path."
    try:
        files = os.listdir(safe_dir)
        return f"Files in {dir_path or 'root'}: {', '.join(files)}" if files else "No files."
    except Exception as e:
        return f"Error listing files: {str(e)}"

def fs_mkdir(dir_path: str) -> str:
    safe_path = os.path.normpath(os.path.join(SANDBOX_DIR, dir_path))
    if not safe_path.startswith(os.path.abspath(SANDBOX_DIR)) or os.path.exists(safe_path):
        return "Invalid directory path or already exists."
    try:
        os.makedirs(safe_path)
        return f"Directory created: {dir_path}"
    except Exception as e:
        return f"Error creating directory: {str(e)}"

# Time Tool
def get_current_time(sync: bool = False, format: str = 'iso') -> str:
    try:
        if sync:
            c = ntplib.NTPClient()
            response = c.request('pool.ntp.org', version=3)
            t = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(response.tx_time))
            source = "NTP"
        else:
            t = time.strftime('%Y-%m-%d %H:%M:%S')
            source = "host"
        if format == 'json':
            return json.dumps({"timestamp": t, "source": source, "timezone": "local"})
        elif format == 'human':
            return f"Current time: {t} ({source}) - LOVE <3"
        return t
    except Exception as e:
        return f"Time error: {str(e)}"

# Code Execution
def code_execution(code: str) -> str:
    if 'repl_namespace' not in st.session_state:
        st.session_state['repl_namespace'] = {'__builtins__': __builtins__}
    namespace = st.session_state['repl_namespace']
    old_stdout = sys.stdout
    redirected_output = io.StringIO()
    sys.stdout = redirected_output
    try:
        exec(code, namespace)
        output = redirected_output.getvalue()
        return f"Execution successful. Output:\n{output}" if output else "Execution successful."
    except Exception as e:
        return f"Error: {str(e)}\n{traceback.format_exc()}"
    finally:
        sys.stdout = old_stdout

# Git Tool
def git_ops(operation: str, repo_path: str = "", **kwargs) -> str:
    safe_repo = os.path.normpath(os.path.join(SANDBOX_DIR, repo_path))
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
            repo.create_commit('HEAD', author, author, message, tree, [repo.head.target] if not repo.head_is_unborn else [])
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
        return "Unsupported operation."
    except Exception as e:
        return f"Git error: {str(e)}"

# DB Query Tool
def db_query(db_path: str, query: str, params: list = []) -> str:
    safe_db = os.path.normpath(os.path.join(SANDBOX_DIR, db_path))
    if not safe_db.startswith(os.path.abspath(SANDBOX_DIR)):
        return "Invalid DB path."
    db_conn = sqlite3.connect(safe_db)
    try:
        cur = db_conn.cursor()
        cur.execute(query, params)
        if query.strip().upper().startswith('SELECT'):
            return json.dumps(cur.fetchall())
        db_conn.commit()
        return f"Query executed, {cur.rowcount} rows affected."
    except Exception as e:
        return f"DB error: {str(e)}"
    finally:
        db_conn.close()

# Shell Tool
def shell_exec(command: str) -> str:
    cmd_parts = command.split()
    if not cmd_parts or cmd_parts[0] not in WHITELISTED_COMMANDS:
        return "Command not whitelisted."
    try:
        result = subprocess.run(command, shell=True, cwd=SANDBOX_DIR, capture_output=True, text=True, timeout=5)
        return result.stdout.strip() + ("\nError: " + result.stderr.strip() if result.stderr else "")
    except Exception as e:
        return f"Shell error: {str(e)}"

# Code Lint
def code_lint(language: str, code: str) -> str:
    if language.lower() != 'python':
        return "Only Python supported."
    try:
        return format_str(code, mode=FileMode(line_length=88))
    except Exception as e:
        return f"Lint error: {str(e)}"

# API Simulate
def api_simulate(url: str, method: str = 'GET', data: dict = None, mock: bool = True) -> str:
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

# Web Search (LangSearch)
def langsearch_web_search(query: str, freshness: str = "noLimit", summary: bool = True, count: int = 10) -> str:
    global LANGSEARCH_API_KEY
    if not LANGSEARCH_API_KEY:
        return "LangSearch API key not set."
    url = "https://api.langsearch.com/v1/web-search"
    payload = json.dumps({"query": query, "freshness": freshness, "summary": summary, "count": count})
    headers = {'Authorization': f'Bearer {LANGSEARCH_API_KEY}', 'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        response.raise_for_status()
        return json.dumps(response.json())
    except Exception as e:
        return f"LangSearch error: {str(e)}"

# Tool Schemas (unchanged, but centralized)
TOOLS = [
    # ... (omit for brevity; same as original TOOLS list, but reference functions above)
    # Note: In practice, update "function" dicts to match function names.
]
