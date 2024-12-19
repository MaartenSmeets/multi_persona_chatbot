import sqlite3
import datetime
from typing import List, Dict, Optional

class DBManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_db_structure()

    def _ensure_column_exists(self, conn, table: str, column: str, col_type: str):
        c = conn.cursor()
        c.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in c.fetchall()]
        if column not in columns:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            conn.commit()
    def _ensure_connection(self):
        return sqlite3.connect(self.db_path)
    
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
            message_type TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
        """)

        # Ensure affect column exists
        self._ensure_column_exists(conn, "messages", "affect", "TEXT")
        # Ensure purpose column exists
        self._ensure_column_exists(conn, "messages", "purpose", "TEXT")

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

        # Ensure summary_index column for multiple summaries
        self._ensure_column_exists(conn, "summaries", "summary_index", "INTEGER DEFAULT 0")
        # Ensure covered_up_to_message_id column to track which messages are summarized
        self._ensure_column_exists(conn, "summaries", "covered_up_to_message_id", "INTEGER DEFAULT 0")

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

    def save_message(self, session_id: str, sender: str, message: str, visible: bool, message_type: str, affect: Optional[str] = None, purpose: Optional[str]=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO messages (session_id, sender, message, timestamp, visible, message_type, affect, purpose) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, sender, message, datetime.datetime.utcnow().isoformat(), 1 if visible else 0, message_type, affect, purpose))
        conn.commit()
        conn.close()

    def get_messages(self, session_id: str) -> List[Dict[str, any]]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT id, sender, message, timestamp, visible, message_type, affect, purpose FROM messages 
            WHERE session_id=? ORDER BY id ASC
        """, (session_id,))
        rows = c.fetchall()
        conn.close()
        messages = []
        for r in rows:
            messages.append({
                "id": r[0],
                "sender": r[1],
                "message": r[2],
                "timestamp": r[3],
                "visible": bool(r[4]),
                "message_type": r[5],
                "affect": r[6],
                "purpose": r[7]
            })
        return messages

    def save_new_summary(self, session_id: str, character_name: str, summary: str, covered_up_to_message_id: int):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT MAX(summary_index) FROM summaries WHERE session_id=? AND character_name=?
        """, (session_id, character_name))
        row = c.fetchone()
        next_index = (row[0] + 1) if row[0] is not None else 0

        c.execute("""
            INSERT INTO summaries (session_id, character_name, summary, last_updated, summary_index, covered_up_to_message_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, character_name, summary, datetime.datetime.utcnow().isoformat(), next_index, covered_up_to_message_id))

        conn.commit()
        conn.close()

    def get_all_summaries(self, session_id: str, character_name: str) -> List[str]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT summary FROM summaries 
            WHERE session_id=? AND character_name=?
            ORDER BY summary_index ASC
        """, (session_id, character_name))
        rows = c.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def get_latest_covered_message_id(self, session_id: str, character_name: str) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT MAX(covered_up_to_message_id) FROM summaries 
            WHERE session_id=? AND character_name=?
        """, (session_id, character_name))
        row = c.fetchone()
        conn.close()
        return row[0] if row[0] is not None else 0
