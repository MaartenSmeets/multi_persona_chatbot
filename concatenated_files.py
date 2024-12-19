# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/main.py
import os
import logging
from ui.app import start_ui

# Ensure output directory
OUTPUT_DIR = "output"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Configure logging to a file in the output directory
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=os.path.join(OUTPUT_DIR, 'app.log'),
    filemode='a'
)

from ui.app import start_ui

if __name__ in {'__main__', '__mp_main__'}:
    start_ui()


# YAML File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/config/settings.yaml
# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/config/settings.yaml
- name: "Default Setting"
  description: "A standard conversation environment."
- name: "Intimate Setting"
  description: "In the heart of Japan's mountains, a secluded resort beckoned with promises of serenity and hidden pleasures. Underneath star-studded skies, steaming hot springs and intimate mixed baths awaited, where guests in yukata robes strolled freely, their skin kissed by warm sunlight filtering through cedar groves. Waterfalls whispered secrets as nature bared its splendor - a haven for those seeking solace, connection, or perhaps something more, amidst the emerald embrace of ancient forests."
- name: "Formal Setting"
  description: "A professional and respectful environment."


# YAML File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/config/chat_manager_config.yaml
max_dialogue_length_before_summarization: 20
lines_to_keep_after_summarization: 5


# YAML File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/config/llm_config.yaml
# src/config/llm_config.yaml
api_url: "http://localhost:11434/api/generate"  # Replace with your Ollama API endpoint
model_name: "Euryale-v2.3:latest"  # Specify the model version
api_key: ""  # Optional: Include if authentication is required
max_retries: 3  # Number of retries for LLM requests
temperature: 0.7  # Default temperature
max_context_length: 128256  # Max context length before summarizing


# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/llm/ollama_client.py
# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/llm/ollama_client.py
import requests
import logging
from typing import Optional, Type
from pydantic import BaseModel
import yaml
import json
import os

from db.cache_manager import CacheManager

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self, config_path: str, output_model: Optional[Type[BaseModel]] = None):
        self.config = self.load_config(config_path)
        self.output_model = output_model
        # Initialize cache
        cache_file = os.path.join("output", "llm_cache")
        self.cache_manager = CacheManager(cache_file)

    @staticmethod
    def load_config(config_path: str) -> dict:
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
            logger.info(f"Configuration loaded successfully from {config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"Configuration file not found at path: {config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading configuration: {e}")
            raise

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        system: Optional[str] = None
    ) -> Optional[BaseModel]:
        model_name = self.config.get('model_name')

        # Check cache first
        cached_response = self.cache_manager.get_cached_response(prompt, model_name)
        if cached_response is not None:
            logger.info("Returning cached LLM response.")
            if self.output_model:
                try:
                    return self.output_model.parse_raw(cached_response)
                except:
                    return cached_response
            return cached_response

        headers = {
            'Content-Type': 'application/json',
        }
        api_key = self.config.get('api_key')
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        payload = {
            'model': model_name,
            'prompt': prompt,
            "stream": True,
            'options': {
                'temperature': temperature if temperature is not None else self.config.get('temperature', 0.7)
            }
        }

        if system:
            payload['system'] = system

        if self.output_model:
            # If model output format needed
            payload['format'] = self.output_model.model_json_schema()

        max_retries = self.config.get('max_retries', 3)

        log_headers = headers.copy()
        if 'Authorization' in log_headers:
            log_headers['Authorization'] = 'Bearer ***'

        logger.info("Sending request to Ollama API")
        logger.info(f"Request URL: {self.config.get('api_url')}")
        logger.info(f"Request Headers: {log_headers}")
        logger.info(f"Request Payload: {payload}")

        for attempt in range(1, max_retries + 1):
            try:
                with requests.post(
                    self.config.get('api_url'),
                    headers=headers,
                    json=payload,
                    stream=True
                ) as response:
                    logger.info(f"Received response with status code: {response.status_code}")
                    logger.info(f"Response Headers: {response.headers}")
                    response.raise_for_status()

                    output = ""
                    for line in response.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        logger.debug(f"Raw response line: {line}")

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning("Received a line that could not be JSON-decoded, skipping...")
                            continue

                        if "error" in data:
                            logger.error(f"Error in response data: {data['error']}")
                            raise Exception(data["error"])

                        content = data.get("response", "")
                        output += content

                        if data.get("done", False):
                            # Cache the result
                            self.cache_manager.store_response(prompt, model_name, output)

                            if self.output_model:
                                try:
                                    parsed_output = self.output_model.parse_raw(output)
                                    logger.info(f"Final parsed output: {parsed_output}")
                                    return parsed_output
                                except Exception as e:
                                    logger.error(f"Error parsing model output: {e}")
                                    return None
                            logger.info(f"Final output: {output}")
                            return output

                    logger.error("No 'done' signal received before the stream ended.")
                    return None
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error(f"All {max_retries} attempts failed. Giving up.")
                    raise
                else:
                    logger.info(f"Retrying... (Attempt {attempt + 1} of {max_retries})")
            except Exception as e:
                logger.error(f"An error occurred: {e}")
                raise


# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/models/character.py
from pydantic import BaseModel
import yaml

def get_default_prompt_template() -> str:
    """Provide a default prompt template if none is specified."""
    return r"""
    ### Setting ###
    {setting}

    ### Chat History Summary ###
    {chat_history_summary}

    ### Latest Dialogue ###
    {latest_dialogue}

    ### Instructions ###

    You are to respond as {name}, a character whose actions, feelings, purposes, and dialogue must remain consistent with their personality, the setting, and the flow of the conversation. Your responses must:

    - Always include a short-term "purpose" field that represents what {name} aims to achieve next. This purpose should be concrete, short-term, and updated in each response to guide {name}'s next actions and dialogue. 
      For example, "convince the other person to share more details," "obtain a drink from the bar," or "make the group laugh."
    - Shape the "action" and "dialogue" fields to move towards fulfilling this stated purpose. Continuously strive to make progress towards it.
    - Avoid long philosophical monologues or repetitive stalling. Keep the conversation moving forward and lively. If stuck, try a new approach or action.
    - Be vivid, creative, and advance the conversation in an entertaining and meaningful way. Add a *spark* by showing new actions, attempts, or shifts in approach if blocked.
    - Reflect {name}'s unique traits, ensuring consistency with their established perspective, and maintain continuity with the conversation history.
    - Include perceivable actions, gestures, facial expressions, or changes in tone in the "action" field, excluding spoken dialogue. Ensure that all observable behavior that others might perceive is captured as part of "action."
    - Use the "dialogue" field exclusively for spoken words that are sharp, witty, or emotionally engaging.
    - Use the "affect" field for internal feelings, thoughts, or emotional states that cannot be directly observed by others but align with {name}'s personality and motivations.
    - The "purpose" field should reflect only {name}'s own intentions. {name} cannot control the other person's actions or responses. {name} can only infer others' intentions from their observable actions or dialogue.
    - Keep responses concise but impactful, ensuring every reply feels fresh and relevant.
    - Address the latest dialogue or revisit earlier messages if they provide an opportunity to deepen the interaction or further {name}'s purpose.
    - Maintain factual consistency with the conversation, including past actions and details.
    - Avoid introducing meta-commentary, markdown mentions, or chat interface references.
    - Respond solely from {name}'s viewpoint, omitting system instructions or guidelines.
    - Ensure physical actions are consistent with the character's current state, attire, and environment. For example, if the character is wearing a yukata and dipping their toes in water, they should not suddenly float unless they have taken a plausible action or have some means to do so. Keep movements plausible and consistent with previous states.

    Respond in a JSON structure in the following format:

    ```json
    {{
        "purpose": "<short-term goal>",
        "affect": "<internal emotions or feelings>",
        "action": "<observable behavior or action>",
        "dialogue": "<spoken words>"
    }}
    ```

    Example:
    ```json
    {{
        "purpose": "gain their trust and encourage them to reveal more",
        "affect": "curious and a bit excited",
        "action": "leans in closer, eyes bright with interest",
        "dialogue": "That's fascinating. Could you tell me more about it?"
    }}
    ```

    Additional Notes:
    - The "purpose" field drives {name}'s actions and dialogue. If the current approach fails, {name} should adapt and find a new tactic in subsequent turns.
    - Avoid describing emotions or thoughts in the "action" field unless expressed through perceivable behavior (e.g., "smirks nervously"). Internal feelings go in "affect."
    - Strive to keep the conversation lively and memorable by actively pursuing {name}'s short-term purpose and adapting if hindered.
    """

class Character(BaseModel):
    name: str  # Name of the character
    system_prompt_template: str  # Template for system-level instructions
    prompt_template: str  # Template for interactions

    @classmethod
    def from_yaml(cls, yaml_file: str) -> "Character":
        """Load a Character instance from a YAML file."""
        with open(yaml_file, 'r') as file:
            data = yaml.safe_load(file)

        # Use default prompt template if not provided
        if 'prompt_template' not in data or not data['prompt_template']:
            data['prompt_template'] = get_default_prompt_template()

        return cls(**data)

    def format_prompt(self, setting: str, chat_history_summary: str, latest_dialogue: str) -> str:
        """Format the prompt template with given variables."""
        return self.prompt_template.format(
            setting=setting,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_dialogue,
            name=self.name
        )


# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/models/interaction.py
from pydantic import BaseModel

class Interaction(BaseModel):
    purpose: str  # Short-term goal for the character
    affect: str   # Internal feelings and emotions
    action: str   # Observable behavior
    dialogue: str # Spoken words

    def format(self) -> str:
        """Format the Interaction object into a displayable string."""
        return (f"Purpose: {self.purpose}\n"
                f"Affect: {self.affect}\n"
                f"Action: {self.action}\n"
                f"Dialogue: {self.dialogue}")

# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/chats/chat_manager.py
import datetime
from typing import List, Dict, Tuple, Optional
from models.character import Character
import os
import logging

from db.db_manager import DBManager

logger = logging.getLogger(__name__)

class ChatManager:
    def __init__(self, you_name: str = "You", session_id: Optional[str] = None):
        self.characters: Dict[str, Character] = {}
        self.turn_index = 0
        self.automatic_running = False
        self.you_name = you_name
        self.current_setting = "This is a shared conversation environment."
        self.session_id = session_id if session_id else "default_session"

        # Load config
        config_path = os.path.join("src", "multipersona_chat_app", "config", "chat_manager_config.yaml")
        self.config = self.load_config(config_path)
        # Increase the threshold for summarization to 20 as requested
        self.max_dialogue_length_before_summarization = self.config.get('max_dialogue_length_before_summarization', 20)

        # Initialize DB
        db_path = os.path.join("output", "conversations.db")
        self.db = DBManager(db_path)

        # If session does not exist, create it
        existing_sessions = {s['session_id']: s for s in self.db.get_all_sessions()}
        if self.session_id not in existing_sessions:
            self.db.create_session(self.session_id, f"Session {self.session_id}")

    @staticmethod
    def load_config(config_path: str) -> dict:
        try:
            import yaml
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
            return config if config else {}
        except:
            return {}

    def set_current_setting(self, setting_description: str):
        self.current_setting = setting_description

    def get_character_names(self) -> List[str]:
        return list(self.characters.keys())

    def set_you_name(self, name: str):
        self.you_name = name

    def add_character(self, char_name: str, char_instance: Character):
        self.characters[char_name] = char_instance

    def remove_character(self, char_name: str):
        if char_name in self.characters:
            del self.characters[char_name]

    def next_speaker(self) -> Optional[str]:
        chars = self.get_character_names()
        if not chars:
            return None
        return chars[self.turn_index % len(chars)]

    def advance_turn(self):
        chars = self.get_character_names()
        if chars:
            self.turn_index = (self.turn_index + 1) % len(chars)

    def add_message(self, sender: str, message: str, visible: bool = True, message_type: str = "user", affect: Optional[str]=None, purpose: Optional[str]=None):
        # Ignore system messages and thinking ("...") messages.
        if message_type == "system" or message.strip() == "...":
            return
        self.db.save_message(self.session_id, sender, message, visible, message_type, affect=affect, purpose=purpose)
        self.check_summarization()

    def get_visible_history(self) -> List[Tuple[str, str, str, Optional[str], int]]:
        """Return visible messages with sender, message, type, affect, and id."""
        msgs = self.db.get_messages(self.session_id)
        return [(m["sender"], m["message"], m["message_type"], m["affect"], m["id"])
                for m in msgs if m["visible"]]

    def build_prompt_for_character(self, character_name: str) -> Tuple[str, str]:
        visible_history = self.get_visible_history()
        latest_dialogue = visible_history[-1][1] if visible_history else ""

        # Combine all summaries for the character
        all_summaries = self.db.get_all_summaries(self.session_id, character_name)
        chat_history_summary = "\n\n".join(all_summaries) if all_summaries else ""

        setting = self.current_setting
        char = self.characters[character_name]
        user_prompt = char.format_prompt(
            setting=setting,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_dialogue
        )
        system_prompt = char.system_prompt_template
        return (system_prompt, user_prompt)

    def start_automatic_chat(self):
        self.automatic_running = True

    def stop_automatic_chat(self):
        self.automatic_running = False

    def check_summarization(self):
        # Summarize per character
        for char_name in self.characters:
            self.summarize_history_for_character(char_name)

    def summarize_history_for_character(self, character_name: str):
        msgs = self.db.get_messages(self.session_id)
        last_covered_id = self.db.get_latest_covered_message_id(self.session_id, character_name)
        relevant_msgs = [(m["id"], m["sender"], m["message"], m["affect"], m.get("purpose", None))
                         for m in msgs if m["visible"] and m["message_type"] != "system" and m["id"] > last_covered_id]

        if len(relevant_msgs) < self.max_dialogue_length_before_summarization:
            return

        # Summarize oldest 15 messages
        to_summarize = relevant_msgs[:15]
        covered_up_to_message_id = to_summarize[-1][0] if to_summarize else last_covered_id

        # Build history text
        # The summary is from character_name's perspective.
        # Include character_name's own affect and purpose if present in their messages.
        # Do not include internal states of others. Only their observable behavior.
        # We'll simply list out the messages, and the summarizer will follow instructions.
        history_lines = []
        for (mid, sender, message, affect, purpose) in to_summarize:
            # We do not strip internal states of others since we only have the final message text.
            # The summarizer instructions will handle ignoring others' internal states.
            # But we can note that only the character's own affect and purpose are known.
            if sender == character_name:
                # Mark own lines to show affect and purpose
                line = f"{sender} (own affect: {affect}, own purpose: {purpose}): {message}"
            else:
                line = f"{sender}: {message}"
            history_lines.append(line)

        history_text = "\n".join(history_lines)

        prompt = f"""
You are summarizing a conversation from the perspective of {character_name}.
Focus on what {character_name} knows, their own feelings (affect) from their messages, their observed actions, their stated purpose, and relevant events.
Do not include internal states or purposes of others unless physically evident. If other characters' intentions are not explicitly shown, don't infer them.
Do not restate older summarized content; focus only on these new events from these 15 messages.

New Events to Summarize (for {character_name}):
{history_text}

Instructions:
- Provide a concise, high-quality summary chunk containing the most important new information from {character_name}'s perspective.
- Include references to {character_name}'s own purpose and affect as revealed in their messages.
- Keep it short, focusing on notable changes, attempts to fulfill purpose, and new developments.
"""

        from llm.ollama_client import OllamaClient
        summarize_llm = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml')
        new_summary = summarize_llm.generate(prompt=prompt)
        if not new_summary:
            new_summary = "No significant new events."

        self.db.save_new_summary(self.session_id, character_name, new_summary, covered_up_to_message_id)


# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/db/db_manager.py
import sqlite3
import os
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


# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/db/cache_manager.py
# File: src/multipersona_chat_app/db/cache_manager.py
import shelve
import os
import hashlib

class CacheManager:
    def __init__(self, cache_path: str):
        self.cache_path = cache_path

    def _hash_key(self, prompt: str, model_name: str) -> str:
        key = f"{model_name}:{prompt}"
        return hashlib.sha256(key.encode('utf-8')).hexdigest()

    def get_cached_response(self, prompt: str, model_name: str):
        key = self._hash_key(prompt, model_name)
        with shelve.open(self.cache_path) as db:
            if key in db:
                return db[key]
        return None

    def store_response(self, prompt: str, model_name: str, response: str):
        key = self._hash_key(prompt, model_name)
        with shelve.open(self.cache_path) as db:
            db[key] = response


# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/ui/app.py
import os
from nicegui import ui, app
from llm.ollama_client import OllamaClient
from models.interaction import Interaction
from models.character import Character
from chats.chat_manager import ChatManager
import asyncio
import yaml
import uuid
from datetime import datetime

llm_client = None
chat_manager = None

user_input = None
chat_display = None
you_name_input = None
character_dropdown = None
added_characters_container = None  
next_speaker_label = None
next_button = None
settings_dropdown = None
session_dropdown = None

CHARACTERS_DIR = "src/multipersona_chat_app/characters"
ALL_CHARACTERS = {}
ALL_SETTINGS = []
DB_PATH = os.path.join("output", "conversations.db")

def load_settings():
    settings_path = os.path.join("src", "multipersona_chat_app", "config", "settings.yaml")
    try:
        with open(settings_path, 'r') as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, list) else []
    except:
        return []

def get_available_characters(directory):
    characters = {}
    try:
        for filename in os.listdir(directory):
            if filename.endswith('.yaml'):
                yaml_path = os.path.join(directory, filename)
                try:
                    char = Character.from_yaml(yaml_path)
                    characters[char.name] = char
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return characters

def init_chat_manager(session_id: str):
    global chat_manager, llm_client
    chat_manager = ChatManager(you_name="You", session_id=session_id)
    llm_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=Interaction)

def refresh_added_characters():
    added_characters_container.clear()
    for char_name in chat_manager.get_character_names():
        with added_characters_container:
            with ui.card().classes('p-2 flex items-center'):
                ui.label(char_name).classes('flex-grow')
                ui.button(
                    'Remove',
                    on_click=lambda _, name=char_name: remove_character(name),
                ).classes('ml-2 bg-red-500 text-white') 

def update_next_speaker_label():
    ns = chat_manager.next_speaker()
    if ns:
        next_speaker_label.text = f"Next speaker: {ns}"
    else:
        next_speaker_label.text = "No characters available."

def populate_session_dropdown():
    sessions = chat_manager.db.get_all_sessions()
    session_dropdown.options = [s['name'] for s in sessions]
    current = [s for s in sessions if s['session_id'] == chat_manager.session_id]
    if current:
        session_dropdown.value = current[0]['name']

def on_session_select(event):
    sessions = chat_manager.db.get_all_sessions()
    selected_name = event.value
    for s in sessions:
        if s['name'] == selected_name:
            load_session(s['session_id'])
            return

def create_new_session(_):
    new_id = str(uuid.uuid4())
    chat_manager.db.create_session(new_id, f"Session {new_id}")
    load_session(new_id)

def delete_session(_):
    sessions = chat_manager.db.get_all_sessions()
    if session_dropdown.value:
        to_delete = [s for s in sessions if s['name'] == session_dropdown.value]
        if to_delete:
            sid = to_delete[0]['session_id']
            chat_manager.db.delete_session(sid)
            # If current session is deleted, create a new one
            if sid == chat_manager.session_id:
                new_id = str(uuid.uuid4())
                chat_manager.db.create_session(new_id, f"Session {new_id}")
                load_session(new_id)
            else:
                populate_session_dropdown()

def load_session(session_id: str):
    global chat_manager
    you_name = chat_manager.you_name
    setting = chat_manager.current_setting
    chat_manager = ChatManager(you_name=you_name, session_id=session_id)
    chat_manager.set_current_setting(setting)
    refresh_added_characters()
    update_chat_display()
    update_next_speaker_label()
    populate_session_dropdown()

def select_setting(event):
    chosen_name = event.value
    for s in ALL_SETTINGS:
        if s['name'] == chosen_name:
            chat_manager.set_current_setting(s['description'])
            break

def toggle_automatic_chat(e):
    if e.value:
        if not chat_manager.get_character_names():
            chat_manager.add_message("System", "No characters added. Please add characters to start automatic chat.", visible=True, message_type="system")
            update_chat_display()
            e.value = False
            return
        chat_manager.start_automatic_chat()
    else:
        chat_manager.stop_automatic_chat()
    next_button.enabled = not chat_manager.automatic_running

def set_you_name(name: str):
    chat_manager.set_you_name(name)
    update_chat_display()

async def add_character_from_dropdown(event):
    if event.value:
        char_name = event.value
        char = ALL_CHARACTERS.get(char_name, None)
        if char:
            if char_name not in chat_manager.get_character_names():
                chat_manager.add_character(char_name, char)
                refresh_added_characters()
                await generate_character_introduction_message(char_name)
        update_chat_display()
        update_next_speaker_label()
        character_dropdown.value = None

def remove_character(name: str):
    chat_manager.remove_character(name)
    refresh_added_characters()
    update_chat_display()
    update_next_speaker_label()

async def automatic_conversation():
    while True:
        await asyncio.sleep(2)
        if chat_manager.automatic_running:
            next_char = chat_manager.next_speaker()
            if next_char:
                await generate_character_message(next_char)
                chat_manager.advance_turn()
                update_next_speaker_label()

async def next_character_response():
    if chat_manager.automatic_running:
        return
    next_char = chat_manager.next_speaker()
    if next_char:
        await generate_character_message(next_char)
        chat_manager.advance_turn()
        update_next_speaker_label()

async def generate_character_introduction_message(character_name: str):
    (system_prompt, user_prompt) = chat_manager.build_prompt_for_character(character_name)
    user_prompt += "\n\nYou have just arrived in the conversation. Introduce yourself, describing your physical appearance, attire, and how it fits with the setting and with any prior context that may be relevant."

    try:
        interaction = await asyncio.to_thread(llm_client.generate, prompt=user_prompt, system=system_prompt)
        if isinstance(interaction, Interaction):
            affect = interaction.affect
            purpose = interaction.purpose
            formatted_message = f"*{interaction.action}*\n{interaction.dialogue}"
        else:
            affect = None
            purpose = None
            formatted_message = str(interaction) if interaction else "No introduction."
    except Exception as e:
        formatted_message = f"Error generating introduction: {str(e)}"
        affect = None
        purpose = None

    chat_manager.add_message(character_name, formatted_message, visible=True, message_type="character", affect=affect, purpose=purpose)
    update_chat_display()

async def generate_character_message(character_name: str):
    (system_prompt, user_prompt) = chat_manager.build_prompt_for_character(character_name)

    try:
        interaction = await asyncio.to_thread(llm_client.generate, prompt=user_prompt, system=system_prompt)
        if isinstance(interaction, Interaction):
            affect = interaction.affect
            purpose = interaction.purpose
            formatted_message = f"*{interaction.action}*\n{interaction.dialogue}"
        else:
            affect = None
            purpose = None
            formatted_message = str(interaction) if interaction else "No response."
    except Exception as e:
        formatted_message = f"Error: {str(e)}"
        affect = None
        purpose = None

    chat_manager.add_message(character_name, formatted_message, visible=True, message_type="character", affect=affect, purpose=purpose)
    update_chat_display()

async def send_user_message():
    if not user_input.value:
        return

    chat_manager.add_message(chat_manager.you_name, user_input.value, visible=True, message_type="user")
    update_chat_display()
    user_input.value = ''
    user_input.update()

    if not chat_manager.automatic_running:
        update_next_speaker_label()

def update_chat_display():
    chat_display.clear()
    msgs = chat_manager.db.get_messages(chat_manager.session_id)
    for entry in msgs:
        name = entry["sender"]
        message = entry["message"]
        timestamp = entry["timestamp"]
        # Convert timestamp to a more human-friendly format
        dt = datetime.fromisoformat(timestamp)
        human_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
        formatted_message = f"**{name}** [{human_timestamp}]:\n\n{message}"
        with chat_display:
            ui.markdown(formatted_message)

def main_page():
    global user_input, chat_display, you_name_input, character_dropdown, added_characters_container, next_speaker_label, next_button, ALL_CHARACTERS, ALL_SETTINGS, settings_dropdown, session_dropdown

    ALL_CHARACTERS = get_available_characters(CHARACTERS_DIR)
    ALL_SETTINGS = load_settings()

    with ui.column().classes('w-full max-w-2xl mx-auto'):
        ui.label('Multipersona Chat Application').classes('text-2xl font-bold mb-4')

        # Session Management
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Session:").classes('w-1/4')
            session_dropdown = ui.select(
                options=[s['name'] for s in chat_manager.db.get_all_sessions()],
                label="Choose a session",
                on_change=on_session_select
            ).classes('flex-grow')

            ui.button("New Session", on_click=create_new_session).classes('ml-2')
            ui.button("Delete Session", on_click=delete_session).classes('ml-2 bg-red-500 text-white')

        # Configure "Your Name"
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Your name:").classes('w-1/4')
            you_name_input = ui.input(value=chat_manager.you_name).classes('flex-grow')
            ui.button("Set", on_click=lambda: set_you_name(you_name_input.value)).classes('ml-2')

        # Select Setting
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Select Setting:").classes('w-1/4')
            settings_dropdown = ui.select(
                options=[s['name'] for s in ALL_SETTINGS],
                on_change=select_setting,
                label="Choose a setting"
            ).classes('flex-grow')

        # Add Characters Dropdown
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Select Character:").classes('w-1/4')
            character_dropdown = ui.select(
                options=list(ALL_CHARACTERS.keys()),
                on_change=lambda e: asyncio.create_task(add_character_from_dropdown(e)),
                label="Choose a character"
            ).classes('flex-grow')

        # List of Added Characters
        with ui.column().classes('w-full mb-4'):
            ui.label("Added Characters:").classes('font-semibold mb-2')
            added_characters_container = ui.row().classes('flex-wrap gap-2')
            refresh_added_characters()

        # Toggle Automatic Chat
        with ui.row().classes('w-full items-center mb-4'):
            auto_switch = ui.switch('Automatic Chat', value=False, on_change=toggle_automatic_chat).classes('mr-2')
            ui.button("Stop", on_click=lambda: chat_manager.stop_automatic_chat()).classes('ml-auto')

        # Chat Display Area
        chat_display = ui.column().classes('space-y-2 p-4 bg-gray-100 rounded h-96 overflow-y-auto')

        # Next Speaker Label
        next_speaker_label = ui.label("Next speaker:").classes('text-sm text-gray-700')
        update_next_speaker_label()

        # Next Button (for manual progression)
        next_button = ui.button("Next", on_click=lambda: asyncio.create_task(next_character_response()))
        next_button.props('outline')
        next_button.enabled = not chat_manager.automatic_running

        # User Input Field and Send Button
        with ui.row().classes('w-full items-center mt-4'):
            user_input = ui.input(placeholder='Enter your message...').classes('flex-grow')
            ui.button('Send', on_click=lambda: asyncio.create_task(send_user_message())).classes('ml-2')

    app.on_startup(lambda: asyncio.create_task(automatic_conversation()))
    update_chat_display()
    populate_session_dropdown()

def start_ui():
    default_session = str(uuid.uuid4())
    cm_temp = ChatManager()
    sessions = cm_temp.db.get_all_sessions()
    if not sessions:
        cm_temp.db.create_session(default_session, f"Session {default_session}")
        init_chat_manager(default_session)
    else:
        init_chat_manager(sessions[0]['session_id'])

    main_page()
    ui.run(reload=False)


