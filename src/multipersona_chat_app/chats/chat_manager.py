import os
import logging
from typing import List, Dict, Tuple, Optional, Any
from models.character import Character
from db.db_manager import DBManager
from llm.ollama_client import OllamaClient
from datetime import datetime
import yaml
from templates import INTRODUCTION_TEMPLATE

logger = logging.getLogger(__name__)

class ChatManager:
    def __init__(self, you_name: str = "You", session_id: Optional[str] = None, settings: List[Dict] = []):
        self.characters: Dict[str, Character] = {}
        self.turn_index = 0
        self.automatic_running = False
        self.you_name = you_name
        self.session_id = session_id if session_id else "default_session"
        self.settings = {setting['name']: setting for setting in settings}

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
            intimate_setting = self.settings.get("Intimate Setting")
            if intimate_setting:
                self.set_current_setting(
                    intimate_setting['name'],
                    intimate_setting['description'],
                    intimate_setting['start_location']
                )
            else:
                logger.error("'Intimate Setting' not found in provided settings. No default setting will be applied.")
                self.current_setting = None
                self.current_location = None
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
                    intimate_setting = self.settings.get("Intimate Setting")
                    if intimate_setting:
                        self.set_current_setting(
                            intimate_setting['name'],
                            intimate_setting['description'],
                            intimate_setting['start_location']
                        )
                    else:
                        logger.error("No matching stored setting and 'Intimate Setting' not found.")
                        self.current_setting = stored_setting
                        self.current_location = "Initial Location within " + self.current_setting
                        self.db.update_current_setting(self.session_id, self.current_setting)
                        self.db.update_current_location(self.session_id, self.current_location, None)
            else:
                intimate_setting = self.settings.get("Intimate Setting")
                if intimate_setting:
                    self.set_current_setting(
                        intimate_setting['name'],
                        intimate_setting['description'],
                        intimate_setting['start_location']
                    )
                else:
                    logger.error("'Intimate Setting' not found. No setting applied.")
                    self.current_setting = None
                    self.current_location = None

    @staticmethod
    def load_config(config_path: str) -> dict:
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
            return config if config else {}
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}")
            return {}

    def set_current_setting(self, setting_name: str, setting_description: str, start_location: str):
        self.current_setting = setting_name
        self.db.update_current_setting(self.session_id, self.current_setting)
        self.current_location = start_location
        self.db.update_current_location(self.session_id, self.current_location, None)
        logger.info(f"Setting changed to '{self.current_setting}' with start location '{self.current_location}'.")

    def set_current_location(self, new_location: str, triggered_by_message_id: Optional[int] = None):
        self.current_location = new_location
        self.db.update_current_location(self.session_id, self.current_location, triggered_by_message_id)
        logger.info(f"Location updated to: {self.current_location}")

    def get_location_history(self) -> str:
        history_entries = self.db.get_location_history(self.session_id)
        if not history_entries:
            return "No location changes yet."
        history = []
        msgs = self.db.get_messages(self.session_id)
        for entry in history_entries:
            changed_at = datetime.fromisoformat(entry["changed_at"]).strftime('%Y-%m-%d %H:%M:%S')
            if entry["triggered_by_message_id"]:
                msg = next((m for m in msgs if m['id'] == entry["triggered_by_message_id"]), None)
                sender_name = msg['sender'] if msg else "Unknown"
                message = msg['message'] if msg else "Unknown message."
                history.append(f"**{entry['location']}** at {changed_at} by **{sender_name}**: _{message}_")
            else:
                history.append(f"**{entry['location']}** at {changed_at} by **System**")
        return "\n".join(history)

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

    def add_message(self, sender: str, message: str, visible: bool = True, message_type: str = "user", affect: Optional[str]=None, purpose: Optional[str]=None) -> Optional[int]:
        if message_type == "system" or message.strip() == "...":
            return None
        message_id = self.db.save_message(self.session_id, sender, message, visible, message_type, affect, purpose)
        self.check_summarization()
        return message_id

    def get_visible_history(self) -> List[Tuple[str, str, str, Optional[str], int]]:
        msgs = self.db.get_messages(self.session_id)
        return [(m["sender"], m["message"], m["message_type"], m["affect"], m["id"])
                for m in msgs if m["visible"]]

    def build_prompt_for_character(self, character_name: str) -> Tuple[str, str]:
        visible_history = self.get_visible_history()
        latest_dialogue = visible_history[-1][1] if visible_history else ""
        all_summaries = self.db.get_all_summaries(self.session_id, character_name)
        chat_history_summary = "\n\n".join(all_summaries) if all_summaries else ""

        if self.current_setting and self.current_setting in self.settings:
            setting_description = self.settings[self.current_setting]['description']
        else:
            setting_description = "A tranquil environment."

        location = self.current_location if self.current_location else "An unspecified location."
        char = self.characters[character_name]

        # Load morality guidelines
        morality_config_path = os.path.join("src", "multipersona_chat_app", "config", "morality_guidelines.yaml")
        try:
            with open(morality_config_path, 'r') as f:
                morality_data = yaml.safe_load(f)
                morality_guidelines_template = morality_data.get('morality_guidelines', "")
                morality_guidelines = morality_guidelines_template.replace("{name}", char.name)
        except Exception as e:
            logger.error(f"Failed to load morality guidelines: {e}")
            morality_guidelines = ""

        # Prepend morality guidelines to the system prompt
        system_prompt = (
            f"{morality_guidelines}\n\n"
            f"{char.system_prompt_template}\n\n"
            f"Appearance: {char.appearance}\n"
            f"Character Description: {char.character_description}\n"
        )

        user_prompt = char.format_prompt(
            setting=setting_description,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_dialogue,
            name=char.name,
            location=location
        )
        return (system_prompt, user_prompt)

    def start_automatic_chat(self):
        self.automatic_running = True

    def stop_automatic_chat(self):
        self.automatic_running = False

    def check_summarization(self):
        for char_name in self.characters:
            self.summarize_history_for_character(char_name)

    def summarize_history_for_character(self, character_name: str):
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



        prompt = f"""You are summarizing the conversation from the perspective of {character_name}. Summarize only the newly presented events from these {self.to_summarize_count} recent messages.

Your summary should:

- Focus on what {character_name} directly observes, knows, or experiences.
- Highlight {character_name}’s own visible actions, stated goals, and expressed feelings (affect) from their own messages.
- Include only behavior and information that is manifestly evident (no guessing about others’ internal states or motives).
- Omit previously summarized content; capture only the new developments introduced within these {self.to_summarize_count} messages.
- Ensure that if any subtle changes occurred (even if minimal), they are noted. It cannot be “nothing happened.” or "No significant new events."

New Events to Summarize (for {character_name}):
{history_text}

Instructions:
- Produce a concise but rich summary of these new events.
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
        sessions = self.db.get_all_sessions()
        for session in sessions:
            if session['session_id'] == self.session_id:
                return session['name']
        return "Unnamed Session"

    def get_introduction_template(self) -> str:
        return INTRODUCTION_TEMPLATE
