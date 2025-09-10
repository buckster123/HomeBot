# db.py
# Handles all database-related operations, including setup, queries, and memory management.

import sqlite3
import os
import json
from datetime import datetime, timedelta
import numpy as np
from sentence_transformers import SentenceTransformer
import streamlit as st

def init_db():
    conn = sqlite3.connect('chatapp.db', check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.enable_load_extension(True)
    vec_path = os.path.join(os.path.dirname(__file__), 'sqlite-vec/dist/vec0.so')
    conn.load_extension(vec_path)
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
    # History table
    c.execute('''CREATE TABLE IF NOT EXISTS history (user TEXT, convo_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, messages TEXT)''')
    # Memory table
    c.execute('''CREATE TABLE IF NOT EXISTS memory (
        user TEXT,
        convo_id INTEGER,
        mem_key TEXT,
        mem_value TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        embedding BLOB,
        salience REAL DEFAULT 1.0,
        parent_id INTEGER,
        PRIMARY KEY (user, convo_id, mem_key)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_memory_user_convo ON memory (user, convo_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_memory_timestamp ON memory (timestamp)')
    conn.commit()
    return conn

def get_cursor(conn):
    return conn.cursor()

# Memory Functions (Basic)
def memory_insert(conn, user: str, convo_id: int, mem_key: str, mem_value: dict) -> str:
    try:
        json_value = json.dumps(mem_value)
        c = get_cursor(conn)
        c.execute("INSERT OR REPLACE INTO memory (user, convo_id, mem_key, mem_value) VALUES (?, ?, ?, ?)",
                  (user, convo_id, mem_key, json_value))
        conn.commit()
        # Update cache
        if 'memory_cache' not in st.session_state:
            st.session_state['memory_cache'] = {}
        cache_key = f"{user}:{convo_id}:{mem_key}"
        st.session_state['memory_cache'][cache_key] = mem_value
        return "Memory inserted successfully."
    except Exception as e:
        return f"Error inserting memory: {str(e)}"

def memory_query(conn, user: str, convo_id: int, mem_key: str = None, limit: int = 10) -> str:
    try:
        if 'memory_cache' not in st.session_state:
            st.session_state['memory_cache'] = {}
        c = get_cursor(conn)
        if mem_key:
            cache_key = f"{user}:{convo_id}:{mem_key}"
            cached = st.session_state['memory_cache'].get(cache_key)
            if cached:
                return json.dumps(cached)
            c.execute("SELECT mem_value FROM memory WHERE user=? AND convo_id=? AND mem_key=? ORDER BY timestamp DESC LIMIT 1",
                      (user, convo_id, mem_key))
            result = c.fetchone()
            if result:
                value = json.loads(result[0])
                st.session_state['memory_cache'][cache_key] = value
                return json.dumps(value)
            return "Not found."
        else:
            c.execute("SELECT mem_key, mem_value FROM memory WHERE user=? AND convo_id=? ORDER BY timestamp DESC LIMIT ?",
                      (user, convo_id, limit))
            results = c.fetchall()
            output = {row[0]: json.loads(row[1]) for row in results}
            for k, v in output.items():
                st.session_state['memory_cache'][f"{user}:{convo_id}:{k}"] = v
            return json.dumps(output)
    except Exception as e:
        return f"Error querying memory: {str(e)}"

# Advanced Memory Functions
def get_embed_model():
    if 'embed_model' not in st.session_state:
        st.session_state['embed_model'] = SentenceTransformer('all-MiniLM-L6-v2')
    return st.session_state['embed_model']

def advanced_memory_consolidate(conn, user: str, convo_id: int, mem_key: str, interaction_data: dict) -> str:
    from api import call_xai_api  # Lazy import to avoid circular deps
    try:
        # Summarize using Grok
        summary_response = call_xai_api(
            model="grok-code-fast-1",
            messages=[{"role": "user", "content": json.dumps(interaction_data)}],
            sys_prompt="Summarize this in max 3 sentences:",
            stream=False
        )
        summary = next(summary_response()).strip()  # Since non-stream, it's a mock generator
        # Embed
        embed_model = get_embed_model()
        embedding = embed_model.encode(json.dumps(interaction_data)).astype(np.float32).tobytes()
        # Store semantic parent
        semantic_value = {"summary": summary}
        json_semantic = json.dumps(semantic_value)
        salience = 1.0
        c = get_cursor(conn)
        c.execute("INSERT OR REPLACE INTO memory (user, convo_id, mem_key, mem_value, salience, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                  (user, convo_id, f"{mem_key}_semantic", json_semantic, salience, datetime.now()))
        parent_id = c.lastrowid
        # Store episodic child
        json_episodic = json.dumps(interaction_data)
        c.execute("INSERT OR REPLACE INTO memory (user, convo_id, mem_key, mem_value, embedding, parent_id, salience, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (user, convo_id, mem_key, json_episodic, embedding, parent_id, salience, datetime.now()))
        conn.commit()
        return "Memory consolidated successfully."
    except Exception as e:
        return f"Error consolidating memory: {str(e)}"

def advanced_memory_retrieve(conn, user: str, convo_id: int, query: str, top_k: int = 5) -> str:
    try:
        embed_model = get_embed_model()
        query_embed = embed_model.encode(query).astype(np.float32)
        query_embed_bytes = query_embed.tobytes()
        c = get_cursor(conn)
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
            sim = 1 - distance
            if parent_id:
                c.execute("UPDATE memory SET salience = salience + 0.1 WHERE rowid = ?", (parent_id,))
            c.execute("UPDATE memory SET salience = salience + 0.1 WHERE user = ? AND convo_id = ? AND mem_key = ?",
                      (user, convo_id, mem_key))
            retrieved.append({"mem_key": mem_key, "value": value, "relevance": float(sim)})
        conn.commit()
        return json.dumps(retrieved)
    except Exception as e:
        return f"Error retrieving memory: {str(e)}"

def advanced_memory_prune(conn, user: str, convo_id: int) -> str:
    try:
        decay_factor = 0.99
        one_week_ago = datetime.now() - timedelta(days=7)
        c = get_cursor(conn)
        c.execute("UPDATE memory SET salience = salience * ? WHERE user=? AND convo_id=? AND timestamp < ?",
                  (decay_factor, user, convo_id, one_week_ago))
        c.execute("DELETE FROM memory WHERE user=? AND convo_id=? AND salience < 0.1",
                  (user, convo_id))
        conn.commit()
        return "Memory pruned successfully."
    except Exception as e:
        return f"Error pruning memory: {str(e)}"
