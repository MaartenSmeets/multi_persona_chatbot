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
        self.max_dialogue_length_before_summarization = self.config.get('max_dialogue_length_before_summarization', 10)

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
        # Initialize summary if not exists
        if not self.db.get_summary(self.session_id, char_name):
            self.db.save_summary(self.session_id, char_name, "")

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

    def add_message(self, sender: str, message: str, visible: bool = True, message_type: str = "user"):
        # Ignore system messages and thinking ("...") messages.
        if message_type == "system" or message.strip() == "...":
            return
        self.db.save_message(self.session_id, sender, message, visible, message_type)
        self.check_summarization()

    def get_visible_history(self) -> List[Tuple[str, str, str]]:
        msgs = self.db.get_messages(self.session_id)
        return [(m["sender"], m["message"], m["message_type"]) for m in msgs if m["visible"]]

    def build_prompt_for_character(self, character_name: str) -> Tuple[str, str]:
        visible_history = self.get_visible_history()
        latest_dialogue = visible_history[-1][1] if visible_history else ""
        chat_history_summary = self.db.get_summary(self.session_id, character_name)
        setting = self.current_setting

        char = self.characters[character_name]
        user_prompt = char.format_prompt(
            setting=setting,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_dialogue
        )
        # Include the system prompt template from the character
        system_prompt = char.system_prompt_template
        return (system_prompt, user_prompt)

    def start_automatic_chat(self):
        self.automatic_running = True

    def stop_automatic_chat(self):
        self.automatic_running = False

    def check_summarization(self):
        visible_history = self.get_visible_history()
        if len(visible_history) > self.max_dialogue_length_before_summarization:
            for char_name in self.characters:
                self.summarize_history_for_character(char_name)

    def summarize_history_for_character(self, character_name: str):
        msgs = self.db.get_messages(self.session_id)
        relevant_msgs = [(m["sender"], m["message"]) for m in msgs if m["visible"] and m["message_type"] != "system"]
        previous_summary = self.db.get_summary(self.session_id, character_name)

        history_text = "\n".join(f"{s}: {m}" for s, m in relevant_msgs)
        prompt = f"""
You are summarizing a conversation from the perspective of {character_name}. 
Focus only on what {character_name} knows, their feelings, their perceptions, and actions they observed.
If there is a previous summary, integrate it into the new summary.

Previous Summary:
{previous_summary}

New Events to Summarize:
{history_text}

Instructions:
- Provide a concise, high-quality summary that contains the most important information from {character_name}'s perspective.
- Include actions perceived by {character_name}, their own thoughts and feelings, and relevant conversation points.
- Do not include information about others' internal states unless {character_name} has perceived it.
- Keep it short and informative.
"""

        from llm.ollama_client import OllamaClient
        summarize_llm = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml')
        new_summary = summarize_llm.generate(prompt=prompt)
        if not new_summary:
            new_summary = previous_summary

        self.db.save_summary(self.session_id, character_name, new_summary)
