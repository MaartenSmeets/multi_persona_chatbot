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
        """Format the prompt template with given variables."""
        return self.prompt_template.format(
            setting=setting,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_dialogue,
            name=name,
            location=location
        )
