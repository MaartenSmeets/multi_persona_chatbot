import os
import logging
from typing import List, Dict, Tuple, Optional
from models.character import Character
from db.db_manager import DBManager
from llm.ollama_client import OllamaClient
from datetime import datetime
import yaml
from templates import INTRODUCTION_TEMPLATE
from models.interaction import Interaction

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
        else:
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

    @staticmethod
    def load_config(config_path: str) -> dict:
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
            return config if config else {}
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}")
            return {}

    @property
    def current_location(self) -> Optional[str]:
        return self.db.get_current_location(self.session_id)
    
    def set_current_setting(self, setting_name: str, setting_description: str, start_location: str):
        self.current_setting = setting_name
        self.db.update_current_setting(self.session_id, self.current_setting)
        self.db.update_current_location(self.session_id, start_location, None)
        logger.info(f"Setting changed to '{self.current_setting}'. (Global location updated for reference.)")

    def get_character_names(self) -> List[str]:
        return list(self.characters.keys())

    def set_you_name(self, name: str):
        self.you_name = name

    def add_character(self, char_name: str, char_instance: Character):
        self.characters[char_name] = char_instance
        current_session_loc = self.db.get_current_location(self.session_id) or ""
        self.db.add_character_to_session(self.session_id, char_name, initial_location=current_session_loc, initial_clothing=char_instance.appearance)
        # By default, we store the character's initial clothing as the "appearance" field from the YAML
        # This can be updated later when "new_clothing" events occur.

    def remove_character(self, char_name: str):
        if char_name in self.characters:
            del self.characters[char_name]
        self.db.remove_character_from_session(self.session_id, char_name)

    def next_speaker(self) -> Optional[str]:
        chars = self.get_character_names()
        if not chars:
            return None
        return chars[self.turn_index % len(chars)]

    def advance_turn(self):
        chars = self.get_character_names()
        if chars:
            self.turn_index = (self.turn_index + 1) % len(chars)

    def add_message(self, sender: str, message: str, visible: bool = True, message_type: str = "user",
                    affect: Optional[str] = None, purpose: Optional[str] = None) -> Optional[int]:
        if message_type == "system" or message.strip() == "...":
            return None
        message_id = self.db.save_message(self.session_id, sender, message, visible, message_type, affect, purpose)
        self.check_summarization()
        return message_id

    def get_visible_history(self):
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

        location = self.get_combined_location()
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

        system_prompt = (
            f"{char.system_prompt_template}\n\n"
            f"Appearance: {char.appearance}\n"
            f"Character Description: {char.character_description}\n"
            f"Guidelines: {morality_guidelines}\n\n"
        )

        user_prompt = char.format_prompt(
            setting=setting_description,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_dialogue,
            name=char.name,
            location=location
        )
        return (system_prompt, user_prompt)

    def build_introduction_prompts_for_character(self, character_name: str) -> Tuple[str, str]:
        char = self.characters[character_name]

        visible_history = self.get_visible_history()
        latest_dialogue = visible_history[-1][1] if visible_history else ""
        all_summaries = self.db.get_all_summaries(self.session_id, character_name)
        chat_history_summary = "\n\n".join(all_summaries) if all_summaries else ""

        if self.current_setting and self.current_setting in self.settings:
            setting_description = self.settings[self.current_setting]['description']
        else:
            setting_description = "A tranquil environment."

        session_loc = self.db.get_current_location(self.session_id) or ""
        if not session_loc and self.current_setting in self.settings:
            session_loc = self.settings[self.current_setting].get('start_location', '')

        morality_config_path = os.path.join("src", "multipersona_chat_app", "config", "morality_guidelines.yaml")
        try:
            with open(morality_config_path, 'r') as f:
                morality_data = yaml.safe_load(f)
                morality_guidelines_template = morality_data.get('morality_guidelines', "")
                morality_guidelines = morality_guidelines_template.replace("{name}", char.name)
        except Exception as e:
            logger.error(f"Failed to load morality guidelines for introduction: {e}")
            morality_guidelines = ""

        system_prompt = (
            f"{char.system_prompt_template}\n\n"
            f"Appearance: {char.appearance}\n"
            f"Character Description: {char.character_description}\n"
            f"Guidelines: {morality_guidelines}\n\n"
        )

        intro_prompt = INTRODUCTION_TEMPLATE.format(
            name=char.name,
            appearance=char.appearance,
            character_description=char.character_description,
            setting=setting_description,
            location=session_loc,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_dialogue
        )

        user_prompt = intro_prompt

        return system_prompt, user_prompt

    def get_combined_location(self) -> str:
        char_locs = self.db.get_all_character_locations(self.session_id)
        char_clothes = self.db.get_all_character_clothing(self.session_id)
        msgs = self.db.get_messages(self.session_id)
        participants = set(
            m["sender"] for m in msgs 
            if m["message_type"] in ["user", "character"]
        )

        if not participants:
            session_loc = self.db.get_current_location(self.session_id)
            if not session_loc and self.current_setting in self.settings:
                session_loc = self.settings[self.current_setting].get('start_location', '')
            if session_loc:
                return f"The setting is: {session_loc}"
            else:
                return "No characters present and no specific location known."

        parts = []
        for c_name in char_locs.keys():
            if c_name not in participants:
                continue
            c_loc = char_locs[c_name].strip()
            c_clothes = char_clothes.get(c_name, "").strip()
            if not c_loc and not c_clothes:
                parts.append(f"{c_name}'s location and clothing are unknown")
            elif c_loc and not c_clothes:
                parts.append(f"{c_name} is at {c_loc} (clothing status unknown)")
            elif not c_loc and c_clothes:
                parts.append(f"{c_name} is wearing: {c_clothes}, location unknown")
            else:
                parts.append(f"{c_name} is at {c_loc}, wearing: {c_clothes}")
        if not parts:
            session_loc = self.db.get_current_location(self.session_id)
            if not session_loc and self.current_setting in self.settings:
                session_loc = self.settings[self.current_setting].get('start_location', '')
            if session_loc:
                return f"The setting is: {session_loc}"
            else:
                return "No active character locations known."
        return " | ".join(parts)

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
        relevant_msgs = [
            (m["id"], m["sender"], m["message"], m["affect"], m.get("purpose", None))
            for m in msgs
            if m["visible"] and m["message_type"] != "system" and m["id"] > last_covered_id
        ]

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

        prompt = f"""You are summarizing the conversation from {character_name}'s perspective. Summarize only the newly presented events from these {self.to_summarize_count} recent messages.

Your summary must:
- Reflect only what {character_name} directly observes or experiences.
- Note any newly revealed behaviors, location changes, clothing changes, or expressed feelings from {character_name}'s own messages.
- Exclude repeated content that was previously summarized.
- Include location changes, new clothing, or new character introductions.

New events for {character_name} to summarize:
{history_text}
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

        if ids_to_hide:
            conn = self.db._ensure_connection()
            c = conn.cursor()
            placeholders = ",".join("?" * len(ids_to_hide))
            c.execute(f"UPDATE messages SET visible=0 WHERE id IN ({placeholders})", ids_to_hide)
            conn.commit()
            conn.close()

        logger.info(f"Summarized and concealed old messages for {character_name}, up to message ID {covered_up_to_message_id}.")

    def get_session_name(self) -> str:
        sessions = self.db.get_all_sessions()
        for session in sessions:
            if session['session_id'] == self.session_id:
                return session['name']
        return "Unnamed Session"

    def get_introduction_template(self) -> str:
        return INTRODUCTION_TEMPLATE

    async def handle_new_location_for_character(self, character_name: str, new_location: str, triggered_message_id: int):
        self.db.update_character_location(
            self.session_id,
            character_name,
            new_location,
            triggered_by_message_id=triggered_message_id
        )
        logger.info(f"Character '{character_name}' moved/updated location to '{new_location}'.")

    async def handle_new_clothing_for_character(self, character_name: str, new_clothing: str, triggered_message_id: int):
        self.db.update_character_clothing(
            self.session_id,
            character_name,
            new_clothing,
            triggered_by_message_id=triggered_message_id
        )
        logger.info(f"Character '{character_name}' updated clothing to '{new_clothing}'.")
