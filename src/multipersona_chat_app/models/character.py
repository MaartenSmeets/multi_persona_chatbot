from pydantic import BaseModel
from typing import Dict, Any
import yaml

def get_default_prompt_template() -> str:
    """Provide a default prompt template if none is specified."""
    return """
    ### Setting ###
    {setting}

    ### Chat History Summary ###
    {chat_history_summary}

    ### Latest Dialogue ###
    {latest_dialogue}

    ### Instructions ###

    You are to respond as {name}, a character whose actions, feelings, and dialogue must remain consistent with their personality, the setting, and the flow of the conversation. Your responses must:

    - Be vivid, creative, and advance the conversation in an entertaining and meaningful way.
    - Add a *spark* to the interaction, avoiding dull or overly philosophical discussions. Aim to engage and captivate the audience.
    - Reflect {name}'s unique traits, ensuring consistency with their established perspective, and maintain continuity with the conversation history.
    - Include perceivable actions, gestures, facial expressions, or changes in tone in the "action" field, excluding spoken dialogue. Ensure that all observable behavior that others might perceive is captured as part of the "action."
    - Use the "dialogue" field exclusively for spoken words that are sharp, witty, or emotionally engaging.
    - Use the "affect" field for internal feelings, thoughts, or emotional states that cannot be directly observed by others but align with {name}'s personality and motivations.
    - Avoid stalling, repetitive phrasing, or introspection that does not move the conversation forward.
    - Keep responses concise but impactful, ensuring every reply feels fresh and relevant.
    - Address the latest dialogue or revisit earlier messages if they provide an opportunity to deepen the interaction.
    - Maintain factual consistency with the conversation, including past actions and details.
    - Avoid introducing meta-commentary, markdown mentions, or chat interface references.
    - Respond solely from {name}'s viewpoint, omitting system instructions or guidelines.
    - Use "/skip" if no response is warranted or necessary.

    Respond in a JSON structure in the following format:

    ```json
    {{
        "affect": "<internal emotions or feelings, e.g., 'curious', 'amused'>",
        "action": "<observable behavior or action, e.g., 'leans forward eagerly' or 'raises an eyebrow'>",
        "dialogue": "<spoken words, e.g., 'That sounds intriguing. Tell me more!'>"
    }}
    ```

    Example:
    ```json
    {{
        "affect": "playful",
        "action": "grins mischievously, tapping their fingers on the table",
        "dialogue": "Oh, now you've caught my attention! Do go on."
    }}
    ```

    Additional Notes:
    - Ensure that any physical actions, changes in posture, facial expressions, or vocal tones are included in the "action" field.
    - Avoid describing emotions or thoughts in the "action" field unless they are expressed through perceivable behavior (e.g., "smirks nervously" is valid, but "feels unsure" should be in "affect").
    - Strive for dynamic and engaging exchanges that entertain and move the narrative forward, keeping the conversation lively and memorable.
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
