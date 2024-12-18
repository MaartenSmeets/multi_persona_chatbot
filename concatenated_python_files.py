# File: /home/maarten/multi_persona_chatbot/concat.py
import os

def concatenate_python_files(output_file, root_dir, exclude_dirs=None):
    """
    Concatenates all Python files in the specified directory recursively into a single file.

    :param output_file: Path to the output file where concatenated content will be written.
    :param root_dir: Root directory to start searching for Python files.
    :param exclude_dirs: List of directories to exclude.
    """
    if exclude_dirs is None:
        exclude_dirs = ['__pycache__', '.git', '.venv', 'build', 'dist', '.idea', '.vscode']

    with open(output_file, 'w') as output:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Remove excluded directories from the traversal
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

            for filename in filenames:
                if filename.endswith('.py'):
                    file_path = os.path.join(dirpath, filename)
                    if os.path.getsize(file_path) > 0:  # Skip empty files
                        output.write(f"# File: {file_path}\n")
                        try:
                            with open(file_path, 'r', encoding='utf-8') as file:
                                content = file.read()
                                output.write(content + '\n\n')
                        except Exception as e:
                            output.write(f"# Error reading {file_path}: {e}\n\n")

if __name__ == "__main__":
    output_file = "concatenated_python_files.py"
    root_dir = os.getcwd()  # Change this to the desired root directory if needed
    concatenate_python_files(output_file, root_dir)
    print(f"All Python files have been concatenated into {output_file}.")


# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/main.py
from ui.app import start_ui

if __name__ in {'__main__', '__mp_main__'}:
    start_ui()

# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/llm/ollama_client.py
# ollama_client.py
import requests
import logging
from typing import Optional, Type
from pydantic import BaseModel
import yaml
import json  # Needed for parsing streaming JSON lines

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self, config_path: str, output_model: Optional[Type[BaseModel]] = None):
        """
        Initialize the OllamaClient with a configuration file.
        """
        self.config = self.load_config(config_path)
        self.output_model = output_model

    @staticmethod
    def load_config(config_path: str) -> dict:
        """
        Load the YAML configuration file and return it as a dictionary.
        """
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
            logger.info(f"Configuration loaded successfully from {config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"Configuration file not found at path: {config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading configuration: {e}")
            raise

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Optional[BaseModel]:
        """
        Generate a response from the model based on the given prompt.
        Implements retry logic based on the configuration and supports streaming responses.
        """
        headers = {
            'Content-Type': 'application/json',
        }
        api_key = self.config.get('api_key')
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        payload = {
            'model': self.config.get('model_name'),
            'prompt': prompt,
            "stream": True,  # Ensuring we request a streaming response
            'options': {         
                'temperature': temperature if temperature is not None else self.config.get('temperature', 0.7)
            }
        }

        if self.output_model:
            # The specifics of how the model is formatted might vary.
            # If your API supports specifying a format, use that here.
            # Otherwise, consider removing or adjusting this line as needed.
            payload['format'] = self.output_model.model_json_schema()

        max_retries = self.config.get('max_retries', 3)

        # Prepare headers for logging by masking the Authorization header
        log_headers = headers.copy()
        if 'Authorization' in log_headers:
            log_headers['Authorization'] = 'Bearer ***'

        logger.info("Sending request to Ollama API")
        logger.info(f"Request URL: {self.config.get('api_url')}")
        logger.info(f"Request Headers: {log_headers}")
        logger.info(f"Request Payload: {payload}")

        for attempt in range(1, max_retries + 1):
            try:
                with requests.post(
                    self.config.get('api_url'),
                    headers=headers,
                    json=payload,
                    stream=True
                ) as response:
                    # Log response status and headers
                    logger.info(f"Received response with status code: {response.status_code}")
                    logger.info(f"Response Headers: {response.headers}")

                    response.raise_for_status()

                    output = ""
                    for line in response.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        # Log the raw response line before parsing
                        logger.debug(f"Raw response line: {line}")

                        try:
                            data = json.loads(line)
                            #logger.info(f"Parsed response line: {data}")
                        except json.JSONDecodeError:
                            logger.warning("Received a line that could not be JSON-decoded, skipping...")
                            continue

                        # Check for errors in streaming data
                        if "error" in data:
                            logger.error(f"Error in response data: {data['error']}")
                            raise Exception(data["error"])

                        # Extract the 'response' field
                        content = data.get("response", "")
                        output += content

                        if data.get("done", False):
                            # Streaming is complete
                            # Parse into output_model if provided
                            if self.output_model:
                                try:
                                    # Validate that output contains valid JSON
                                    if not output.strip():
                                        raise ValueError("Output is empty, cannot parse.")
                                    
                                    parsed_output = self.output_model.parse_raw(output)
                                    logger.info(f"Final parsed output: {parsed_output}")
                                    return parsed_output
                                except Exception as e:
                                    logger.error(f"Error parsing model output: {e}")
                                    return None
                            logger.info(f"Final output: {output}")
                            return output

                    # If we exit the loop without hitting 'done', something might be wrong
                    logger.error("No 'done' signal received before the stream ended.")
                    return None
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error(f"All {max_retries} attempts failed. Giving up.")
                    raise
                else:
                    logger.info(f"Retrying... (Attempt {attempt + 1} of {max_retries})")
            except Exception as e:
                logger.error(f"An error occurred: {e}")
                raise


# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/models/character.py
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


# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/models/interaction.py
from pydantic import BaseModel

class Interaction(BaseModel):
    affect: str   # Internal feelings and emotions
    action: str   # Observable behavior
    dialogue: str # Spoken words

    def format(self) -> str:
        """Format the Interaction object into a displayable string."""
        return (f"Affect: {self.affect}\n"
                f"Action: {self.action}\n"
                f"Dialogue: {self.dialogue}")

# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/chats/chat_manager.py
# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/chats/chat_manager.py
import datetime
from typing import List, Dict, Tuple, Optional
from models.character import Character

class ChatManager:
    def __init__(self, you_name: str = "You"):
        self.characters: Dict[str, Character] = {}
        self.chat_history: List[Dict[str, any]] = []
        self.turn_index = 0
        self.automatic_running = False
        self.you_name = you_name

    def set_you_name(self, name: str):
        self.you_name = name

    def add_character(self, char_name: str, char_instance: Character):
        self.characters[char_name] = char_instance

    def remove_character(self, char_name: str):
        if char_name in self.characters:
            del self.characters[char_name]

    def get_characters_in_order(self) -> List[str]:
        return list(self.characters.keys())

    def next_speaker(self) -> Optional[str]:
        chars = self.get_characters_in_order()
        if not chars:
            return None
        return chars[self.turn_index % len(chars)]

    def advance_turn(self):
        chars = self.get_characters_in_order()
        if chars:
            self.turn_index = (self.turn_index + 1) % len(chars)

    def add_message(self, sender: str, message: str, visible: bool = True):
        self.chat_history.append({
            "sender": sender,
            "message": message,
            "timestamp": datetime.datetime.now(),
            "visible": visible
        })

    def get_visible_history(self) -> List[Tuple[str, str]]:
        return [(entry["sender"], entry["message"]) for entry in self.chat_history if entry["visible"]]

    def build_prompt_for_character(self, character_name: str) -> str:
        visible_history = self.get_visible_history()
        latest_dialogue = visible_history[-1][1] if visible_history else ""
        setting = "This is a shared conversation environment."
        chat_history_summary = "\n".join(f"{s}: {m}" for s, m in visible_history[:-1])

        char = self.characters[character_name]
        prompt = char.format_prompt(
            setting=setting,
            chat_history_summary=chat_history_summary,
            latest_dialogue=latest_dialogue
        )
        return prompt

    def start_automatic_chat(self):
        self.automatic_running = True

    def stop_automatic_chat(self):
        self.automatic_running = False


# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/ui/app.py
import os
from nicegui import ui, app
from llm.ollama_client import OllamaClient
from models.interaction import Interaction
from models.character import Character
from chats.chat_manager import ChatManager
import asyncio

# Initialize LLM client and ChatManager
llm_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=Interaction)
chat_manager = ChatManager(you_name="You")

user_input = None
chat_display = None
you_name_input = None
character_dropdown = None
added_characters_container = None  # Declare as global

CHARACTERS_DIR = "src/multipersona_chat_app/characters"  # Adjust path as needed


def get_available_characters(directory):
    """Retrieve a list of available characters with their names and YAML filenames."""
    characters = []
    try:
        for f in os.listdir(directory):
            if f.endswith('.yaml'):
                yaml_file = os.path.join(directory, f)
                try:
                    char = Character.from_yaml(yaml_file)
                    characters.append({'label': char.name, 'value': f})
                except Exception:
                    pass  # Skip files that cannot be loaded
    except FileNotFoundError:
        pass
    return characters


def main_page():
    global user_input, chat_display, you_name_input, character_dropdown, added_characters_container

    with ui.column().classes('w-full max-w-2xl mx-auto'):
        ui.label('Multipersona Chat Application').classes('text-2xl font-bold mb-4')

        # Configure "Your Name"
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Your name:").classes('w-1/4')
            you_name_input = ui.input(value=chat_manager.you_name).classes('flex-grow')
            ui.button("Set", on_click=lambda: set_you_name(you_name_input.value)).classes('ml-2')

        # Add Characters Dropdown
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Select Character:").classes('w-1/4')
            character_dropdown = ui.select(
                options=get_available_characters(CHARACTERS_DIR),
                on_change=add_character_from_dropdown,
                label="Choose a character"
            ).classes('flex-grow')

        # List of Added Characters with Remove Buttons
        with ui.column().classes('w-full mb-4'):
            ui.label("Added Characters:").classes('font-semibold mb-2')
            added_characters_container = ui.row().classes('flex-wrap gap-2')

            def refresh_added_characters():
                added_characters_container.clear()
                for char_name in chat_manager.get_character_names():
                    with added_characters_container:
                        with ui.card().classes('p-2 flex items-center'):
                            ui.label(char_name).classes('flex-grow')
                            ui.button(
                                'Remove',
                                on_click=lambda _, name=char_name: remove_character(name),
                                style='background-color: red; color: white;'
                            ).classes('ml-2')

            # Initial Population of Added Characters
            refresh_added_characters()

        # Toggle Automatic Chat
        with ui.row().classes('w-full items-center mb-4'):
            auto_switch = ui.switch('Automatic Chat', value=False, on_change=toggle_automatic_chat).classes('mr-2')
            ui.button("Stop", on_click=lambda: chat_manager.stop_automatic_chat()).classes('ml-auto')

        # Chat Display Area
        chat_display = ui.column().classes('space-y-2 p-4 bg-gray-100 rounded h-96 overflow-y-auto')

        # User Input Field and Send Button
        with ui.row().classes('w-full items-center mt-4'):
            user_input = ui.input(placeholder='Enter your message...').classes('flex-grow')
            ui.button('Send', on_click=lambda: asyncio.create_task(send_user_message())).classes('ml-2')

    # Schedule the Background Task for Automatic Conversation
    app.on_startup(lambda: asyncio.create_task(automatic_conversation()))


def toggle_automatic_chat(e):
    if e.value:
        if not chat_manager.get_character_names():
            chat_manager.add_message("System", "No characters added. Please add characters to start automatic chat.", visible=True)
            update_chat_display()
            e.value = False
            return
        chat_manager.start_automatic_chat()
    else:
        chat_manager.stop_automatic_chat()


def set_you_name(name: str):
    chat_manager.set_you_name(name)
    update_chat_display()


def add_character_from_dropdown(event):
    """Add a character based on the selected YAML file."""
    if event.value:
        yaml_file = os.path.join(CHARACTERS_DIR, event.value)
        try:
            char = Character.from_yaml(yaml_file)
            if char.name in chat_manager.get_character_names():
                chat_manager.add_message("System", f"Character '{char.name}' is already added.", visible=True)
            else:
                chat_manager.add_character(char.name, char)
                chat_manager.add_message("System", f"Character '{char.name}' added.", visible=True)
                refresh_added_characters()
        except Exception as e:
            chat_manager.add_message("System", f"Failed to add character: {e}", visible=True)
        finally:
            update_chat_display()
            character_dropdown.value = None  # Reset dropdown selection


def remove_character(name: str):
    chat_manager.remove_character(name)
    chat_manager.add_message("System", f"Character '{name}' removed.", visible=True)
    update_chat_display()
    refresh_added_characters()


async def automatic_conversation():
    """Continuous loop to facilitate automatic character turns."""
    while True:
        await asyncio.sleep(2)
        if chat_manager.automatic_running:
            next_char = chat_manager.next_speaker()
            if next_char:
                await generate_character_message(next_char)
                chat_manager.advance_turn()


async def generate_character_message(character_name: str):
    prompt = chat_manager.build_prompt_for_character(character_name)
    # Indicate that character is thinking
    chat_manager.add_message(character_name, "...", visible=True)
    update_chat_display()

    try:
        interaction = await asyncio.to_thread(llm_client.generate, prompt=prompt)
        if interaction:
            formatted_message = f"*{interaction.action}*\n{interaction.dialogue}"
        else:
            formatted_message = "No response."
    except Exception as e:
        formatted_message = f"Error: {str(e)}"

    # Replace placeholder message with final response
    chat_manager.chat_history[-1]["message"] = formatted_message
    update_chat_display()


async def send_user_message():
    if not user_input.value:
        return

    chat_manager.add_message(chat_manager.you_name, user_input.value, visible=True)
    update_chat_display()
    user_input.value = ''
    user_input.update()

    # If not running automatically, have the next character respond
    if not chat_manager.automatic_running:
        next_char = chat_manager.next_speaker()
        if next_char:
            await generate_character_message(next_char)
            chat_manager.advance_turn()


def update_chat_display():
    chat_display.clear()
    for entry in chat_manager.chat_history:
        name = entry["sender"]
        message = entry["message"]
        timestamp = entry["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        # Format the message with sender's name and timestamp
        formatted_message = f"**{name}** [{timestamp}]:\n\n{message}"
        with chat_display:
            ui.markdown(formatted_message)


def refresh_added_characters():
    """Refresh the list of added characters in the UI."""
    added_characters_container.clear()
    for char_name in chat_manager.get_character_names():
        with added_characters_container:
            with ui.card().classes('p-2 flex items-center'):
                ui.label(char_name).classes('flex-grow')
                ui.button(
                    'Remove',
                    on_click=lambda _, name=char_name: remove_character(name),
                    style='background-color: red; color: white;'
                ).classes('ml-2')


def start_ui():
    main_page()
    ui.run(reload=False)


if __name__ in {'__main__', '__mp_main__'}:
    start_ui()


