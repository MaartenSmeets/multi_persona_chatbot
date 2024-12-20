# File: /home/maarten/multi_persona_chatbot/src/multipersona_chatbot/src/multipersona_chat_app/db/db_manager.py

import sqlite3
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class DBManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initialize_database()

    def _initialize_database(self):
        """Initialize the database and create necessary tables if they don't exist."""
        conn = self._ensure_connection()
        c = conn.cursor()
        # Create sessions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                current_setting TEXT,
                current_location TEXT
            )
        ''')
        # Create messages table
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                visible INTEGER DEFAULT 1,
                message_type TEXT DEFAULT 'user',
                affect TEXT,
                purpose TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        ''')
        # Create summaries table
        c.execute('''
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                character_name TEXT NOT NULL,
                summary TEXT NOT NULL,
                covered_up_to_message_id INTEGER,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        ''')
        # Create location_history table
        c.execute('''
            CREATE TABLE IF NOT EXISTS location_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                location TEXT NOT NULL,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                triggered_by_message_id INTEGER,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                FOREIGN KEY(triggered_by_message_id) REFERENCES messages(id)
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully with all required tables.")

    def _ensure_connection(self) -> sqlite3.Connection:
        """Ensure that a connection to the database is established."""
        return sqlite3.connect(self.db_path)

    # Session Management Methods
    def create_session(self, session_id: str, name: str):
        """Create a new session."""
        conn = self._ensure_connection()
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO sessions (session_id, name)
                VALUES (?, ?)
            ''', (session_id, name))
            conn.commit()
            logger.info(f"Session '{name}' with ID '{session_id}' created.")
        except sqlite3.IntegrityError:
            logger.error(f"Session with ID '{session_id}' already exists.")
        finally:
            conn.close()

    def delete_session(self, session_id: str):
        """Delete an existing session along with its messages, summaries, and location history."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('DELETE FROM summaries WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM location_history WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()
        logger.info(f"Session with ID '{session_id}' and all associated data deleted.")

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Retrieve all sessions."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('SELECT session_id, name FROM sessions')
        rows = c.fetchall()
        sessions = [{'session_id': row[0], 'name': row[1]} for row in rows]
        conn.close()
        logger.debug(f"Retrieved {len(sessions)} sessions.")
        return sessions

    def get_current_setting(self, session_id: str) -> Optional[str]:
        """Retrieve the current setting of a session."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('SELECT current_setting FROM sessions WHERE session_id = ?', (session_id,))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            logger.debug(f"Current setting for session '{session_id}': {row[0]}")
            return row[0]
        logger.warning(f"No current setting found for session '{session_id}'.")
        return None

    def update_current_setting(self, session_id: str, setting_name: str):
        """Update the current setting of a session."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('UPDATE sessions SET current_setting = ? WHERE session_id = ?', (setting_name, session_id))
        conn.commit()
        conn.close()
        logger.info(f"Session '{session_id}' updated with new setting '{setting_name}'.")

    def get_current_location(self, session_id: str) -> Optional[str]:
        """Retrieve the current location of a session."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('SELECT current_location FROM sessions WHERE session_id = ?', (session_id,))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            logger.debug(f"Current location for session '{session_id}': {row[0]}")
            return row[0]
        logger.warning(f"No current location found for session '{session_id}'.")
        return None

    def update_current_location(self, session_id: str, location: str, triggered_by_message_id: Optional[int] = None):
        """Update the current location of a session and log the change in location_history."""
        conn = self._ensure_connection()
        c = conn.cursor()
        # Update current_location in sessions table
        c.execute('''
            UPDATE sessions
            SET current_location = ?
            WHERE session_id = ?
        ''', (location, session_id))
        # Insert into location_history table
        c.execute('''
            INSERT INTO location_history (session_id, location, triggered_by_message_id)
            VALUES (?, ?, ?)
        ''', (session_id, location, triggered_by_message_id))
        conn.commit()
        conn.close()
        if triggered_by_message_id:
            logger.info(f"Session '{session_id}' location updated to '{location}' by message ID {triggered_by_message_id}.")
        else:
            logger.info(f"Session '{session_id}' location updated to '{location}'.")

    def get_location_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve the location history of a session."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT location, changed_at, triggered_by_message_id
            FROM location_history
            WHERE session_id = ?
            ORDER BY changed_at ASC
        ''', (session_id,))
        rows = c.fetchall()
        history = []
        for row in rows:
            history.append({
                'location': row[0],
                'changed_at': row[1],
                'triggered_by_message_id': row[2]
            })
        conn.close()
        logger.debug(f"Retrieved {len(history)} location history entries for session '{session_id}'.")
        return history

    # Message Management Methods
    def save_message(self, session_id: str, sender: str, message: str, visible: bool = True, message_type: str = "user", affect: Optional[str]=None, purpose: Optional[str]=None) -> int:
        """Save a new message to the database."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO messages (session_id, sender, message, visible, message_type, affect, purpose)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (session_id, sender, message, int(visible), message_type, affect, purpose))
        message_id = c.lastrowid
        conn.commit()
        conn.close()
        logger.debug(f"Message saved with ID {message_id} for session '{session_id}'.")
        return message_id

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve all messages for a given session."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT id, sender, message, visible, message_type, affect, purpose
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
        ''', (session_id,))
        rows = c.fetchall()
        messages = []
        for row in rows:
            messages.append({
                'id': row[0],
                'sender': row[1],
                'message': row[2],
                'visible': bool(row[3]),
                'message_type': row[4],
                'affect': row[5],
                'purpose': row[6]
            })
        conn.close()
        logger.debug(f"Retrieved {len(messages)} messages for session '{session_id}'.")
        return messages

    # Summaries Management Methods
    def save_new_summary(self, session_id: str, character_name: str, summary: str, covered_up_to_message_id: int):
        """Save a new summary for a character in a session."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO summaries (session_id, character_name, summary, covered_up_to_message_id)
            VALUES (?, ?, ?, ?)
        ''', (session_id, character_name, summary, covered_up_to_message_id))
        conn.commit()
        conn.close()
        logger.debug(f"Summary saved for character '{character_name}' in session '{session_id}' up to message ID {covered_up_to_message_id}.")

    def get_all_summaries(self, session_id: str, character_name: str) -> List[str]:
        """Retrieve all summaries for a character in a session."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT summary FROM summaries
            WHERE session_id = ? AND character_name = ?
            ORDER BY id ASC
        ''', (session_id, character_name))
        rows = c.fetchall()
        summaries = [row[0] for row in rows]
        conn.close()
        logger.debug(f"Retrieved {len(summaries)} summaries for character '{character_name}' in session '{session_id}'.")
        return summaries

    def get_latest_covered_message_id(self, session_id: str, character_name: str) -> int:
        """Retrieve the latest covered message ID for a character in a session."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT covered_up_to_message_id FROM summaries
            WHERE session_id = ? AND character_name = ?
            ORDER BY covered_up_to_message_id DESC
            LIMIT 1
        ''', (session_id, character_name))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            logger.debug(f"Latest covered message ID for character '{character_name}' in session '{session_id}': {row[0]}")
            return row[0]
        logger.debug(f"No summaries found for character '{character_name}' in session '{session_id}'. Starting from ID 0.")
        return 0
