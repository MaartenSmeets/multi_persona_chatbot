import sqlite3
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def merge_location_update(old_location: str, new_location: str) -> str:
    """
    If new_location is empty, keep old. If not empty, replace with the new location.
    """
    if not new_location.strip():
        return old_location
    return new_location

def merge_clothing_update(old_clothing: str, new_clothing: str) -> str:
    """
    If new_clothing is empty, keep old. If not empty, replace with new.
    """
    if not new_clothing.strip():
        return old_clothing
    return new_clothing

class DBManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initialize_database()

    def _ensure_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

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

        # Create messages table (with columns for all "why_*" plus new_location/new_clothing)
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

                why_purpose TEXT,
                why_affect TEXT,
                why_action TEXT,
                why_dialogue TEXT,
                why_new_location TEXT,
                why_new_clothing TEXT,

                new_location TEXT,
                new_clothing TEXT,

                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        ''')

        # Add columns if they do not exist:
        columns_to_add = [
            ("why_purpose", "TEXT"),
            ("why_affect", "TEXT"),
            ("why_action", "TEXT"),
            ("why_dialogue", "TEXT"),
            ("why_new_location", "TEXT"),
            ("why_new_clothing", "TEXT"),
            ("new_location", "TEXT"),
            ("new_clothing", "TEXT"),
        ]
        for col, ctype in columns_to_add:
            try:
                c.execute(f"ALTER TABLE messages ADD COLUMN {col} {ctype}")
            except sqlite3.OperationalError:
                pass  # Column already exists

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

        # Create or alter session_characters table to include current_location and current_clothing
        c.execute('''
            CREATE TABLE IF NOT EXISTS session_characters (
                session_id TEXT NOT NULL,
                character_name TEXT NOT NULL,
                current_location TEXT,
                current_clothing TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                PRIMARY KEY (session_id, character_name)
            )
        ''')
        try:
            c.execute("ALTER TABLE session_characters ADD COLUMN current_clothing TEXT")
        except sqlite3.OperationalError:
            pass

        # Create character_prompts table
        c.execute('''
            CREATE TABLE IF NOT EXISTS character_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                character_name TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                user_prompt_template TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                UNIQUE(session_id, character_name)
            )
        ''')

        # NEW: Create clothing_history table for storing chronological clothing changes
        c.execute('''
            CREATE TABLE IF NOT EXISTS clothing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                character_name TEXT NOT NULL,
                clothing TEXT NOT NULL,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                triggered_by_message_id INTEGER,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                FOREIGN KEY(triggered_by_message_id) REFERENCES messages(id)
            )
        ''')

        conn.commit()
        conn.close()
        logger.info("Database initialized with required tables (including new location/clothing histories).")

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
        c.execute('DELETE FROM character_prompts WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM clothing_history WHERE session_id = ?', (session_id,))
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
            logger.debug(f"Current location (session-wide) for session '{session_id}': {row[0]}")
            return row[0]
        return None

    def update_current_location(self, session_id: str, location: str, triggered_by_message_id: Optional[int] = None):
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('UPDATE sessions SET current_location = ? WHERE session_id = ?', (location, session_id))
        if triggered_by_message_id is not None:
            c.execute('INSERT INTO location_history (session_id, location, triggered_by_message_id) VALUES (?, ?, ?)',
                      (session_id, location, triggered_by_message_id))
        conn.commit()
        conn.close()
        if triggered_by_message_id:
            logger.info(f"Global location for session '{session_id}' updated to '{location}' (by message ID={triggered_by_message_id}).")
        else:
            logger.info(f"Global location for session '{session_id}' updated to '{location}' with no trigger message.")

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

    # Character location & clothing management
    def add_character_to_session(self, session_id: str, character_name: str, initial_location: str = "", initial_clothing: str = ""):
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            INSERT OR IGNORE INTO session_characters (session_id, character_name, current_location, current_clothing)
            VALUES (?, ?, ?, ?)
        ''', (session_id, character_name, initial_location, initial_clothing))
        conn.commit()
        conn.close()
        logger.debug(
            f"Added character '{character_name}' to session '{session_id}' with initial location: '{initial_location}', clothing: '{initial_clothing}'."
        )

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

    def get_character_location(self, session_id: str, character_name: str) -> Optional[str]:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT current_location
            FROM session_characters
            WHERE session_id = ? AND character_name = ?
        ''', (session_id, character_name))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
        return ""

    def get_character_clothing(self, session_id: str, character_name: str) -> str:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT current_clothing
            FROM session_characters
            WHERE session_id = ? AND character_name = ?
        ''', (session_id, character_name))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
        return ""

    def get_all_character_locations(self, session_id: str) -> Dict[str, str]:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT character_name, current_location
            FROM session_characters
            WHERE session_id = ?
        ''', (session_id,))
        rows = c.fetchall()
        conn.close()
        return {row[0]: (row[1] if row[1] else "") for row in rows}

    def get_all_character_clothing(self, session_id: str) -> Dict[str, str]:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT character_name, current_clothing
            FROM session_characters
            WHERE session_id = ?
        ''', (session_id,))
        rows = c.fetchall()
        conn.close()
        return {row[0]: (row[1] if row[1] else "") for row in rows}

    def update_character_location(self, session_id: str, character_name: str, new_location: str, triggered_by_message_id: Optional[int] = None):
        old_location = self.get_character_location(session_id, character_name)
        updated_location = merge_location_update(old_location, new_location)

        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            UPDATE session_characters
            SET current_location = ?
            WHERE session_id = ? AND character_name = ?
        ''', (updated_location, session_id, character_name))
        conn.commit()
        conn.close()

        logger.info(
            f"Updated location of character '{character_name}' in session '{session_id}' "
            f"from '{old_location}' to '{updated_location}'."
        )

        if triggered_by_message_id:
            conn = self._ensure_connection()
            c = conn.cursor()
            c.execute('INSERT INTO location_history (session_id, location, triggered_by_message_id) VALUES (?, ?, ?)',
                      (session_id, f"{character_name} is now {updated_location}", triggered_by_message_id))
            conn.commit()
            conn.close()

    def update_character_clothing(self, session_id: str, character_name: str, new_clothing: str, triggered_by_message_id: Optional[int] = None):
        old_clothing = self.get_character_clothing(session_id, character_name)
        updated_clothing = merge_clothing_update(old_clothing, new_clothing)

        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            UPDATE session_characters
            SET current_clothing = ?
            WHERE session_id = ? AND character_name = ?
        ''', (updated_clothing, session_id, character_name))
        conn.commit()
        conn.close()

        logger.info(
            f"Updated clothing of character '{character_name}' in session '{session_id}' "
            f"from '{old_clothing}' to '{updated_clothing}'."
        )

        if triggered_by_message_id:
            # Also record in clothing_history
            conn = self._ensure_connection()
            c = conn.cursor()
            c.execute('''
                INSERT INTO clothing_history (session_id, character_name, clothing, triggered_by_message_id)
                VALUES (?, ?, ?, ?)
            ''', (session_id, character_name, updated_clothing, triggered_by_message_id))
            conn.commit()
            conn.close()

    # Messages
    def save_message(self,
                     session_id: str,
                     sender: str,
                     message: str,
                     visible: bool = True,
                     message_type: str = "user",
                     affect: Optional[str]=None,
                     purpose: Optional[str]=None,
                     why_purpose: Optional[str]=None,
                     why_affect: Optional[str]=None,
                     why_action: Optional[str]=None,
                     why_dialogue: Optional[str]=None,
                     why_new_location: Optional[str]=None,
                     why_new_clothing: Optional[str]=None,
                     new_location: Optional[str]=None,
                     new_clothing: Optional[str]=None) -> int:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO messages (
                session_id, sender, message, visible, message_type,
                affect, purpose,
                why_purpose, why_affect, why_action, why_dialogue, 
                why_new_location, why_new_clothing,
                new_location, new_clothing
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id,
            sender,
            message,
            int(visible),
            message_type,
            affect,
            purpose,
            why_purpose,
            why_affect,
            why_action,
            why_dialogue,
            why_new_location,
            why_new_clothing,
            new_location,
            new_clothing
        ))
        message_id = c.lastrowid
        conn.commit()
        conn.close()
        logger.debug(f"Message saved with ID {message_id} for session '{session_id}'.")
        return message_id

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT 
                id, sender, message, visible, message_type,
                affect, purpose, created_at,
                why_purpose, why_affect, why_action, why_dialogue,
                why_new_location, why_new_clothing,
                new_location, new_clothing
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
                'created_at': row[7],
                'why_purpose': row[8],
                'why_affect': row[9],
                'why_action': row[10],
                'why_dialogue': row[11],
                'why_new_location': row[12],
                'why_new_clothing': row[13],
                'new_location': row[14],
                'new_clothing': row[15],
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
        logger.debug(
            f"Summary saved for character '{character_name}' in session '{session_id}' "
            f"up to message ID {covered_up_to_message_id}."
        )

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

    # Character Prompts
    def get_character_prompts(self, session_id: str, character_name: str) -> Optional[Dict[str, str]]:
        """Fetches the stored system_prompt and user_prompt_template for this character in this session."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT system_prompt, user_prompt_template
            FROM character_prompts
            WHERE session_id = ? AND character_name = ?
        ''', (session_id, character_name))
        row = c.fetchone()
        conn.close()
        if row:
            return {'system_prompt': row[0], 'user_prompt_template': row[1]}
        return None

    def save_character_prompts(self, session_id: str, character_name: str, system_prompt: str, user_prompt_template: str):
        """Inserts or replaces the character prompts for a given (session, character)."""
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO character_prompts (session_id, character_name, system_prompt, user_prompt_template)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, character_name)
            DO UPDATE SET system_prompt=excluded.system_prompt,
                          user_prompt_template=excluded.user_prompt_template
        ''', (session_id, character_name, system_prompt, user_prompt_template))
        conn.commit()
        conn.close()
        logger.info(f"Stored system_prompt and user_prompt_template for character '{character_name}' in session '{session_id}'.")
