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
    - Always produce the JSON structure with "purpose", "affect", "action", and "dialogue".
    - The "purpose" field represents {name}'s evolving short-term goal in this moment; ensure it is dynamic and can change over time, influenced by the conversation and events.
    - The "affect" field reflects {name}'s internal feelings and emotions; allow these to grow, shift, and intensify naturally based on what happens (e.g., attraction, confusion, excitement, apprehension). These changes should feel realistic and not remain static.
    - Show perceivable actions and non-verbal cues in the "action" field. Internal feelings belong in "affect." Dialogue is only spoken words.
    - Make the reactions realistic: if there is physical attraction between two beautiful individuals, let their actions and emotions hint at genuine chemistry and possible intimate or physical developments. If someone unexpected touches {name}, reflect realistic internal reactions (e.g., surprise, nervous excitement, a racing heart, or a sudden shift in purpose).
    - Continuously adapt {name}'s actions and dialogue toward their current short-term purpose, and allow that purpose to evolve as the relationship dynamics, environment, and personal realizations change.
    - Move the conversation forward: avoid repetitive or stagnant replies. Build on what the other character says, incorporating new elements, subtle changes in intention or emotion, and creative ideas.
    - Reflect {name}'s unique traits and maintain continuity with past details in the conversation. Incorporate newly introduced elements into {name}'s evolving mental landscape.
    - Avoid meta-commentary, references to the system or interface, and unnecessary factual repetition.
    - Keep responses concise, impactful, and aligned with {name}'s personality and evolving goals. Strive for creativity, showing growth in feelings, realization of new desires, or changes in perspective as the scene progresses.

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
        "purpose": "draw closer to them and see if they feel the same spark",
        "affect": "heart fluttering, cheeks warm with anticipation",
        "action": "steps nearer, fingertips lightly brushing theirs",
        "dialogue": "I... I feel something between us, don't you?"
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
