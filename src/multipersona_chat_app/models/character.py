from pydantic import BaseModel
import yaml

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

        appearance = data.get('appearance', "")
        character_description = data.get('character_description', "")

        return cls(
            name=data['name'],
            system_prompt_template=data['system_prompt_template'],
            prompt_template='',
            appearance=appearance,
            character_description=character_description
        )

    def format_prompt(self, setting: str, chat_history_summary: str, latest_dialogue: str, location: str) -> str:
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
        current_location_section = optional_section("Current Location", location)
        history_section = optional_section("Chat History Summary", chat_history_summary)
        dialogue_section = optional_section("Latest Dialogue", latest_dialogue)
        current_outfit_section = optional_section("Current Outfit", self.appearance)

        prompt = self.prompt_template.format(
            setting=setting_section.strip(),
            chat_history_summary=history_section.strip(),
            latest_dialogue=dialogue_section.strip(),
            current_location=current_location_section.strip(),
            current_outfit=current_outfit_section.strip()
        )

        return prompt
