import os
import logging
from typing import List, Dict, Tuple, Optional
from models.character import Character
from db.db_manager import DBManager
from llm.ollama_client import OllamaClient
from datetime import datetime
import yaml
from templates import (
    INTRODUCTION_TEMPLATE,
    CHARACTER_INTRODUCTION_SYSTEM_PROMPT_TEMPLATE,
    CharacterIntroductionOutput
)
from models.interaction import Interaction, AppearanceSegments
from pydantic import BaseModel, Field
import utils
import json

import asyncio  # <-- used for async background calls

logger = logging.getLogger(__name__)

class InteractionValidationOutput(BaseModel):
    """
    A structured output to check if the interaction is valid according to
    the character's system prompt and dynamic prompt template. If not valid,
    we receive a corrected version.
    """
    is_valid: str
    corrected_interaction: Optional[Interaction] = None


#
# UPDATED Pydantic Model for Character Plans
#
from typing import List

class CharacterPlan(BaseModel):
    goal: str = ""
    steps: List[str] = []
    why_new_plan_goal: str = ""  # <-- New field for storing reason(s) behind a changed plan/goal


class ChatManager:
    def __init__(self, you_name: str = "You", session_id: Optional[str] = None, settings: List[Dict] = []):
        self.characters: Dict[str, Character] = {}
        self.turn_index = 0
        self.automatic_running = False
        self.you_name = you_name
        self.session_id = session_id if session_id else "default_session"
        # Store settings in a dict keyed by setting name
        self.settings = {setting['name']: setting for setting in settings}

        config_path = os.path.join("src", "multipersona_chat_app", "config", "chat_manager_config.yaml")
        self.config = self.load_config(config_path)

        # Summarization config
        self.summarization_threshold = self.config.get('summarization_threshold', 20)
        self.recent_dialogue_lines = self.config.get('recent_dialogue_lines', 5)
        self.to_summarize_count = self.summarization_threshold - self.recent_dialogue_lines

        # Validation loop config
        self.validation_loop_setting = self.config.get('validation_loop', 1)

        # New similarity threshold from config
        self.similarity_threshold = self.config.get("similarity_threshold", 0.8)

        db_path = os.path.join("output", "conversations.db")
        self.db = DBManager(db_path)

        existing_sessions = {s['session_id']: s for s in self.db.get_all_sessions()}
        if self.session_id not in existing_sessions:
            # Create a new session in the DB
            self.db.create_session(self.session_id, f"Session {self.session_id}")
            # Default to the first setting in the provided settings list if available
            if settings:
                default_setting = settings[0]
                self.set_current_setting(
                    default_setting['name'],
                    default_setting['description'],
                    default_setting['start_location']
                )
            else:
                self.current_setting = None
                logger.error("No settings available to set as default.")
        else:
            # The session already exists, check if there's a stored current setting
            stored_setting = self.db.get_current_setting(self.session_id)
            if stored_setting and stored_setting in self.settings:
                # Use the stored setting from the DB
                setting = self.settings[stored_setting]
                self.set_current_setting(
                    setting['name'],
                    setting['description'],
                    setting['start_location']
                )
            else:
                # If no valid stored setting, default to the first from the settings list
                if settings:
                    default_setting = settings[0]
                    self.set_current_setting(
                        default_setting['name'],
                        default_setting['description'],
                        default_setting['start_location']
                    )
                else:
                    self.current_setting = None
                    logger.error("No matching stored setting and no default setting found. No setting applied.")

    @staticmethod
    def load_config(config_path: str) -> dict:
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
            logger.info(f"Configuration loaded successfully from {config_path}")
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
        self.db.add_character_to_session(
            self.session_id,
            char_name,
            initial_location=current_session_loc,
            initial_appearance=char_instance.appearance
        )

        if char_instance.character_system_prompt and char_instance.dynamic_prompt_template:
            self.db.save_character_prompts(
                self.session_id,
                char_name,
                char_instance.character_system_prompt,
                char_instance.dynamic_prompt_template
            )
            logger.info(f"Stored system/dynamic prompts for '{char_name}' from YAML in DB.")
        else:
            logger.warning(f"No system/dynamic prompts found in YAML for '{char_name}'.")

        self.ensure_character_plan_exists(char_name)

    def remove_character(self, char_name: str):
        if char_name in self.characters:
            del self.characters[char_name]
        self.db.remove_character_from_session(self.session_id, char_name)

    def ensure_character_plan_exists(self, char_name: str):
        plan_data = self.db.get_character_plan(self.session_id, char_name)
        if plan_data is None:
            logger.info(f"No existing plan for '{char_name}'. Not creating any default plan.")
        else:
            logger.debug(f"Plan for '{char_name}' already exists in DB. Goal: {plan_data['goal']}")

    def get_character_plan(self, char_name: str) -> CharacterPlan:
        plan_data = self.db.get_character_plan(self.session_id, char_name)
        if plan_data:
            return CharacterPlan(
                goal=plan_data['goal'] or "",
                steps=plan_data['steps'] or [],
                why_new_plan_goal=plan_data.get('why_new_plan_goal', "")
            )
        else:
            return CharacterPlan()

    def save_character_plan(self, char_name: str, plan: CharacterPlan):
        self.db.save_character_plan(self.session_id, char_name, plan.goal, plan.steps, plan.why_new_plan_goal)

    def next_speaker(self) -> Optional[str]:
        chars = self.get_character_names()
        if not chars:
            return None

        all_msgs = self.db.get_messages(self.session_id)
        if not all_msgs:
            # If no conversation yet, default to the first added character
            return chars[0]

        last_speaker = all_msgs[-1]['sender']

        if last_speaker == self.you_name:
            return chars[0]

        if last_speaker in chars:
            idx = chars.index(last_speaker)
            next_idx = (idx + 1) % len(chars)
            return chars[next_idx]

        return chars[0]

    def advance_turn(self):
        # No-op placeholder for UI usage
        pass

    def get_visible_history_for_character(self, character_name: str) -> List[Dict]:
        return self.db.get_visible_messages_for_character(self.session_id, character_name)

    async def add_message(self,
                          sender: str,
                          message: str,
                          visible: bool = True,
                          message_type: str = "user",
                          affect: Optional[str] = None,
                          purpose: Optional[str] = None,
                          why_purpose: Optional[str] = None,
                          why_affect: Optional[str] = None,
                          why_action: Optional[str] = None,
                          why_dialogue: Optional[str] = None,
                          why_new_location: Optional[str] = None,
                          why_new_appearance: Optional[str] = None,
                          new_location: Optional[str] = None,
                          new_appearance: Optional[AppearanceSegments] = None
                         ) -> Optional[int]:
        if message_type == "system" or message.strip() == "...":
            return None

        hair_val = (new_appearance.hair.strip() if new_appearance and new_appearance.hair else "")
        cloth_val = (new_appearance.clothing.strip() if new_appearance and new_appearance.clothing else "")
        acc_val = (new_appearance.accessories_and_held_items.strip() if new_appearance and new_appearance.accessories_and_held_items else "")
        posture_val = (new_appearance.posture_and_body_language.strip() if new_appearance and new_appearance.posture_and_body_language else "")
        other_val = (new_appearance.other_relevant_details.strip() if new_appearance and new_appearance.other_relevant_details else "")

        message_id = self.db.save_message(
            self.session_id,
            sender,
            message,
            True,
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
            hair_val,
            cloth_val,
            acc_val,
            posture_val,
            other_val
        )

        self.db.add_message_visibility_for_session_characters(self.session_id, message_id)

        await self.check_summarization()

        return message_id

    async def check_summarization(self):
        all_msgs = self.db.get_messages(self.session_id)
        if not all_msgs:
            return

        participants = set(m["sender"] for m in all_msgs if m["message_type"] in ["user", "character"])
        for char_name in participants:
            if char_name not in self.characters:
                continue

            visible_for_char = self.db.get_visible_messages_for_character(self.session_id, char_name)
            if len(visible_for_char) >= self.summarization_threshold:
                await self.summarize_history_for_character(char_name)

    async def summarize_history_for_character(self, character_name: str):
        summarize_llm = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml')

        while True:
            msgs = self.db.get_visible_messages_for_character(self.session_id, character_name)
            if len(msgs) < self.summarization_threshold:
                break

            msgs.sort(key=lambda x: x['id'])
            chunk = msgs[: self.to_summarize_count]
            chunk_ids = [m['id'] for m in chunk]

            history_lines = []
            max_message_id_in_chunk = 0
            for m in chunk:
                mid = m["id"]
                sender = m["sender"]
                message = m["message"]
                affect = m.get("affect", None)
                purpose = m.get("purpose", None)
                why_purpose = m.get("why_purpose", None)
                why_affect = m.get("why_affect", None)
                why_action = m.get("why_action", None)
                why_dialogue = m.get("why_dialogue", None)
                why_new_location = m.get("why_new_location", None)
                why_new_appearance = m.get("why_new_appearance", None)

                if mid > max_message_id_in_chunk:
                    max_message_id_in_chunk = mid

                if sender == character_name:
                    line_parts = [f"{sender}:"]
                    line_parts.append(f"(Affect={affect}, Purpose={purpose})")
                    if why_purpose:
                        line_parts.append(f"why_purpose={why_purpose}")
                    if why_affect:
                        line_parts.append(f"why_affect={why_affect}")
                    if why_action:
                        line_parts.append(f"why_action={why_action}")
                    if why_dialogue:
                        line_parts.append(f"why_dialogue={why_dialogue}")
                    if why_new_location:
                        line_parts.append(f"why_new_location={why_new_location}")
                    if why_new_appearance:
                        line_parts.append(f"why_new_appearance={why_new_appearance}")

                    line_parts.append(f"Message={message}")
                    line = " | ".join(line_parts)
                else:
                    line = f"{sender}: {message}"

                history_lines.append(line)

            plan_changes_notes = []
            plan_changes = self.db.get_plan_changes_for_range(
                self.session_id,
                character_name,
                0,
                max_message_id_in_chunk
            )
            for pc in plan_changes:
                note = f"Plan changed (message {pc['triggered_by_message_id']}): {pc['change_summary']}"
                if 'why_new_plan_goal' in pc and pc['why_new_plan_goal']:
                    note += f" Reason: {pc['why_new_plan_goal']}"
                plan_changes_notes.append(note)

            plan_changes_text = ""
            if plan_changes_notes:
                plan_changes_text = (
                    "\n\nAdditionally, the following plan changes occurred:\n"
                    + "\n".join(plan_changes_notes)
                )

            history_text = "\n".join(history_lines) + plan_changes_text

            prompt = f"""You are creating a concise summary **from {character_name}'s perspective**.
Focus on newly revealed or changed details (feelings, location, appearance, important topic shifts, interpersonal dynamics).
Incorporate any 'why_*' information to clarify motivations or changes in mind/goals.
Also note any important plan changes or newly revealed steps in the plan. 
Avoid restating old environment details unless crucial changes occurred. Avoid redundancy and stay concise.

Messages to summarize:
{history_text}

Now produce a short summary from {character_name}'s viewpoint, emphasizing why changes happened when relevant.
"""

            new_summary = await asyncio.to_thread(summarize_llm.generate, prompt=prompt)
            if not new_summary:
                new_summary = "No significant new events."

            self.db.save_new_summary(self.session_id, character_name, new_summary, max_message_id_in_chunk)
            self.db.hide_messages_for_character(self.session_id, character_name, chunk_ids)

            logger.info(
                f"Summarized and concealed a block of {len(chunk)} messages for '{character_name}'. "
                f"Newest remaining count: {len(self.db.get_visible_messages_for_character(self.session_id, character_name))}."
            )

    def get_latest_dialogue(self, character_name: str) -> str:
        """
        We gather the last few visible lines of conversation from the perspective
        of `character_name`. The final line is tagged with "[Latest]" to highlight it.
        The speaker is clearly indicated for every line, ensuring clarity of who said what.
        """
        visible_history = self.get_visible_history_for_character(character_name)
        recent_msgs = visible_history[-self.recent_dialogue_lines:]

        formatted_dialogue_lines = []
        for i, msg in enumerate(recent_msgs):
            if msg['sender'] == self.you_name and msg['message_type'] == 'user':
                affect = msg.get('affect', 'N/A')
                purpose = msg.get('purpose', 'N/A')
                line = f"You [Affect: {affect}, Purpose: {purpose}]: {msg['message']}"
            else:
                line = f"{msg['sender']}: {msg['message']}"

            # For the final line, mark it clearly but retain the speaker's name
            if i == len(recent_msgs) - 1:
                line = f"{line} [Latest]"
            formatted_dialogue_lines.append(line)

        return "\n".join(formatted_dialogue_lines)

    def build_prompt_for_character(self, character_name: str) -> Tuple[str, str]:
        existing_prompts = self.db.get_character_prompts(self.session_id, character_name)
        if not existing_prompts:
            raise ValueError(f"Existing prompts not found in the session for '{character_name}'.")

        system_prompt = existing_prompts['character_system_prompt']
        dynamic_prompt_template = existing_prompts['dynamic_prompt_template']

        latest_dialogue = self.get_latest_dialogue(character_name)

        all_summaries = self.db.get_all_summaries(self.session_id, character_name)
        chat_history_summary = "\n\n".join(all_summaries) if all_summaries else ""

        setting_description = "A tranquil environment."
        if self.current_setting and self.current_setting in self.settings:
            setting_description = self.settings[self.current_setting]['description']

        location = self.get_combined_location()
        current_appearance = self.db.get_character_appearance(self.session_id, character_name)

        plan_obj = self.get_character_plan(character_name)
        steps_text = "\n".join(f"- {s}" for s in plan_obj.steps)
        plan_text = f"Goal: {plan_obj.goal}\nSteps:\n{steps_text}"

        try:
            formatted_prompt = dynamic_prompt_template
            formatted_prompt = formatted_prompt.replace("{setting}", setting_description)
            formatted_prompt = formatted_prompt.replace("{chat_history_summary}", chat_history_summary)
            formatted_prompt = formatted_prompt.replace("{latest_dialogue}", latest_dialogue)
            formatted_prompt = formatted_prompt.replace("{current_location}", location)
            formatted_prompt = formatted_prompt.replace("{current_appearance}", current_appearance)
            formatted_prompt = formatted_prompt.replace("{character_plan}", plan_text)
        except Exception as e:
            logger.error(f"Error replacing placeholders in dynamic_prompt_template: {e}")
            raise

        logger.debug(f"Built prompt for character '{character_name}':\n{formatted_prompt}")
        return system_prompt, formatted_prompt

    def build_introduction_prompts_for_character(self, character_name: str) -> Tuple[str, str]:
        char = self.characters[character_name]

        system_prompt = CHARACTER_INTRODUCTION_SYSTEM_PROMPT_TEMPLATE.format(
            character_name=char.name,
            character_description=char.character_description,
            appearance=char.appearance,
        )

        visible_history = self.get_visible_history_for_character(character_name)
        if visible_history:
            last_msg = visible_history[-1]
            latest_text = f"{last_msg['sender']}: {last_msg['message']} [Latest]"
        else:
            latest_text = ""

        all_summaries = self.db.get_all_summaries(self.session_id, character_name)
        chat_history_summary = "\n\n".join(all_summaries) if all_summaries else ""

        setting_description = "A tranquil environment."
        if self.current_setting and self.current_setting in self.settings:
            setting_description = self.settings[self.current_setting]['description']

        session_loc = self.db.get_current_location(self.session_id) or ""
        if not session_loc and self.current_setting in self.settings:
            session_loc = self.settings[self.current_setting].get('start_location', '')

        user_prompt = INTRODUCTION_TEMPLATE.format(
            name=character_name,
            character_name=character_name,
            appearance=char.appearance,
            character_description=char.character_description,
            setting=setting_description,
            location=session_loc,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_text,
            current_appearance=self.db.get_character_appearance(self.session_id, character_name)
        )
        return system_prompt, user_prompt

    def get_combined_location(self) -> str:
        char_locs = self.db.get_all_character_locations(self.session_id)
        char_apps = self.db.get_all_character_appearances(self.session_id)
        msgs = self.db.get_messages(self.session_id)
        participants = set(m["sender"] for m in msgs if m["message_type"] in ["user", "character"])

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
            c_app = char_apps.get(c_name, "").strip()
            if not c_loc and not c_app:
                logger.warning(f"Character '{c_name}' has no known location or appearance.")
            elif c_loc and not c_app:
                parts.append(f"{c_name}'s location: {c_loc}")
            elif not c_loc and c_app:
                parts.append(f"{c_name} has appearance: {c_app}")
            else:
                parts.append(f"{c_name}'s location: {c_loc}, appearance: {c_app}")
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

    async def generate_character_message(self, character_name: str):
        logger.info(f"Generating message for character: {character_name}")

        all_msgs = self.db.get_messages(self.session_id)
        triggered_message_id = all_msgs[-1]['id'] if all_msgs else None
        await self.update_character_plan(character_name, triggered_message_id)

        char_spoken_before = any(
            m for m in all_msgs
            if m["sender"] == character_name and m["message_type"] == "character"
        )
        if not char_spoken_before:
            await self.generate_character_introduction_message(character_name)
            return

        try:
            system_prompt, formatted_prompt = self.build_prompt_for_character(character_name)
            llm_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=Interaction)
            interaction = await asyncio.to_thread(
                llm_client.generate,
                prompt=formatted_prompt,
                system=system_prompt,
                use_cache=False
            )

            if not interaction:
                logger.warning(f"No response for {character_name}. Not storing.")
                return
            if not isinstance(interaction, Interaction):
                logger.error(f"Invalid interaction type from LLM: {type(interaction)}. Value: {interaction}")
                return

            # Validate & possibly correct
            validated = await self.validate_and_possibly_correct_interaction(
                character_name, system_prompt, formatted_prompt, interaction
            )
            if not validated:
                logger.warning(f"Interaction for {character_name} could not be validated or corrected. Not storing.")
                return

            # Check for repetitive lines
            final_interaction = await self.check_and_regenerate_if_repetitive(
                character_name, system_prompt, formatted_prompt, validated
            )
            if not final_interaction:
                logger.warning(f"Repetitive interaction could not be resolved for {character_name}.")
                # We fall back to the validated interaction
                final_interaction = validated

            final_interaction.action = utils.remove_markdown(final_interaction.action)
            final_interaction.dialogue = utils.remove_markdown(final_interaction.dialogue)


            formatted_message = f"*{final_interaction.action}*\n{final_interaction.dialogue.replace('[Latest]', '')}"
            msg_id = await self.add_message(
                character_name,
                formatted_message,
                visible=True,
                message_type="character",
                affect=final_interaction.affect,
                purpose=final_interaction.purpose,
                why_purpose=final_interaction.why_purpose,
                why_affect=final_interaction.why_affect,
                why_action=final_interaction.why_action,
                why_dialogue=final_interaction.why_dialogue,
                why_new_location=final_interaction.why_new_location,
                why_new_appearance=final_interaction.why_new_appearance,
                new_location=final_interaction.new_location.strip() if final_interaction.new_location.strip() else None,
                new_appearance=final_interaction.new_appearance
            )

            if final_interaction.new_location.strip():
                await self.handle_new_location_for_character(character_name, final_interaction.new_location, msg_id)
            if final_interaction.new_appearance and any([
                final_interaction.new_appearance.hair.strip(),
                final_interaction.new_appearance.clothing.strip(),
                final_interaction.new_appearance.accessories_and_held_items.strip(),
                final_interaction.new_appearance.posture_and_body_language.strip(),
                final_interaction.new_appearance.other_relevant_details.strip()
            ]):
                await self.handle_new_appearance_for_character(
                    character_name,
                    AppearanceSegments(
                        hair=final_interaction.new_appearance.hair,
                        clothing=final_interaction.new_appearance.clothing,
                        accessories_and_held_items=final_interaction.new_appearance.accessories_and_held_items,
                        posture_and_body_language=final_interaction.new_appearance.posture_and_body_language,
                        other_relevant_details=final_interaction.new_appearance.other_relevant_details
                    ),
                    msg_id
                )
        except Exception as e:
            logger.error(f"Error generating message for {character_name}: {e}", exc_info=True)

    async def generate_character_introduction_message(self, character_name: str):
        logger.info(f"Building introduction prompts for character: {character_name}")
        system_prompt, introduction_prompt = self.build_introduction_prompts_for_character(character_name)
        introduction_llm_client = OllamaClient(
            'src/multipersona_chat_app/config/llm_config.yaml',
            output_model=CharacterIntroductionOutput
        )

        try:
            introduction_response = await asyncio.to_thread(
                introduction_llm_client.generate,
                prompt=introduction_prompt,
                system=system_prompt
            )

            if isinstance(introduction_response, CharacterIntroductionOutput):
                intro_text = introduction_response.introduction_text.strip()
                app_seg = introduction_response.current_appearance
                loc = introduction_response.current_location.strip()

                msg_id = await self.add_message(
                    character_name,
                    intro_text,
                    visible=True,
                    message_type="character"
                )

                if loc:
                    await self.handle_new_location_for_character(character_name, loc, msg_id)

                new_app_segments = AppearanceSegments(
                    hair=app_seg.hair,
                    clothing=app_seg.clothing,
                    accessories_and_held_items=app_seg.accessories_and_held_items,
                    posture_and_body_language=app_seg.posture_and_body_language,
                    other_relevant_details=app_seg.other_relevant_details
                )
                await self.handle_new_appearance_for_character(character_name, new_app_segments, msg_id)

                logger.info(f"Saved introduction message for {character_name}")
            else:
                logger.warning(f"Invalid response received for introduction of {character_name}. Response: {introduction_response}")

        except Exception as e:
            logger.error(f"Error generating introduction for {character_name}: {e}", exc_info=True)


    def get_session_name(self) -> str:
        sessions = self.db.get_all_sessions()
        for session in sessions:
            if session['session_id'] == self.session_id:
                return session['name']
        return "Unnamed Session"

    def get_introduction_template(self) -> str:
        return INTRODUCTION_TEMPLATE

    async def handle_new_location_for_character(self, character_name: str, new_location: str, triggered_message_id: int):
        updated = self.db.update_character_location(
            self.session_id,
            character_name,
            new_location,
            triggered_by_message_id=triggered_message_id
        )
        if updated:
            logger.info(f"Character '{character_name}' location updated to '{new_location}'.")

    async def handle_new_appearance_for_character(self, character_name: str, new_appearance: AppearanceSegments, triggered_message_id: int) -> bool:
        updated = self.db.update_character_appearance(
            self.session_id,
            character_name,
            new_appearance,
            triggered_by_message_id=triggered_message_id
        )
        if updated:
            logger.info(f"Character '{character_name}' appearance updated: {new_appearance.dict()}")
        return updated

    def get_all_visible_messages(self) -> List[Dict]:
        visible_msgs = self.db.get_messages(self.session_id)
        return [m for m in visible_msgs if m["message_type"] in ("user","character","assistant","system")]

    async def validate_and_possibly_correct_interaction(
        self,
        character_name: str,
        system_prompt: str,
        dynamic_prompt: str,
        initial_interaction: Interaction
    ) -> Optional[Interaction]:
        if self.validation_loop_setting == 0:
            return initial_interaction

        validation_client = OllamaClient(
            'src/multipersona_chat_app/config/llm_config.yaml',
            output_model=InteractionValidationOutput
        )

        current_interaction = initial_interaction
        iteration = 0

        while True:
            iteration += 1
            validation_prompt = f"""You are checking if the following JSON interaction is valid according to the character's system prompt and dynamic prompt template.

System Prompt (character rules, guidelines):
{system_prompt}

Dynamic Prompt (with relevant context):
{dynamic_prompt}

The user-generated interaction JSON to validate:
{current_interaction.model_dump_json()}

Please reply in valid JSON format with the following fields:
{{
  "is_valid": "yes" or "no",
  "corrected_interaction": {{
      "purpose": "...",
      "why_purpose": "...",
      "affect": "...",
      "why_affect": "...",
      "action": "...",
      "why_action": "...",
      "dialogue": "...",
      "why_dialogue": "...",
      "new_location": "...",
      "why_new_location": "...",
      "new_appearance": {{
         "hair": "...",
         "clothing": "...",
         "accessories_and_held_items": "...",
         "posture_and_body_language": "...",
         "other_relevant_details": "..."
      }},
      "why_new_appearance": "..."
  }}
}}
- If is_valid is "yes", do NOT provide a corrected_interaction (or leave it empty).
- If is_valid is "no", provide a corrected_interaction with valid fields.

Only produce valid JSON with these two top-level keys: "is_valid" and "corrected_interaction". 
"""

            result = await asyncio.to_thread(
                validation_client.generate,
                prompt=validation_prompt,
                system=None,
                use_cache=False
            )

            if not result:
                if self.validation_loop_setting > 0 and iteration >= self.validation_loop_setting:
                    return None
                continue

            if isinstance(result, InteractionValidationOutput):
                validation_output = result
            else:
                try:
                    validation_output = InteractionValidationOutput.parse_raw(result)
                except Exception:
                    if self.validation_loop_setting > 0 and iteration >= self.validation_loop_setting:
                        return None
                    continue

            if validation_output.is_valid.lower() == "yes":
                return current_interaction

            corrected = validation_output.corrected_interaction
            if not corrected:
                if self.validation_loop_setting > 0 and iteration >= self.validation_loop_setting:
                    return None
                continue

            current_interaction = corrected
            if self.validation_loop_setting > 0 and iteration >= self.validation_loop_setting:
                return None

    #
    # NEW: check for repeated lines from the same character
    #
    async def check_and_regenerate_if_repetitive(
        self,
        character_name: str,
        system_prompt: str,
        dynamic_prompt: str,
        interaction: Interaction
    ) -> Optional[Interaction]:
        """
        We compare 'interaction.action' and 'interaction.dialogue' to the recent lines
        from the same speaker. If similarity >= self.similarity_threshold, we
        regenerate the interaction with an additional instruction to avoid repetition.
        We do up to 2 additional tries before giving up.
        """
        # 1) Gather the last N lines from the same speaker
        all_visible = self.db.get_visible_messages_for_character(self.session_id, character_name)
        # Filter out only the messages from this speaker (character_name)
        same_speaker_lines = [m for m in all_visible if m["sender"] == character_name]
        # We only need a handful of recent lines, let's take 5 or so
        recent_speaker_lines = same_speaker_lines[-5:] if len(same_speaker_lines) > 5 else same_speaker_lines

        # 2) We'll embed the new action and dialogue, compare each with the recent lines
        embed_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml')
        tries = 0
        max_tries = 2  # how many times we allow regeneration

        current_interaction = interaction

        while True:
            # Check similarity for action
            action_embedding = embed_client.get_embedding(current_interaction.action)
            is_action_similar = False
            # Check similarity for dialogue
            dialogue_embedding = embed_client.get_embedding(current_interaction.dialogue)
            is_dialogue_similar = False
            actiondialogue_embedding = embed_client.get_embedding(current_interaction.action+' '+current_interaction.dialogue)
            is_actiondialogue_similar = False

            for line_obj in recent_speaker_lines:
                old_msg = line_obj["message"]
                old_embedding = embed_client.get_embedding(old_msg)
                if old_embedding:
                    # Compare with action
                    sim_action = embed_client.compute_cosine_similarity(action_embedding, old_embedding)
                    if sim_action >= self.similarity_threshold:
                        is_action_similar = True
                    
                    # Compare with dialogue
                    sim_dialogue = embed_client.compute_cosine_similarity(dialogue_embedding, old_embedding)
                    if sim_dialogue >= self.similarity_threshold:
                        is_dialogue_similar = True
                    
                    # Compare combined
                    sim_actiondialogue = embed_client.compute_cosine_similarity(actiondialogue_embedding, old_embedding)
                    if sim_actiondialogue >= self.similarity_threshold:
                        is_actiondialogue_similar = True

            if not is_action_similar and not is_dialogue_similar and not is_actiondialogue_similar:
                logger.info("Similarity check passed! No repetition detected.")
                return current_interaction

            tries += 1
            if tries > max_tries:
                logger.warning("Exceeded maximum repetition regeneration attempts.")
                return None

            # We need to regenerate the interaction with an additional instruction
            repetition_warning = ""
            if (is_action_similar and is_dialogue_similar) or is_actiondialogue_similar:
                repetition_warning = "Your action AND dialogue are too similar to recent lines."
            elif is_action_similar:
                repetition_warning = "Your action is too similar to something you previously did."
            else:
                repetition_warning = "Your dialogue is too similar to something you previously said."

            logger.info(f"Similarity check not passed! Repetition detected: {repetition_warning}")

            extra_instruction = f"""
IMPORTANT: {repetition_warning}
The current suggestion includes the action: (“{current_interaction.action}”)
and the dialogue: (“{current_interaction.dialogue}”).
Please revise your next interaction so that it is clearly different from these,
avoids repetition, and moves the story forward.
"""

            # Let's append the extra instruction to the dynamic_prompt
            revised_prompt = dynamic_prompt + "\n\n" + extra_instruction

            regen_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=Interaction)
            new_interaction = await asyncio.to_thread(
                regen_client.generate,
                prompt=revised_prompt,
                system=system_prompt,
                use_cache=False
            )
            if not new_interaction or not isinstance(new_interaction, Interaction):
                logger.warning("No valid regeneration received; returning None.")
                return None

            # Validate again
            revalidated = await self.validate_and_possibly_correct_interaction(
                character_name, system_prompt, revised_prompt, new_interaction
            )
            if not revalidated:
                logger.warning("Regenerated interaction not valid. Trying again if tries remain.")
                current_interaction = new_interaction  # fallback
                continue

            current_interaction = revalidated

    #
    # Plan Updating
    #
    async def update_character_plan(self, character_name: str, triggered_message_id: Optional[int] = None):
        plan_client = OllamaClient(
            config_path='src/multipersona_chat_app/config/llm_config.yaml',
            output_model=CharacterPlan
        )

        existing_plan = self.get_character_plan(character_name)
        old_goal = existing_plan.goal
        old_steps = existing_plan.steps
        old_why = existing_plan.why_new_plan_goal

        current_appearance = self.db.get_character_appearance(self.session_id, character_name)
        character_description = self.characters[character_name].character_description

        system_prompt = f"""
You are an expert assistant in crafting and refining long-term plans for narrative characters. Your primary responsibility is to ensure that {character_name}'s plan is practical, achievable within hours or days, and tailored to their current context, including their location and appearance and recent events. Each plan consists of:

- A clear goal: The ultimate objective {character_name} seeks to achieve.
- Actionable steps: Specific, concrete, and sequential tasks (not numbered but ordered from first to last) that systematically progress {character_name} toward their goal.
- If the plan or goal has changed, a short explanation of why should be stored in the field: "why_new_plan_goal".

Your focus is to create plans that are logical, detailed, and aligned with the {character_name}’s circumstances.
"""

        user_prompt = f"""
**Character Name:** {character_name}
**Character description:** {character_description}

**Existing Plan:**
- **Goal:** {old_goal}
- **Steps:**
{''.join(f'  - {step}\n' for step in old_steps)}

**Context:**
- **Current Setting:** {self.current_setting}
- **Current Location:** {self.get_combined_location()}
- **Current Appearance:** {current_appearance}

**Latest Dialogue:**
{self.get_latest_dialogue(character_name)}

**Instructions:**
- Review {character_name}'s existing plan and the current context for {character_name}.
- Determine if {character_name}'s plan needs to be revised based on any changes.
- Ensure that the steps are actionable, concrete, sequential, and very important **start from the current location, appearance and [Latest] line**.
- By the final step, the goal should be achieved.
- If revisions are necessary:
    - The "goal" might change or remain the same. When the goal changes, revise the steps accordingly.
    - Modify the "steps" as needed by adding, removing, or updating them. Make sure starting from the current location, appearance and [Latest] line. Completed steps should be removed.
- Also provide a short explanation why {character_name} changes his steps/plan/goal in "why_new_plan_goal".

Update or confirm the plan if needed. Output strictly in JSON:

{{
"goal": "<string>",
"steps": [ "step1", "step2", ... ],
"why_new_plan_goal": "<short explanation here>"
}}

If no changes are needed, simply repeat the existing plan in the same JSON format (including "why_new_plan_goal" if relevant).
"""

        plan_result = await asyncio.to_thread(
            plan_client.generate,
            prompt=user_prompt,
            system=system_prompt,
            use_cache=False
        )

        if not plan_result:
            logger.warning("Plan update returned no result. Keeping existing plan.")
            return

        try:
            if isinstance(plan_result, CharacterPlan):
                new_plan: CharacterPlan = plan_result
            else:
                new_plan = CharacterPlan.model_validate_json(plan_result)

            new_goal = new_plan.goal
            new_steps = new_plan.steps
            new_why = new_plan.why_new_plan_goal.strip()

            if not new_why and ((new_goal != old_goal) or (new_steps != old_steps)):
                new_why = "Plan changed; no explanation provided."

            if (new_goal != old_goal) or (new_steps != old_steps) or (new_why != old_why):
                change_explanation = self.build_plan_change_summary(old_goal, old_steps, new_goal, new_steps)
                if new_why:
                    change_explanation += f" Additional reason: {new_why}"
                self.db.save_character_plan_with_history(
                    self.session_id,
                    character_name,
                    new_goal,
                    new_steps,
                    new_why,
                    triggered_message_id,
                    change_explanation
                )
            else:
                self.db.save_character_plan_with_history(
                    self.session_id,
                    character_name,
                    new_goal,
                    new_steps,
                    new_why,
                    triggered_message_id,
                    "No change in plan"
                )
        except Exception as e:
            logger.error(
                f"Failed to parse new plan for '{character_name}'. Keeping old plan. Error: {e}"
            )

    def build_plan_change_summary(self, old_goal: str, old_steps: List[str], new_goal: str, new_steps: List[str]) -> str:
        changes = []
        if old_goal != new_goal:
            changes.append(f"Goal changed from '{old_goal}' to '{new_goal}'.")
        if old_steps != new_steps:
            changes.append(f"Steps changed from {old_steps} to {new_steps}.")
        return " ".join(changes)
