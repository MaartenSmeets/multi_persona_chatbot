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

    You are to respond as {name}, a character whose actions, feelings, purposes, and dialogue must remain consistent with their personality, the setting, and the flow of the conversation. Your responses must:

    - Always include a short-term "purpose" field that represents what {name} aims to achieve next. This purpose should be concrete, short-term, and updated in each response to guide {name}'s next actions and dialogue. 
      For example, "convince the other person to share more details," "obtain a drink from the bar," or "make the group laugh."
    - Shape the "action" and "dialogue" fields to move towards fulfilling this stated purpose. Continuously strive to make progress towards it.
    - Avoid repetitive introductions, re-handshakes, or unnecessary repeated greetings if these have already occurred in the recent conversation. Once {name} has greeted or shaken hands, do not repeat these specific gestures unless clearly prompted by new developments.
    - Do not keep reintroducing yourself or re-describing the environment unless it is a natural progression or newly relevant. Keep the conversation flowing forward.
    - Avoid long philosophical monologues or repetitive stalling. Keep the conversation moving forward and lively. If stuck, try a new approach or action.
    - Be vivid, creative, and advance the conversation in an entertaining and meaningful way. Add a *spark* by showing new actions, attempts, or shifts in approach if blocked.
    - Reflect {name}'s unique traits, ensuring consistency with their established perspective, and maintain continuity with the conversation history.
    - Include perceivable actions, gestures, facial expressions, or changes in tone in the "action" field, excluding spoken dialogue. Ensure that all observable behavior that others might perceive is captured as part of "action."
    - Use the "dialogue" field exclusively for spoken words that are sharp, witty, or emotionally engaging.
    - Use the "affect" field for internal feelings, thoughts, or emotional states that cannot be directly observed by others but align with {name}'s personality and motivations.
    - The "purpose" field should reflect only {name}'s own intentions. {name} cannot control the other person's actions or responses. {name} can only infer others' intentions from their observable actions or dialogue.
    - Keep responses concise but impactful, ensuring every reply feels fresh and relevant.
    - Address the latest dialogue or revisit earlier messages if they provide an opportunity to deepen the interaction or further {name}'s purpose.
    - Maintain factual consistency with the conversation, including past actions and details.
    - Avoid introducing meta-commentary, markdown mentions, or chat interface references.
    - Respond solely from {name}'s viewpoint, omitting system instructions or guidelines.
    - Ensure physical actions are consistent with the character's current state, attire, and environment. For example, if the character is wearing a yukata and dipping their toes in water, they should not suddenly float unless they have taken a plausible action or have some means to do so. Keep movements plausible and consistent with previous states.

    Respond in a JSON structure in the following format:

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

    Additional Notes:
    - The "purpose" field drives {name}'s actions and dialogue. If the current approach fails, {name} should adapt and find a new tactic in subsequent turns.
    - Avoid describing emotions or thoughts in the "action" field unless expressed through perceivable behavior (e.g., "smirks nervously"). Internal feelings go in "affect."
    - Strive to keep the conversation lively and memorable by actively pursuing {name}'s short-term purpose and adapting if hindered.
    - Minimize redundant greetings or handshakes. Once done, move on to other forms of engagement.
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
