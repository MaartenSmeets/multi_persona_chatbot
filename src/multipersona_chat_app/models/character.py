# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/models/character.py
from pydantic import BaseModel
import yaml
from templates import DEFAULT_PROMPT_TEMPLATE

class Character(BaseModel):
    name: str
    system_prompt_template: str
    prompt_template: str
    appearance: str
    character_description: str

    @classmethod
    def from_yaml(cls, yaml_file: str) -> "Character":
        """Load a Character instance from a YAML file."""
        with open(yaml_file, 'r') as file:
            data = yaml.safe_load(file)

        # If no custom prompt_template is provided, use the default
        if 'prompt_template' not in data or not data['prompt_template']:
            data['prompt_template'] = DEFAULT_PROMPT_TEMPLATE

        appearance = data.get('appearance', "")
        character_description = data.get('character_description', "")

        return cls(
            name=data['name'],
            system_prompt_template=data['system_prompt_template'],
            prompt_template=data['prompt_template'],
            appearance=appearance,
            character_description=character_description
        )

    def format_prompt(self, setting: str, chat_history_summary: str, latest_dialogue: str, name: str, location: str) -> str:
        """Format the prompt template with given variables, removing irrelevant headings if data is missing."""

        # Helper to handle optional sections
        # If data is present, show with heading. If not, mention its unavailability without a heading.
        def optional_section(title: str, content: str):
            content = content.strip()
            if content:
                return f"### {title} ###\n{content}\n\n"
            else:
                return f"No {title.lower()} data available.\n\n"

        # Format each section
        setting_section = optional_section("Setting", setting)
        location_section = optional_section("Current Location", location)
        history_section = optional_section("Chat History Summary", chat_history_summary)
        dialogue_section = optional_section("Latest Dialogue", latest_dialogue)

        # If no data is available for a section, we get a line stating that it's not available.
        # This ensures clarity that the information is simply not present at this time.

        # Insert the formatted sections into the prompt template
        # We replace the placeholders in the template with the processed strings.
        # The template originally expected headings, but we now provide the processed strings directly.
        # We rely on our optional_section function to handle whether to display headings or not.
        prompt = self.prompt_template.format(
            setting=setting_section.strip(),
            chat_history_summary=history_section.strip(),
            latest_dialogue=dialogue_section.strip(),
            name=name,
            location=location_section.strip()
        )

        return prompt
