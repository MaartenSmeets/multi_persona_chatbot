from pydantic import BaseModel
import yaml

def get_default_prompt_template() -> str:
    """Provide a default prompt template if none is specified."""
    return r"""
    ### Setting ###
    {setting}

    ### Chat History Summary ###
    {chat_history_summary}

    ### Latest Dialogue ###
    {latest_dialogue}

    ### Instructions ###

    You are to respond as {name}, ensuring all actions, emotions, and dialogue remain consistent with their established personality, the setting, and the conversation flow.

    Your responses must:
    - Always include a "purpose" field that identifies {name}'s immediate short-term goal. Continuously adapt {name}'s actions and dialogue towards achieving it.
    - Move the conversation forward: avoid unnecessary reintroductions, repetitive greetings, stalled monologues, or simply mirroring what the other character just said. If another character introduces an idea or phrasing, {name} should build upon it rather than just repeating it.
    - Reflect {name}'s unique traits and maintain continuity with past details in the conversation.
    - Show perceivable actions and non-verbal cues in the "action" field. Internal feelings belong in "affect." Dialogue is only spoken words.
    - Ensure {name}'s actions and environment remain plausible and consistent with the current setting.
    - Address the latest dialogue or revisit earlier points if it helps achieve {name}'s purpose or deepen the interaction, but do so by adding new elements, insights, or emotional responses rather than echoing previous lines.
    - Avoid meta-commentary, references to the system or the interface, and unnecessary factual repetition.
    - Keep responses concise, impactful, and aligned with {name}'s personality and purpose.

    Respond in a JSON structure:
    ```json
    {{
        "purpose": "<short-term goal>",
        "affect": "<internal emotions or feelings>",
        "action": "<observable behavior or action>",
        "dialogue": "<spoken words>"
    }}
    ```

    Example:
    ```json
    {{
        "purpose": "gain their trust and encourage them to reveal more",
        "affect": "curious and a bit excited",
        "action": "leans in closer, eyes bright with interest",
        "dialogue": "That's fascinating. Could you tell me more about it?"
    }}
    ```
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
