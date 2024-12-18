# File: src/multipersona_chat_app/db/db_manager.py
import sqlite3
import os
import datetime
from typing import List, Dict, Optional

class DBManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_db_structure()

    def _ensure_db_structure(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # sessions table
        c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        # messages table
        c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            visible INTEGER NOT NULL,
            message_type TEXT NOT NULL, -- 'user', 'character', 'system'
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
        """)
        # summaries table
        c.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            character_name TEXT NOT NULL,
            summary TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
        """)
        conn.commit()
        conn.close()

    def create_session(self, session_id: str, name: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT INTO sessions (session_id, name, created_at) VALUES (?, ?, ?)",
                  (session_id, name, datetime.datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()

    def delete_session(self, session_id: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        c.execute("DELETE FROM summaries WHERE session_id=?", (session_id,))
        c.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        conn.commit()
        conn.close()

    def get_all_sessions(self) -> List[Dict[str, str]]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT session_id, name, created_at FROM sessions ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        sessions = [{"session_id": r[0], "name": r[1], "created_at": r[2]} for r in rows]
        return sessions

    def save_message(self, session_id: str, sender: str, message: str, visible: bool, message_type: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO messages (session_id, sender, message, timestamp, visible, message_type) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, sender, message, datetime.datetime.utcnow().isoformat(), 1 if visible else 0, message_type))
        conn.commit()
        conn.close()

    def get_messages(self, session_id: str) -> List[Dict[str, any]]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT sender, message, timestamp, visible, message_type FROM messages 
            WHERE session_id=? ORDER BY id ASC
        """, (session_id,))
        rows = c.fetchall()
        conn.close()
        messages = []
        for r in rows:
            messages.append({
                "sender": r[0],
                "message": r[1],
                "timestamp": r[2],
                "visible": bool(r[3]),
                "message_type": r[4]
            })
        return messages

    def save_summary(self, session_id: str, character_name: str, summary: str):
        # Upsert logic: if exists, update, else insert
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT id FROM summaries WHERE session_id=? AND character_name=?
        """, (session_id, character_name))
        row = c.fetchone()
        if row:
            c.execute("""
                UPDATE summaries
                SET summary=?, last_updated=?
                WHERE id=?
            """, (summary, datetime.datetime.utcnow().isoformat(), row[0]))
        else:
            c.execute("""
                INSERT INTO summaries (session_id, character_name, summary, last_updated)
                VALUES (?, ?, ?, ?)
            """, (session_id, character_name, summary, datetime.datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()

    def get_summary(self, session_id: str, character_name: str) -> str:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT summary FROM summaries WHERE session_id=? AND character_name=?
        """, (session_id, character_name))
        row = c.fetchone()
        conn.close()
        if row:
            return row[0]
        return ""
