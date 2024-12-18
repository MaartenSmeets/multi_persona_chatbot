# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/chats/chat_manager.py
import datetime
from typing import List, Dict, Tuple, Optional
from models.character import Character

class ChatManager:
    def __init__(self, you_name: str = "You"):
        self.characters: Dict[str, Character] = {}
        self.chat_history: List[Dict[str, any]] = []
        self.turn_index = 0
        self.automatic_running = False
        self.you_name = you_name

    def get_character_names(self) -> List[str]:
        return self.get_characters_in_order()

    def set_you_name(self, name: str):
        self.you_name = name

    def add_character(self, char_name: str, char_instance: Character):
        self.characters[char_name] = char_instance

    def remove_character(self, char_name: str):
        if char_name in self.characters:
            del self.characters[char_name]

    def get_characters_in_order(self) -> List[str]:
        return list(self.characters.keys())

    def next_speaker(self) -> Optional[str]:
        chars = self.get_characters_in_order()
        if not chars:
            return None
        return chars[self.turn_index % len(chars)]

    def advance_turn(self):
        chars = self.get_characters_in_order()
        if chars:
            self.turn_index = (self.turn_index + 1) % len(chars)

    def add_message(self, sender: str, message: str, visible: bool = True):
        self.chat_history.append({
            "sender": sender,
            "message": message,
            "timestamp": datetime.datetime.now(),
            "visible": visible
        })

    def get_visible_history(self) -> List[Tuple[str, str]]:
        return [(entry["sender"], entry["message"]) for entry in self.chat_history if entry["visible"]]

    def build_prompt_for_character(self, character_name: str) -> str:
        visible_history = self.get_visible_history()
        latest_dialogue = visible_history[-1][1] if visible_history else ""
        setting = "This is a shared conversation environment."
        chat_history_summary = "\n".join(f"{s}: {m}" for s, m in visible_history[:-1])

        char = self.characters[character_name]
        prompt = char.format_prompt(
            setting=setting,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_dialogue
        )
        return prompt

    def start_automatic_chat(self):
        self.automatic_running = True

    def stop_automatic_chat(self):
        self.automatic_running = False
