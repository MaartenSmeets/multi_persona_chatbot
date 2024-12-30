# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/chats/chat_manager.py

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
from models.interaction import Interaction
from pydantic import BaseModel, Field
import json

import asyncio  # <-- added for async background calls

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

        # Summarization config
        self.summarization_threshold = self.config.get('summarization_threshold', 20)
        self.recent_dialogue_lines = self.config.get('recent_dialogue_lines', 5)
        self.to_summarize_count = self.summarization_threshold - self.recent_dialogue_lines

        self.validation_loop_setting = self.config.get('validation_loop', 1)

        db_path = os.path.join("output", "conversations.db")
        self.db = DBManager(db_path)

        existing_sessions = {s['session_id']: s for s in self.db.get_all_sessions()}
        if self.session_id not in existing_sessions:
            self.db.create_session(self.session_id, f"Session {self.session_id}")
            # Default to "Intimate Setting" if available
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

        # Ensure we do NOT assign a default plan; only create if it exists
        self.ensure_character_plan_exists(char_name)

    def remove_character(self, char_name: str):
        if char_name in self.characters:
            del self.characters[char_name]
        self.db.remove_character_from_session(self.session_id, char_name)

    def ensure_character_plan_exists(self, char_name: str):
        """
        Check if character plan is present in DB; if not, do nothing.
        """
        plan_data = self.db.get_character_plan(self.session_id, char_name)
        if plan_data is None:
            logger.info(f"No existing plan for '{char_name}'. Not creating any default plan.")
        else:
            logger.debug(f"Plan for '{char_name}' already exists in DB. Goal: {plan_data['goal']}")

    def get_character_plan(self, char_name: str) -> CharacterPlan:
        plan_data = self.db.get_character_plan(self.session_id, char_name)
        if plan_data:
            return CharacterPlan(goal=plan_data['goal'] or "", steps=plan_data['steps'] or [])
        else:
            return CharacterPlan()

    def save_character_plan(self, char_name: str, plan: CharacterPlan):
        self.db.save_character_plan(self.session_id, char_name, plan.goal, plan.steps)

    def next_speaker(self) -> Optional[str]:
        chars = self.get_character_names()
        if not chars:
            return None
        return chars[self.turn_index % len(chars)]

    def advance_turn(self):
        chars = self.get_character_names()
        if chars:
            self.turn_index = (self.turn_index + 1) % len(chars)

    #
    # CHANGE: 'add_message' is now async to avoid blocking when we do summarization.
    #
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
                          new_appearance: Optional[str] = None) -> Optional[int]:

        if message_type == "system" or message.strip() == "...":
            return None

        message_id = self.db.save_message(
            self.session_id,
            sender,
            message,
            visible,
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
            new_appearance
        )

        # Kick off summarization in the background
        await self.check_summarization()

        return message_id

    def get_visible_history(self):
        summaries = self.db.get_all_summaries(self.session_id, None)
        visible_msgs = self.db.get_messages(self.session_id)
        recent_msgs = visible_msgs[-self.recent_dialogue_lines:]
        history = summaries + [m for m in recent_msgs if m["visible"]]
        logger.debug(f"Retrieved {len(history)} messages for visible history.")
        return history

    def build_prompt_for_character(self, character_name: str) -> Tuple[str, str]:
        existing_prompts = self.db.get_character_prompts(self.session_id, character_name)
        if not existing_prompts:
            raise ValueError(f"Existing prompts not found in the session for '{character_name}'.")

        system_prompt = existing_prompts['character_system_prompt']
        dynamic_prompt_template = existing_prompts['dynamic_prompt_template']

        visible_history = self.get_visible_history()
        recent_msgs = visible_history[-self.recent_dialogue_lines:]

        formatted_dialogue_lines = []
        for msg in recent_msgs:
            if msg['sender'] == self.you_name and msg['message_type'] == 'user':
                affect = msg.get('affect', 'N/A')
                purpose = msg.get('purpose', 'N/A')
                line = f"You [Affect: {affect}, Purpose: {purpose}]: {msg['message']}"
            else:
                line = f"{msg['sender']}: {msg['message']}"
            formatted_dialogue_lines.append(line)

        if formatted_dialogue_lines:
            formatted_dialogue_lines[-1] = f"### Latest Dialogue Line:\n{formatted_dialogue_lines[-1]}"

        latest_dialogue = "\n".join(formatted_dialogue_lines)

        all_summaries = self.db.get_all_summaries(self.session_id, character_name)
        chat_history_summary = "\n\n".join(all_summaries) if all_summaries else ""

        setting_description = "A tranquil environment."
        if self.current_setting and self.current_setting in self.settings:
            setting_description = self.settings[self.current_setting]['description']

        location = self.get_combined_location()
        current_appearance = self.db.get_character_appearance(self.session_id, character_name)

        # Insert the existing plan
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

        visible_history = self.get_visible_history()
        latest_dialogue = visible_history[-1]['message'] if visible_history else ""
        
        if latest_dialogue:
            latest_dialogue = f"### Latest Dialogue Line:\n{latest_dialogue}"

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
            latest_dialogue=latest_dialogue,
            current_appearance=self.db.get_character_appearance(self.session_id, character_name)
        )
        return system_prompt, user_prompt

    def get_combined_location(self) -> str:
        char_locs = self.db.get_all_character_locations(self.session_id)
        char_apps = self.db.get_all_character_appearances(self.session_id)
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
            c_app = char_apps.get(c_name, "").strip()
            if not c_loc and not c_app:
                logger.warning(f"Character '{c_name}' has no known location or appearance.")
            elif c_loc and not c_app:
                parts.append(f"{c_name}'s location: {c_loc}")
                logger.warning(f"Character '{c_name}' has no known appearance.")
            elif not c_loc and c_app:
                parts.append(f"{c_name} has appearance: {c_app}")
                logger.warning(f"Character '{c_name}' has no known location.")
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

    #
    # CHANGE: 'check_summarization' is now async; it calls 'await' on summarize_history_for_character.
    #
    async def check_summarization(self):
        for char_name in self.characters:
            await self.summarize_history_for_character(char_name)

    #
    # CHANGE: 'summarize_history_for_character' is now async so we can run the LLM call in a background thread.
    #
    async def summarize_history_for_character(self, character_name: str):
        msgs = self.db.get_messages(self.session_id)
        last_covered_id = self.db.get_latest_covered_message_id(self.session_id, character_name)
        relevant_msgs = [
            (m["id"], m["sender"], m["message"], m["affect"], m.get("purpose", None))
            for m in msgs
            if m["visible"] and m["message_type"] != "system" and m["id"] > last_covered_id
        ]

        logger.debug(f"Summarizing history for '{character_name}'. Total relevant messages: {len(relevant_msgs)} (threshold: {self.summarization_threshold})")

        if len(relevant_msgs) < self.summarization_threshold:
            logger.debug(f"Not enough messages to summarize for '{character_name}'. Required: {self.summarization_threshold}, available: {len(relevant_msgs)}.")
            return

        to_summarize = relevant_msgs[:self.to_summarize_count]
        covered_up_to_message_id = to_summarize[-1][0] if to_summarize else last_covered_id

        logger.debug(f"Messages to summarize for '{character_name}': {len(to_summarize)}. Covering up to message ID: {covered_up_to_message_id}.")

        history_lines = []
        for (mid, sender, message, affect, purpose) in to_summarize:
            if sender == character_name:
                line = f"{sender} (Affect: {affect}, Purpose: {purpose}): {message}"
            else:
                line = f"{sender}: {message}"
            history_lines.append(line)

        history_text = "\n".join(history_lines)

        prompt = f"""You are summarizing the conversation **from {character_name}'s perspective**. 
Focus on newly revealed or changed details (feelings, location, appearance, important topic shifts, interpersonal dynamics).
Do **not** restate the entire environment or old details. Keep it concise and relevant to what {character_name} newly learns or experiences.

Recent events to summarize:
{history_text}

Now produce a short summary from {character_name}'s viewpoint.
"""

        logger.debug(f"Summarization prompt for '{character_name}':\n{prompt}")

        # Use background thread for LLM call
        summarize_llm = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml')
        new_summary = await asyncio.to_thread(summarize_llm.generate, prompt=prompt)

        logger.debug(f"Summarization response for '{character_name}': {new_summary}")

        if not new_summary:
            new_summary = "No significant new events."

        self.db.save_new_summary(self.session_id, character_name, new_summary, covered_up_to_message_id)

        # Hide old messages from the visible log, except for recent_dialogue_lines
        to_hide_ids = [m[0] for m in to_summarize]
        if len(to_hide_ids) > self.recent_dialogue_lines:
            ids_to_hide = to_hide_ids[:-self.recent_dialogue_lines]
        else:
            ids_to_hide = to_hide_ids[:]

        if ids_to_hide:
            conn = self.db._ensure_connection()
            c = conn.cursor()
            placeholders = ",".join("?" * len(ids_to_hide))
            try:
                c.execute(f"UPDATE messages SET visible=0 WHERE id IN ({placeholders})", ids_to_hide)
                conn.commit()
                logger.debug(f"Hid message IDs for '{character_name}': {ids_to_hide}")
            except Exception as e:
                logger.error(f"Error hiding messages for '{character_name}': {e}")
            finally:
                conn.close()

        logger.info(f"Summarized and concealed old messages for '{character_name}', up to message ID {covered_up_to_message_id}.")

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
            logger.info(f"Character '{character_name}' moved/updated location to '{new_location}'.")

    async def handle_new_appearance_for_character(self, character_name: str, new_appearance: str, triggered_message_id: int):
        updated = self.db.update_character_appearance(
            self.session_id,
            character_name,
            new_appearance,
            triggered_by_message_id=triggered_message_id
        )
        if updated:
            logger.info(f"Character '{character_name}' updated appearance to '{new_appearance}'.")

    def get_all_visible_messages(self) -> List[Dict]:
        summaries = self.db.get_all_summaries(self.session_id, None)
        visible_msgs = self.db.get_messages(self.session_id)
        recent_msgs = visible_msgs[-self.recent_dialogue_lines:]
        history = summaries + [m for m in recent_msgs if m["visible"]]
        return history
    
    async def validate_and_possibly_correct_interaction(
        self,
        character_name: str,
        system_prompt: str,
        dynamic_prompt: str,
        initial_interaction: Interaction
    ) -> Optional[Interaction]:
        """
        Validates (and if needed corrects) the given interaction to ensure
        it conforms to prompts. Returns a valid Interaction or None if it cannot be validated.
        """
        if self.validation_loop_setting == 0:
            # Even if we skip validation, still update plan
            await self.update_character_plan(character_name)
            return initial_interaction

        validation_client = OllamaClient(
            'src/multipersona_chat_app/config/llm_config.yaml',
            output_model=InteractionValidationOutput
        )

        current_interaction = initial_interaction
        iteration = 0

        while True:
            iteration += 1
            logger.debug(f"Validation iteration {iteration} for character '{character_name}'")

            validation_prompt = f"""You are checking if the following JSON interaction is valid according to the character's system prompt and dynamic prompt.

System Prompt (character rules, guidelines):
{system_prompt}

Dynamic Prompt (with relevant context):
{dynamic_prompt}

The user-generated interaction JSON to validate:
{current_interaction.json()}

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
      "new_appearance": "...",
      "why_new_appearance": "..."
  }}
}}
- If is_valid is "yes", do NOT provide a corrected_interaction (or leave it empty).
- If is_valid is "no", provide a corrected_interaction with valid fields.

Only produce valid JSON with these two top-level keys: "is_valid" and "corrected_interaction". 
Include all fields in "corrected_interaction" if is_valid="no".
"""

            # Call the LLM in a thread
            result = await asyncio.to_thread(
                validation_client.generate,
                prompt=validation_prompt,
                system=None,
                use_cache=False
            )

            if not result:
                logger.warning(f"Validation request returned no result for iteration {iteration}.")
                if self.validation_loop_setting == -1:
                    continue
                if self.validation_loop_setting > 0 and iteration >= self.validation_loop_setting:
                    return None
                continue

            if isinstance(result, InteractionValidationOutput):
                validation_output = result
            else:
                try:
                    validation_output = InteractionValidationOutput.parse_raw(result)
                except Exception as parse_e:
                    logger.warning(f"Failed to parse validation output: {parse_e}")
                    if self.validation_loop_setting == -1:
                        continue
                    if self.validation_loop_setting > 0 and iteration >= self.validation_loop_setting:
                        return None
                    continue

            if validation_output.is_valid.lower() == "yes":
                logger.debug(f"Interaction is valid on iteration {iteration}.")
                await self.update_character_plan(character_name)
                return current_interaction

            corrected = validation_output.corrected_interaction
            if not corrected:
                logger.warning("Validation said 'no' but didn't provide a corrected_interaction.")
                if self.validation_loop_setting == -1:
                    continue
                if self.validation_loop_setting > 0 and iteration >= self.validation_loop_setting:
                    return None
                continue

            current_interaction = corrected

            if self.validation_loop_setting > 0 and iteration >= self.validation_loop_setting:
                logger.warning("Reached validation iteration limit without achieving 'is_valid=yes'.")
                return None
        
        # Not reached normally
        return None

    #
    # CHANGE: 'update_character_plan' calls the LLM in a separate thread so it won't block.
    #
    async def update_character_plan(self, character_name: str):
        """
        Revise or confirm the existing plan for the given character based on the latest context.
        If the plan changes, store the new plan.
        """
        plan_client = OllamaClient(
            config_path='src/multipersona_chat_app/config/llm_config.yaml',
            output_model=CharacterPlan
        )

        existing_plan = self.get_character_plan(character_name)
        current_appearance = self.db.get_character_appearance(self.session_id, character_name)
        character_description = self.characters[character_name].character_description

        system_prompt = """
You are an expert assistant in crafting and refining long-term plans for narrative characters. Your primary responsibility is to ensure that each character's plan is practical, achievable within hours or days, and tailored to their current context, including their location and appearance. Each plan consists of:

- A clear goal: The ultimate objective the character seeks to achieve.
- Actionable steps: Specific, concrete, and sequential tasks that systematically progress the character toward their goal.

Your focus is to create plans that are logical, detailed, and aligned with the character’s circumstances.
        """

        user_prompt = f"""
**Character Name:** {character_name}
**Character description:** {character_description}

**Existing Plan:**
- **Goal:** {existing_plan.goal}
- **Steps:**
{''.join(f'  - {step}\n' for step in existing_plan.steps)}

**Context:**
- **Current Setting:** {self.current_setting}
- **Current Location:** {self.get_combined_location()}
- **Current Appearance:** {current_appearance}

**Latest Dialogue:**
{''.join(f'- {m["message"]}\n' for m in self.get_visible_history() if isinstance(m, dict))}

**Instructions:**
- Review the existing plan and the current context for {character_name}.
- Determine if the plan needs to be revised based on any changes in {character_name}'s situation.
- Ensure that the steps are actionable, concrete, sequential and start from the current location at setting and current appearance.
- By the final step, the goal should be achieved.
- If revisions are necessary:
    - The "goal" might change or remain the same.
    - Modify the "steps" as needed by adding, removing, or updating them.
- Output the updated plan strictly in JSON format following this structure:

{{
"goal": "<string>",
"steps": [ "step1", "step2", ... ]
}}

**Example JSON:**
{{
"goal": "Achieve relaxation during a visit to the hot springs.",
"steps": [
    "Change into swimwear.",
    "Soak in the hot springs to relax.",
    "Take a break to hydrate and enjoy the surroundings.",
    "Rinse off and change into your clothes."
]
}}

If no changes are needed, repeat the existing plan in the specified JSON format.
"""

        # LLM call in a background thread
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

            self.save_character_plan(character_name, new_plan)
            logger.info(
                f"Plan updated for '{character_name}'. "
                f"New goal: {new_plan.goal}, steps: {new_plan.steps}"
            )
        except Exception as e:
            logger.error(
                f"Failed to parse new plan data for '{character_name}'. "
                f"Keeping old plan. Error: {e}"
            )

    #
    # We keep this async so the user can call it from app.py
    #
    async def generate_character_introduction_message(self, character_name: str):
        """
        Generates the character's introduction and then triggers an initial plan update.
        """
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
                appearance = introduction_response.current_appearance.strip()
                location = introduction_response.current_location.strip()

                logger.info(f"Introduction generated for {character_name}. Text: {intro_text}")

                msg_id = await self.add_message(
                    character_name,
                    intro_text,
                    visible=True,
                    message_type="character"
                )

                if appearance:
                    await self.handle_new_appearance_for_character(character_name, appearance, msg_id)
                if location:
                    await self.handle_new_location_for_character(character_name, location, msg_id)

                logger.info(f"Saved introduction message for {character_name}")
            else:
                logger.warning(f"Invalid response received for introduction of {character_name}. Response: {introduction_response}")


        except Exception as e:
            logger.error(f"Error generating introduction for {character_name}: {e}", exc_info=True)
            return

        # Now generate the initial plan
        await self.update_character_plan(character_name)
