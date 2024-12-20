# File: /home/maarten/multi_persona_chatbot/src/multipersona_chatbot/src/multipersona_chat_app/chats/chat_manager.py

from typing import List, Dict, Tuple, Optional
from models.character import Character
import os
import logging
import threading  # Added for threading
from typing import List, Dict, Tuple, Optional, Any

from db.db_manager import DBManager
from llm.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

class ChatManager:
    def __init__(self, you_name: str = "You", session_id: Optional[str] = None, settings: List[Dict] = []):
        self.characters: Dict[str, Character] = {}
        self.turn_index = 0
        self.automatic_running = False
        self.you_name = you_name
        self.session_id = session_id if session_id else "default_session"

        # Store settings in a dictionary for easy access
        self.settings = {setting['name']: setting for setting in settings}

        # Flag to prevent changing settings after initialization
        self.setting_locked = False

        config_path = os.path.join("src", "multipersona_chat_app", "config", "chat_manager_config.yaml")
        self.config = self.load_config(config_path)
        
        self.max_dialogue_length_before_summarization = self.config.get('max_dialogue_length_before_summarization', 20)
        self.lines_to_keep_after_summarization = self.config.get('lines_to_keep_after_summarization', 5)
        self.to_summarize_count = self.config.get('to_summarize_count', 15)

        db_path = os.path.join("output", "conversations.db")
        self.db = DBManager(db_path)

        existing_sessions = {s['session_id']: s for s in self.db.get_all_sessions()}
        if self.session_id not in existing_sessions:
            self.db.create_session(self.session_id, f"Session {self.session_id}")
            # Set default setting and location based on settings
            default_setting = self.settings.get("Default Setting")
            if default_setting:
                self.set_current_setting(
                    default_setting['name'],
                    default_setting['description'],
                    default_setting['start_location']
                )
            else:
                # Fallback if "Default Setting" is not found
                self.current_setting = "Default Setting"
                self.current_location = "Initial Location within Default Setting."
                self.db.update_current_setting(self.session_id, self.current_setting)
                self.db.update_current_location(self.session_id, self.current_location)
                self.setting_locked = True
        else:
            # Load existing setting and location from DB if available
            stored_setting = self.db.get_current_setting(self.session_id)
            if stored_setting:
                setting = self.settings.get(stored_setting)
                if setting:
                    self.set_current_setting(
                        setting['name'],
                        setting['description'],
                        setting['start_location']
                    )
                else:
                    # If stored setting not found in current settings
                    self.current_setting = stored_setting
                    self.current_location = "Initial Location within " + self.current_setting
                    self.db.update_current_location(self.session_id, self.current_location)
                    self.setting_locked = True
            else:
                # If no setting is stored, set to default
                default_setting = self.settings.get("Default Setting")
                if default_setting:
                    self.set_current_setting(
                        default_setting['name'],
                        default_setting['description'],
                        default_setting['start_location']
                    )
                else:
                    self.current_setting = "Default Setting"
                    self.current_location = "Initial Location within Default Setting."
                    self.db.update_current_setting(self.session_id, self.current_setting)
                    self.db.update_current_location(self.session_id, self.current_location)
                    self.setting_locked = True

    @staticmethod
    def load_config(config_path: str) -> dict:
        try:
            import yaml
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
            return config if config else {}
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}")
            return {}

    def set_current_setting(self, setting_name: str, setting_description: str, start_location: str):
        """Set the current setting and initialize the current location based on start_location."""
        if self.setting_locked:
            if self.current_setting != setting_name:
                logger.error("Attempted to change setting after initialization. Operation denied.")
                raise PermissionError("Cannot change setting after initialization.")
            else:
                logger.debug("Setting is already locked and matches the requested setting. No action taken.")
                return

        self.current_setting = setting_name
        self.db.update_current_setting(self.session_id, self.current_setting)

        self.current_location = start_location
        self.db.update_current_location(self.session_id, self.current_location)
        logger.info(f"Setting changed to '{self.current_setting}' with start location '{self.current_location}'.")

        # Lock the setting after it has been set once
        self.setting_locked = True
        logger.debug("Setting has been locked and cannot be changed further.")

    def set_current_location(self, new_location: str, triggered_by_message_id: Optional[int] = None):
        """Update the current location and log the change in location history."""
        self.current_location = new_location
        self.db.update_current_location(self.session_id, self.current_location, triggered_by_message_id)
        logger.info(f"Location updated to: {self.current_location}")

    def get_location_history(self) -> List[Dict[str, Any]]:
        """Retrieve the location history for the current session."""
        return self.db.get_location_history(self.session_id)

    def get_character_names(self) -> List[str]:
        """Get a list of all added character names."""
        return list(self.characters.keys())

    def set_you_name(self, name: str):
        """Set the user's name."""
        self.you_name = name

    def add_character(self, char_name: str, char_instance: Character):
        """Add a new character to the chat."""
        self.characters[char_name] = char_instance

    def remove_character(self, char_name: str):
        """Remove a character from the chat."""
        if char_name in self.characters:
            del self.characters[char_name]

    def next_speaker(self) -> Optional[str]:
        """Determine the next speaker based on turn index."""
        chars = self.get_character_names()
        if not chars:
            return None
        return chars[self.turn_index % len(chars)]

    def advance_turn(self):
        """Advance the turn index to the next character."""
        chars = self.get_character_names()
        if chars:
            self.turn_index = (self.turn_index + 1) % len(chars)

    def add_message(self, sender: str, message: str, visible: bool = True, message_type: str = "user", affect: Optional[str]=None, purpose: Optional[str]=None) -> Optional[int]:
        """
        Add a message to the database. If the message contains a location change command,
        update the current location accordingly.
        Returns the message ID if saved, else None.
        """
        # Ignore system messages and thinking ("...") messages.
        if message_type == "system" or message.strip() == "...":
            return None
        message_id = self.db.save_message(self.session_id, sender, message, visible, message_type, affect, purpose)
        self.check_summarization()
        # If the message contains a location change command, handle it
        if self.is_location_change_message(message):
            new_location = self.extract_new_location(message)
            if new_location:
                self.set_current_location(new_location, triggered_by_message_id=message_id)
                logger.info(f"Location changed to '{new_location}' by message ID {message_id}")
        return message_id

    def is_location_change_message(self, message: str) -> bool:
        """
        Determine if the message contains a location change command.
        This is a simple implementation; you may need a more sophisticated parser.
        For example, you could define a specific syntax or keywords to indicate a location change.
        """
        # Example: messages starting with "/move " indicate a location change
        return message.lower().startswith("/move ")

    def extract_new_location(self, message: str) -> Optional[str]:
        """
        Extract the new location from the message.
        For example, if the message is "/move to the garden", it extracts "to the garden".
        """
        if self.is_location_change_message(message):
            return message[6:].strip()  # Remove "/move " prefix
        return None

    def get_visible_history(self) -> List[Tuple[str, str, str, Optional[str], int]]:
        """
        Retrieve all visible messages for the current session.
        Returns a list of tuples containing sender, message, message_type, affect, and message_id.
        """
        msgs = self.db.get_messages(self.session_id)
        return [(m["sender"], m["message"], m["message_type"], m["affect"], m["id"])
                for m in msgs if m["visible"]]

    def build_prompt_for_character(self, character_name: str) -> Tuple[str, str]:
        """
        Build the system and user prompts for a character based on the current session state.
        """
        visible_history = self.get_visible_history()
        latest_dialogue = visible_history[-1][1] if visible_history else ""

        all_summaries = self.db.get_all_summaries(self.session_id, character_name)
        chat_history_summary = "\n\n".join(all_summaries) if all_summaries else ""

        setting = self.current_setting
        location = self.current_location
        char = self.characters[character_name]
        user_prompt = char.format_prompt(
            setting=setting,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_dialogue
        )
        system_prompt = char.system_prompt_template
        return (system_prompt, user_prompt)

    def start_automatic_chat(self):
        """Start the automatic chat feature."""
        self.automatic_running = True

    def stop_automatic_chat(self):
        """Stop the automatic chat feature."""
        self.automatic_running = False

    def check_summarization(self):
        """Check if summarization is needed for each character."""
        for char_name in self.characters:
            self.summarize_history_for_character(char_name)

    def summarize_history_for_character(self, character_name: str):
        """
        Summarize the conversation history for a specific character.
        This helps in maintaining a concise context for the LLM.
        """
        msgs = self.db.get_messages(self.session_id)
        last_covered_id = self.db.get_latest_covered_message_id(self.session_id, character_name)
        relevant_msgs = [(m["id"], m["sender"], m["message"], m["affect"], m.get("purpose", None))
                        for m in msgs if m["visible"] and m["message_type"] != "system" and m["id"] > last_covered_id]

        if len(relevant_msgs) < self.max_dialogue_length_before_summarization:
            return

        to_summarize = relevant_msgs[:self.to_summarize_count]
        covered_up_to_message_id = to_summarize[-1][0] if to_summarize else last_covered_id

        history_lines = []
        for (mid, sender, message, affect, purpose) in to_summarize:
            if sender == character_name:
                line = f"{sender} (own affect: {affect}, own purpose: {purpose}): {message}"
            else:
                line = f"{sender}: {message}"
            history_lines.append(line)

        history_text = "\n".join(history_lines)

        prompt = f"""
You are summarizing a conversation from the perspective of {character_name}.
Focus on what {character_name} knows, their own feelings (affect) from their messages, their observed actions, their stated purpose, and relevant events.
Do not include internal states or purposes of others unless physically evident.
Do not restate older summarized content; focus only on these new events from these {self.to_summarize_count} messages.

New Events to Summarize (for {character_name}):
{history_text}

Instructions:
- Provide a concise, high-quality summary chunk containing the most important new information from {character_name}'s perspective.
- Include references to {character_name}'s own purpose and affect as revealed in their messages.
- Keep it short, focusing on notable changes, attempts to fulfill purpose, and new developments.
"""

        summarize_llm = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml')
        new_summary = summarize_llm.generate(prompt=prompt)
        if not new_summary:
            new_summary = "No significant new events."

        self.db.save_new_summary(self.session_id, character_name, new_summary, covered_up_to_message_id)

        to_hide_ids = [m[0] for m in to_summarize]
        if len(to_hide_ids) > self.lines_to_keep_after_summarization:
            ids_to_hide = to_hide_ids[:-self.lines_to_keep_after_summarization]
        else:
            ids_to_hide = to_hide_ids[:]

        conn = self.db._ensure_connection()
        c = conn.cursor()
        if ids_to_hide:
            placeholders = ",".join("?" * len(ids_to_hide))
            c.execute(f"UPDATE messages SET visible=0 WHERE id IN ({placeholders})", ids_to_hide)
        conn.commit()
        conn.close()

        logger.info(f"Summarized and adjusted visibility for old messages for {character_name}, up to message ID {covered_up_to_message_id}.")

    def get_session_name(self) -> str:
        """
        Retrieve the name of the current session based on session_id.
        """
        sessions = self.db.get_all_sessions()
        for session in sessions:
            if session['session_id'] == self.session_id:
                return session['name']

        return "Unnamed Session"
