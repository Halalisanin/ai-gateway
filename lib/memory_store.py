#!/usr/bin/env python3
import sqlite3
import json

DB_PATH = "/home/liviyo/.agent_memory.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                agent_name TEXT,
                role TEXT,
                content TEXT,
                model TEXT,
                tokens_used INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session_time ON messages(session_id, timestamp)")

def add_message(session_id, agent_name, role, content, model=None, tokens_used=None, metadata=None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO messages (session_id, agent_name, role, content, model, tokens_used, metadata) VALUES (?,?,?,?,?,?,?)",
            (session_id, agent_name, role, content, model, tokens_used, json.dumps(metadata) if metadata else None)
        )

def get_recent_context(session_id, n=10):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?", (session_id, n))
        rows = cur.fetchall()
        return list(reversed(rows))

def get_full_history(session_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT role, content, agent_name, timestamp FROM messages WHERE session_id = ? ORDER BY timestamp ASC", (session_id,)).fetchall()

def clear_session(session_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
