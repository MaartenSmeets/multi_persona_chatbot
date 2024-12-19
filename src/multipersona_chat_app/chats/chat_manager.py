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
