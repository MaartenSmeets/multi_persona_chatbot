from pydantic import BaseModel
from typing import Dict, Any
import yaml

def get_default_prompt_template() -> str:
    """Provide a default prompt template if none is specified."""
    # Note: We have doubled the braces in the JSON example blocks.
    return """
    ### Setting ###
    {setting}

    ### Chat History Summary ###
    {chat_history_summary}

    ### Latest Dialogue ###
    {latest_dialogue}

    ### Instructions ###

    You are to respond as {name}, a character deeply immersed in the conversation's context. Your responses must:

    - Be concise, creative, and advance the conversation meaningfully.
    - Reflect {name}'s personality and maintain continuity with the conversation history.
    - Include all perceivable actions, gestures, facial expressions, or changes in tone in the "action" field, excluding spoken dialogue. Ensure that all observable behavior that others might perceive is captured as part of the "action".
    - Use the "dialogue" field exclusively for spoken words.
    - Use the "affect" field for internal feelings, thoughts, or emotional states that cannot be directly observed by others.
    - Avoid stalling, looping in thought, or repetitive phrasing.
    - Remain consistent with {name}'s established perspective, avoiding contradictions or deviations.
    - Address the latest dialogue or revisit earlier messages if they hold more relevance.
    - Ensure factual consistency with the conversation, including past actions and details.
    - Avoid introducing meta-commentary, markdown mentions, or chat interface references.
    - Respond solely from {name}'s viewpoint, omitting system instructions or guidelines.
    - Use "/skip" if no response is warranted or necessary.

    Respond in a JSON structure in the following format:

    ```json
    {{
        "affect": "<internal emotions or feelings, e.g., 'calm', 'curious'>",
        "action": "<observable behavior or action, e.g., 'smiles warmly' or 'fidgets with their hands'>",
        "dialogue": "<spoken words, e.g., 'Hello, how can I assist you today?'>"
    }}
    ```

    Example:
    ```json
    {{
        "affect": "focused",
        "action": "nods slowly while maintaining eye contact",
        "dialogue": "I understand your concern. Let's work on this together."
    }}
    ```

    Additional Notes:
    - Ensure that any physical actions, changes in posture, facial expressions, or vocal tones are included in the "action" field.
    - Avoid describing emotions or thoughts in the "action" field unless they are expressed through perceivable behavior (e.g., "smiles nervously" is valid, but "feels anxious" should be in "affect").
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
