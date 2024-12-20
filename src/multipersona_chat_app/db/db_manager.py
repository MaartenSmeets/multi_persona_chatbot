import sqlite3
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class DBManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initialize_database()

    def _initialize_database(self):
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
        # Create session_characters table
        c.execute('''
            CREATE TABLE IF NOT EXISTS session_characters (
                session_id TEXT NOT NULL,
                character_name TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully with all required tables.")

    def _ensure_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # Session Management
    def create_session(self, session_id: str, name: str):
        conn = self._ensure_connection()
        c = conn.cursor()
        try:
            c.execute('INSERT INTO sessions (session_id, name) VALUES (?, ?)', (session_id, name))
            conn.commit()
            logger.info(f"Session '{name}' with ID '{session_id}' created.")
        except sqlite3.IntegrityError:
            logger.error(f"Session with ID '{session_id}' already exists.")
        finally:
            conn.close()

    def delete_session(self, session_id: str):
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('DELETE FROM summaries WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM location_history WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM session_characters WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()
        logger.info(f"Session with ID '{session_id}' and all associated data deleted.")

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('SELECT session_id, name FROM sessions')
        rows = c.fetchall()
        sessions = [{'session_id': row[0], 'name': row[1]} for row in rows]
        conn.close()
        logger.debug(f"Retrieved {len(sessions)} sessions.")
        return sessions

    def get_current_setting(self, session_id: str) -> Optional[str]:
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
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('UPDATE sessions SET current_setting = ? WHERE session_id = ?', (setting_name, session_id))
        conn.commit()
        conn.close()
        logger.info(f"Session '{session_id}' updated with new setting '{setting_name}'.")

    def get_current_location(self, session_id: str) -> Optional[str]:
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
        conn = self._ensure_connection()
        c = conn.cursor()
        # Always update current_location in sessions
        c.execute('UPDATE sessions SET current_location = ? WHERE session_id = ?', (location, session_id))
        # Only record location history if triggered by a message
        if triggered_by_message_id is not None:
            c.execute('INSERT INTO location_history (session_id, location, triggered_by_message_id) VALUES (?, ?, ?)', (session_id, location, triggered_by_message_id))
        conn.commit()
        conn.close()
        if triggered_by_message_id:
            logger.info(f"Session '{session_id}' location updated to '{location}' by message ID {triggered_by_message_id}.")
        else:
            logger.info(f"Session '{session_id}' current location updated internally (no history recorded).")

    def get_location_history(self, session_id: str) -> List[Dict[str, Any]]:
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

    # Session Characters
    def add_character_to_session(self, session_id: str, character_name: str):
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('INSERT INTO session_characters (session_id, character_name) VALUES (?, ?)', (session_id, character_name))
        conn.commit()
        conn.close()
        logger.debug(f"Added character '{character_name}' to session '{session_id}'.")

    def remove_character_from_session(self, session_id: str, character_name: str):
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('DELETE FROM session_characters WHERE session_id = ? AND character_name = ?', (session_id, character_name))
        conn.commit()
        conn.close()
        logger.debug(f"Removed character '{character_name}' from session '{session_id}'.")

    def get_session_characters(self, session_id: str) -> List[str]:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('SELECT character_name FROM session_characters WHERE session_id = ?', (session_id,))
        rows = c.fetchall()
        conn.close()
        chars = [r[0] for r in rows]
        logger.debug(f"Retrieved {len(chars)} characters for session '{session_id}'.")
        return chars

    # Messages
    def save_message(self, session_id: str, sender: str, message: str, visible: bool = True, message_type: str = "user", affect: Optional[str]=None, purpose: Optional[str]=None) -> int:
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
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT id, sender, message, visible, message_type, affect, purpose, created_at
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
                'purpose': row[6],
                'created_at': row[7]
            })
        conn.close()
        logger.debug(f"Retrieved {len(messages)} messages for session '{session_id}'.")
        return messages

    # Summaries
    def save_new_summary(self, session_id: str, character_name: str, summary: str, covered_up_to_message_id: int):
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
