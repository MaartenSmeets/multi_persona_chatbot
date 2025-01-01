# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/db/db_manager.py
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from models.interaction import AppearanceSegments

logger = logging.getLogger(__name__)


def merge_location_update(old_location: str, new_location: str) -> str:
    """
    If new_location is empty, keep old. If not empty, replace with new_location.
    """
    if not new_location.strip():
        return old_location
    return new_location


def merge_appearance_subfield(old_val: str, new_val: str) -> str:
    """
    If new_val is empty, keep old_val. Otherwise, use new_val.
    """
    if not new_val.strip():
        return old_val
    return new_val


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

                why_purpose TEXT,
                why_affect TEXT,
                why_action TEXT,
                why_dialogue TEXT,
                why_new_location TEXT,
                why_new_appearance TEXT,

                new_location TEXT,

                -- Each new_appearance subfield is stored in separate columns:
                hair TEXT,
                clothing TEXT,
                accessories_and_held_items TEXT,
                posture_and_body_language TEXT,
                other_relevant_details TEXT,

                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        ''')

        # Add columns if they do not exist
        columns_to_add = [
            ("why_purpose", "TEXT"),
            ("why_affect", "TEXT"),
            ("why_action", "TEXT"),
            ("why_dialogue", "TEXT"),
            ("why_new_location", "TEXT"),
            ("why_new_appearance", "TEXT"),
            ("new_location", "TEXT"),
            ("hair", "TEXT"),
            ("clothing", "TEXT"),
            ("accessories_and_held_items", "TEXT"),
            ("posture_and_body_language", "TEXT"),
            ("other_relevant_details", "TEXT"),
        ]
        for col, ctype in columns_to_add:
            try:
                c.execute(f"ALTER TABLE messages ADD COLUMN {col} {ctype}")
                logger.info(f"Added column '{col}' to 'messages' table.")
            except sqlite3.OperationalError:
                logger.debug(f"Column '{col}' already exists in 'messages' table. Skipping.")

        # Create per-character message visibility table
        c.execute('''
            CREATE TABLE IF NOT EXISTS message_visibility (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                character_name TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                visible INTEGER DEFAULT 1,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                FOREIGN KEY(message_id) REFERENCES messages(id)
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
                current_location TEXT,
                current_appearance TEXT,
                PRIMARY KEY (session_id, character_name),
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        ''')
        # Add new appearance subfields if not present
        subfields_to_add = [
            ("hair", "TEXT"),
            ("clothing", "TEXT"),
            ("accessories_and_held_items", "TEXT"),
            ("posture_and_body_language", "TEXT"),
            ("other_relevant_details", "TEXT"),
        ]
        for col, ctype in subfields_to_add:
            try:
                c.execute(f"ALTER TABLE session_characters ADD COLUMN {col} {ctype}")
                logger.info(f"Added column '{col}' to 'session_characters' table.")
            except sqlite3.OperationalError:
                logger.debug(f"Column '{col}' already exists in 'session_characters' table. Skipping.")

        # Create appearance_history table
        c.execute('''
            CREATE TABLE IF NOT EXISTS appearance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                character_name TEXT NOT NULL,

                hair TEXT,
                clothing TEXT,
                accessories_and_held_items TEXT,
                posture_and_body_language TEXT,
                other_relevant_details TEXT,

                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                triggered_by_message_id INTEGER,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                FOREIGN KEY(triggered_by_message_id) REFERENCES messages(id)
            )
        ''')
        # Add columns if they do not exist
        appearance_cols = [
            ("hair", "TEXT"),
            ("clothing", "TEXT"),
            ("accessories_and_held_items", "TEXT"),
            ("posture_and_body_language", "TEXT"),
            ("other_relevant_details", "TEXT"),
        ]
        for col, ctype in appearance_cols:
            try:
                c.execute(f"ALTER TABLE appearance_history ADD COLUMN {col} {ctype}")
                logger.info(f"Added column '{col}' to 'appearance_history' table.")
            except sqlite3.OperationalError:
                logger.debug(f"Column '{col}' already exists in 'appearance_history' table. Skipping.")

        # Create character_prompts table
        c.execute('''
            CREATE TABLE IF NOT EXISTS character_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                character_name TEXT NOT NULL,
                character_system_prompt TEXT NOT NULL,
                dynamic_prompt_template TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                UNIQUE(session_id, character_name)
            )
        ''')

        # Create character_plans table
        c.execute('''
            CREATE TABLE IF NOT EXISTS character_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                character_name TEXT NOT NULL,
                goal TEXT,
                steps TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                UNIQUE(session_id, character_name)
            )
        ''')

        # Create character_plans_history table
        c.execute('''
            CREATE TABLE IF NOT EXISTS character_plans_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                character_name TEXT NOT NULL,
                goal TEXT,
                steps TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                triggered_by_message_id INTEGER,
                change_summary TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                FOREIGN KEY(triggered_by_message_id) REFERENCES messages(id)
            )
        ''')

        # Add a new column 'why_new_plan_goal' if not present in character_plans and history
        try:
            c.execute("ALTER TABLE character_plans ADD COLUMN why_new_plan_goal TEXT")
            logger.info("Added column 'why_new_plan_goal' to 'character_plans'.")
        except sqlite3.OperationalError:
            logger.debug("Column 'why_new_plan_goal' already exists in 'character_plans'. Skipping.")

        try:
            c.execute("ALTER TABLE character_plans_history ADD COLUMN why_new_plan_goal TEXT")
            logger.info("Added column 'why_new_plan_goal' to 'character_plans_history'.")
        except sqlite3.OperationalError:
            logger.debug("Column 'why_new_plan_goal' already exists in 'character_plans_history'. Skipping.")

        conn.commit()
        conn.close()
        logger.info("Database initialized with required tables (including new columns for segmented appearance).")

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
        c.execute('DELETE FROM appearance_history WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM character_plans WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM character_plans_history WHERE session_id = ?', (session_id,))
        c.execute('DELETE FROM message_visibility WHERE session_id = ?', (session_id,))
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

    # Character location & appearance management
    def add_character_to_session(self, session_id: str, character_name: str, initial_location: str = "", initial_appearance: str = ""):
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            INSERT OR IGNORE INTO session_characters (session_id, character_name, current_location, current_appearance)
            VALUES (?, ?, ?, ?)
        ''', (session_id, character_name, initial_location, initial_appearance))
        conn.commit()
        conn.close()
        logger.debug(
            f"Added character '{character_name}' to session '{session_id}' with initial location: '{initial_location}', appearance: '{initial_appearance}'."
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

    def get_character_appearance(self, session_id: str, character_name: str) -> str:
        """
        Returns a textual summary of the subfields plus the old current_appearance field
        for backward compatibility. 
        """
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT current_appearance, hair, clothing, accessories_and_held_items, posture_and_body_language, other_relevant_details
            FROM session_characters
            WHERE session_id = ? AND character_name = ?
        ''', (session_id, character_name))
        row = c.fetchone()
        conn.close()
        if row:
            legacy_app = row[0] or ""
            hair = row[1] or ""
            cloth = row[2] or ""
            acc = row[3] or ""
            posture = row[4] or ""
            other = row[5] or ""
            combined = []
            if hair.strip():
                combined.append(f"Hair: {hair}")
            if cloth.strip():
                combined.append(f"Clothing: {cloth}")
            if acc.strip():
                combined.append(f"Accessories/Held Items: {acc}")
            if posture.strip():
                combined.append(f"Posture/Body Language: {posture}")
            if other.strip():
                combined.append(f"Other Details: {other}")
            if not combined:
                # fallback to legacy
                return legacy_app
            return " | ".join(combined)
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

    def get_all_character_appearances(self, session_id: str) -> Dict[str, str]:
        """
        For each character, we do a short textual summary of the subfields.
        """
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT character_name, current_appearance, hair, clothing, accessories_and_held_items, posture_and_body_language, other_relevant_details
            FROM session_characters
            WHERE session_id = ?
        ''', (session_id,))
        rows = c.fetchall()
        conn.close()

        results = {}
        for row in rows:
            c_name = row[0]
            legacy_app = row[1] or ""
            hair = row[2] or ""
            cloth = row[3] or ""
            acc = row[4] or ""
            posture = row[5] or ""
            other = row[6] or ""
            combined = []
            if hair.strip():
                combined.append(f"Hair: {hair}")
            if cloth.strip():
                combined.append(f"Clothing: {cloth}")
            if acc.strip():
                combined.append(f"Accessories/Held Items: {acc}")
            if posture.strip():
                combined.append(f"Posture/Body: {posture}")
            if other.strip():
                combined.append(f"Other: {other}")
            if not combined:
                results[c_name] = legacy_app
            else:
                results[c_name] = " | ".join(combined)
        return results

    def update_character_location(self, session_id: str, character_name: str, new_location: str, triggered_by_message_id: Optional[int] = None) -> bool:
        old_location = self.get_character_location(session_id, character_name)
        updated_location = merge_location_update(old_location, new_location)

        if updated_location == old_location:
            logger.debug(f"No location change for character '{character_name}' in session '{session_id}'.")
            return False

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
                      (session_id, updated_location, triggered_by_message_id))
            conn.commit()
            conn.close()

        return True

    def update_character_appearance(self, session_id: str, character_name: str, new_appearance: AppearanceSegments, triggered_by_message_id: Optional[int] = None) -> bool:
        """
        Merge each subfield. If new_appearance has something, replace old.
        Then store in session_characters. Also store in appearance_history if changed.
        """
        # 1) get old subfields
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT hair, clothing, accessories_and_held_items, posture_and_body_language, other_relevant_details
            FROM session_characters
            WHERE session_id = ? AND character_name = ?
        ''', (session_id, character_name))
        row = c.fetchone()
        if not row:
            conn.close()
            logger.warning(f"No row found in session_characters for '{character_name}' in session '{session_id}'.")
            return False
        old_hair, old_cloth, old_acc, old_posture, old_other = row
        conn.close()

        # 2) merge
        merged_hair = merge_appearance_subfield(old_hair or "", new_appearance.hair or "")
        merged_cloth = merge_appearance_subfield(old_cloth or "", new_appearance.clothing or "")
        merged_acc = merge_appearance_subfield(old_acc or "", new_appearance.accessories_and_held_items or "")
        merged_posture = merge_appearance_subfield(old_posture or "", new_appearance.posture_and_body_language or "")
        merged_other = merge_appearance_subfield(old_other or "", new_appearance.other_relevant_details or "")

        if (
            merged_hair == (old_hair or "") and
            merged_cloth == (old_cloth or "") and
            merged_acc == (old_acc or "") and
            merged_posture == (old_posture or "") and
            merged_other == (old_other or "")
        ):
            logger.debug(f"No appearance change for '{character_name}' in session '{session_id}'.")
            return False

        # 3) update session_characters
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            UPDATE session_characters
            SET hair = ?, clothing = ?, accessories_and_held_items = ?, 
                posture_and_body_language = ?, other_relevant_details = ?
            WHERE session_id = ? AND character_name = ?
        ''', (
            merged_hair,
            merged_cloth,
            merged_acc,
            merged_posture,
            merged_other,
            session_id,
            character_name
        ))
        conn.commit()
        conn.close()

        logger.info(
            f"Updated appearance of character '{character_name}' in session '{session_id}'."
        )

        # 4) insert into appearance_history
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO appearance_history (
                session_id, character_name,
                hair, clothing, accessories_and_held_items, 
                posture_and_body_language, other_relevant_details,
                triggered_by_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id,
            character_name,
            merged_hair,
            merged_cloth,
            merged_acc,
            merged_posture,
            merged_other,
            triggered_by_message_id
        ))
        conn.commit()
        conn.close()

        return True

    # Messages
    def save_message(self,
                     session_id: str,
                     sender: str,
                     message: str,
                     visible: bool,
                     message_type: str,
                     affect: Optional[str],
                     purpose: Optional[str],
                     why_purpose: Optional[str],
                     why_affect: Optional[str],
                     why_action: Optional[str],
                     why_dialogue: Optional[str],
                     why_new_location: Optional[str],
                     why_new_appearance: Optional[str],
                     new_location: Optional[str],
                     hair: Optional[str],
                     clothing: Optional[str],
                     accessories_and_held_items: Optional[str],
                     posture_and_body_language: Optional[str],
                     other_relevant_details: Optional[str]
                    ) -> int:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO messages (
                session_id, sender, message, visible, message_type,
                affect, purpose,
                why_purpose, why_affect, why_action, why_dialogue,
                why_new_location, why_new_appearance,
                new_location,
                hair, clothing, accessories_and_held_items, posture_and_body_language, other_relevant_details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            why_new_appearance,
            new_location,
            hair,
            clothing,
            accessories_and_held_items,
            posture_and_body_language,
            other_relevant_details
        ))
        message_id = c.lastrowid
        conn.commit()
        conn.close()
        logger.debug(f"Message saved with ID {message_id} for session '{session_id}'.")
        return message_id

    #
    # Per-character message visibility
    #
    def add_message_visibility_for_session_characters(self, session_id: str, message_id: int):
        """
        After saving a new message, mark it as visible for each character in session_characters.
        """
        chars = self.get_session_characters(session_id)
        conn = self._ensure_connection()
        c = conn.cursor()
        for char in chars:
            c.execute('''
                INSERT INTO message_visibility (session_id, character_name, message_id, visible)
                VALUES (?, ?, ?, ?)
            ''', (session_id, char, message_id, 1))
        conn.commit()
        conn.close()
        logger.debug(
            f"Marked message ID {message_id} as visible for all characters in session '{session_id}': {chars}"
        )

    def get_visible_messages_for_character(self, session_id: str, character_name: str) -> List[Dict[str, Any]]:
        """
        Return only messages that are still marked visible for a given character.
        """
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT m.id, m.sender, m.message, mv.visible, m.message_type,
                   m.affect, m.purpose, m.created_at,
                   m.why_purpose, m.why_affect, m.why_action, m.why_dialogue,
                   m.why_new_location, m.why_new_appearance,
                   m.new_location,
                   m.hair, m.clothing, m.accessories_and_held_items, m.posture_and_body_language, m.other_relevant_details
            FROM messages m
            JOIN message_visibility mv ON m.id = mv.message_id
            WHERE mv.session_id = ?
              AND mv.character_name = ?
              AND mv.visible = 1
            ORDER BY m.id ASC
        ''', (session_id, character_name))
        rows = c.fetchall()
        conn.close()
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
                'why_new_appearance': row[13],
                'new_location': row[14],
                'hair': row[15],
                'clothing': row[16],
                'accessories_and_held_items': row[17],
                'posture_and_body_language': row[18],
                'other_relevant_details': row[19],
            })
        return messages

    def hide_messages_for_character(self, session_id: str, character_name: str, message_ids: List[int]):
        """
        Hide a list of messages for one character by setting visible=0 in message_visibility.
        """
        if not message_ids:
            return
        conn = self._ensure_connection()
        c = conn.cursor()
        placeholders = ",".join("?" * len(message_ids))
        params = [session_id, character_name] + message_ids
        c.execute(f'''
            UPDATE message_visibility
            SET visible = 0
            WHERE session_id = ?
              AND character_name = ?
              AND message_id IN ({placeholders})
        ''', params)
        conn.commit()
        conn.close()
        logger.debug(
            f"Hidden messages {message_ids} for character '{character_name}' in session '{session_id}'."
        )

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """
        This returns *all* messages in ascending order from the messages table.
        This does NOT reflect the per-character visibility. It's mostly for overall
        session logging or for the user to see everything.
        """
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT 
                id, sender, message, visible, message_type,
                affect, purpose, created_at,
                why_purpose, why_affect, why_action, why_dialogue,
                why_new_location, why_new_appearance,
                new_location,
                hair, clothing, accessories_and_held_items, posture_and_body_language, other_relevant_details
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
                'why_new_appearance': row[13],
                'new_location': row[14],
                'hair': row[15],
                'clothing': row[16],
                'accessories_and_held_items': row[17],
                'posture_and_body_language': row[18],
                'other_relevant_details': row[19],
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

    def get_all_summaries(self, session_id: str, character_name: Optional[str]) -> List[str]:
        conn = self._ensure_connection()
        c = conn.cursor()
        if character_name:
            c.execute('''
                SELECT summary FROM summaries
                WHERE session_id = ? AND character_name = ?
                ORDER BY id ASC
            ''', (session_id, character_name))
        else:
            c.execute('''
                SELECT summary FROM summaries
                WHERE session_id = ?
                ORDER BY id ASC
            ''', (session_id,))
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
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT character_system_prompt, dynamic_prompt_template
            FROM character_prompts
            WHERE session_id = ? AND character_name = ?
        ''', (session_id, character_name))
        row = c.fetchone()
        conn.close()
        if row:
            logger.debug(f"Retrieved prompts for character '{character_name}' in session '{session_id}'.")
            return {
                'character_system_prompt': row[0],
                'dynamic_prompt_template': row[1]
            }
        logger.debug(f"No prompts found for character '{character_name}' in session '{session_id}'.")
        return None

    def save_character_prompts(self, session_id: str, character_name: str, character_system_prompt: str, dynamic_prompt_template: str):
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO character_prompts (session_id, character_name, character_system_prompt, dynamic_prompt_template)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, character_name)
            DO UPDATE SET character_system_prompt=excluded.character_system_prompt,
                          dynamic_prompt_template=excluded.dynamic_prompt_template
        ''', (session_id, character_name, character_system_prompt, dynamic_prompt_template))
        conn.commit()
        conn.close()
        logger.info(f"Stored character_system_prompt and dynamic_prompt_template for character '{character_name}' in session '{session_id}'.")

    #
    # Character Plans (goal + steps + reason)
    #
    def get_character_plan(self, session_id: str, character_name: str) -> Optional[Dict[str, Any]]:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT goal, steps, updated_at, why_new_plan_goal
            FROM character_plans
            WHERE session_id = ? AND character_name = ?
        ''', (session_id, character_name))
        row = c.fetchone()
        conn.close()
        if row:
            goal_str = row[0] or ""
            steps_str = row[1] or ""
            updated_at = row[2]
            why_new_plan = row[3] or ""
            steps_list = []
            if steps_str:
                try:
                    steps_list = json.loads(steps_str)
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse steps as JSON: {steps_str}")
            return {
                'goal': goal_str,
                'steps': steps_list,
                'updated_at': updated_at,
                'why_new_plan_goal': why_new_plan
            }
        return None

    def save_character_plan(self, session_id: str, character_name: str, goal: str, steps: List[str], why_new_plan_goal: str):
        steps_str = json.dumps(steps)
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO character_plans (session_id, character_name, goal, steps, why_new_plan_goal)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id, character_name)
            DO UPDATE SET goal=excluded.goal,
                          steps=excluded.steps,
                          why_new_plan_goal=excluded.why_new_plan_goal,
                          updated_at=CURRENT_TIMESTAMP
        ''', (session_id, character_name, goal, steps_str, why_new_plan_goal))
        conn.commit()
        conn.close()
        logger.info(f"Saved character plan for '{character_name}' in session '{session_id}': goal={goal}, steps={steps}, reason={why_new_plan_goal}")

    def save_character_plan_with_history(
        self,
        session_id: str,
        character_name: str,
        goal: str,
        steps: List[str],
        why_new_plan_goal: str,
        triggered_by_message_id: Optional[int],
        change_summary: str
    ):
        steps_str = json.dumps(steps)
        conn = self._ensure_connection()
        c = conn.cursor()

        c.execute('''
            INSERT INTO character_plans (session_id, character_name, goal, steps, why_new_plan_goal)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id, character_name)
            DO UPDATE SET goal=excluded.goal,
                          steps=excluded.steps,
                          why_new_plan_goal=excluded.why_new_plan_goal,
                          updated_at=CURRENT_TIMESTAMP
        ''', (session_id, character_name, goal, steps_str, why_new_plan_goal))

        c.execute('''
            INSERT INTO character_plans_history (session_id, character_name, goal, steps, triggered_by_message_id, change_summary, why_new_plan_goal)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id,
            character_name,
            goal,
            steps_str,
            triggered_by_message_id if triggered_by_message_id else None,
            change_summary,
            why_new_plan_goal
        ))

        conn.commit()
        conn.close()
        logger.info(
            f"Saved character plan (with history) for '{character_name}' in session '{session_id}': "
            f"goal={goal}, steps={steps}, reason={why_new_plan_goal}, triggered_by={triggered_by_message_id}, summary='{change_summary}'"
        )

    def get_plan_changes_for_range(self, session_id: str, character_name: str, after_message_id: int, up_to_message_id: int) -> List[Dict[str, Any]]:
        conn = self._ensure_connection()
        c = conn.cursor()
        c.execute('''
            SELECT triggered_by_message_id, change_summary, why_new_plan_goal
            FROM character_plans_history
            WHERE session_id = ?
              AND character_name = ?
              AND triggered_by_message_id IS NOT NULL
              AND triggered_by_message_id > ?
              AND triggered_by_message_id <= ?
            ORDER BY id ASC
        ''', (session_id, character_name, after_message_id, up_to_message_id))
        rows = c.fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append({
                "triggered_by_message_id": row[0],
                "change_summary": row[1],
                "why_new_plan_goal": row[2] or ""
            })
        return results

