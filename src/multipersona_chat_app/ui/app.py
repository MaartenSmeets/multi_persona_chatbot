import os
from nicegui import ui, app
from llm.ollama_client import OllamaClient
from models.interaction import Interaction
from models.character import Character
from chats.chat_manager import ChatManager
import asyncio
import yaml

llm_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=Interaction)
chat_manager = ChatManager(you_name="You")

user_input = None
chat_display = None
you_name_input = None
character_dropdown = None
added_characters_container = None  
next_speaker_label = None
next_button = None
settings_dropdown = None

CHARACTERS_DIR = "src/multipersona_chat_app/characters"
ALL_CHARACTERS = {}
ALL_SETTINGS = []

def load_settings():
    settings_path = os.path.join("src", "multipersona_chat_app", "config", "settings.yaml")
    try:
        with open(settings_path, 'r') as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, list) else []
    except:
        return []

def get_available_characters(directory):
    characters = {}
    try:
        for filename in os.listdir(directory):
            if filename.endswith('.yaml'):
                yaml_path = os.path.join(directory, filename)
                try:
                    char = Character.from_yaml(yaml_path)
                    characters[char.name] = char
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return characters

def refresh_added_characters():
    added_characters_container.clear()
    for char_name in chat_manager.get_character_names():
        with added_characters_container:
            with ui.card().classes('p-2 flex items-center'):
                ui.label(char_name).classes('flex-grow')
                ui.button(
                    'Remove',
                    on_click=lambda _, name=char_name: remove_character(name),
                ).classes('ml-2 bg-red-500 text-white') 

def update_next_speaker_label():
    ns = chat_manager.next_speaker()
    if ns:
        next_speaker_label.text = f"Next speaker: {ns}"
    else:
        next_speaker_label.text = "No characters available."

def main_page():
    global user_input, chat_display, you_name_input, character_dropdown, added_characters_container, next_speaker_label, next_button, ALL_CHARACTERS, ALL_SETTINGS, settings_dropdown

    ALL_CHARACTERS = get_available_characters(CHARACTERS_DIR)
    ALL_SETTINGS = load_settings()

    with ui.column().classes('w-full max-w-2xl mx-auto'):
        ui.label('Multipersona Chat Application').classes('text-2xl font-bold mb-4')

        # Configure "Your Name"
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Your name:").classes('w-1/4')
            you_name_input = ui.input(value=chat_manager.you_name).classes('flex-grow')
            ui.button("Set", on_click=lambda: set_you_name(you_name_input.value)).classes('ml-2')

        # Select Setting
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Select Setting:").classes('w-1/4')
            settings_dropdown = ui.select(
                options=[s['name'] for s in ALL_SETTINGS],
                on_change=select_setting,
                label="Choose a setting"
            ).classes('flex-grow')

        # Add Characters Dropdown
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Select Character:").classes('w-1/4')
            character_dropdown = ui.select(
                options=list(ALL_CHARACTERS.keys()),
                on_change=add_character_from_dropdown,
                label="Choose a character"
            ).classes('flex-grow')

        # List of Added Characters
        with ui.column().classes('w-full mb-4'):
            ui.label("Added Characters:").classes('font-semibold mb-2')
            added_characters_container = ui.row().classes('flex-wrap gap-2')
            refresh_added_characters()

        # Toggle Automatic Chat
        with ui.row().classes('w-full items-center mb-4'):
            auto_switch = ui.switch('Automatic Chat', value=False, on_change=toggle_automatic_chat).classes('mr-2')
            ui.button("Stop", on_click=lambda: chat_manager.stop_automatic_chat()).classes('ml-auto')

        # Chat Display Area
        chat_display = ui.column().classes('space-y-2 p-4 bg-gray-100 rounded h-96 overflow-y-auto')

        # Next Speaker Label
        next_speaker_label = ui.label("Next speaker:").classes('text-sm text-gray-700')
        update_next_speaker_label()

        # Next Button (for manual progression)
        next_button = ui.button("Next", on_click=lambda: asyncio.create_task(next_character_response()))
        next_button.props('outline')
        next_button.enabled = not chat_manager.automatic_running

        # User Input Field and Send Button
        with ui.row().classes('w-full items-center mt-4'):
            user_input = ui.input(placeholder='Enter your message...').classes('flex-grow')
            ui.button('Send', on_click=lambda: asyncio.create_task(send_user_message())).classes('ml-2')

    app.on_startup(lambda: asyncio.create_task(automatic_conversation()))

def select_setting(event):
    chosen_name = event.value
    for s in ALL_SETTINGS:
        if s['name'] == chosen_name:
            chat_manager.set_current_setting(s['description'])
            break

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
    next_button.enabled = not chat_manager.automatic_running

def set_you_name(name: str):
    chat_manager.set_you_name(name)
    update_chat_display()

def add_character_from_dropdown(event):
    if event.value:
        char_name = event.value
        char = ALL_CHARACTERS.get(char_name, None)
        if char:
            if char_name in chat_manager.get_character_names():
                chat_manager.add_message("System", f"Character '{char_name}' is already added.", visible=True)
            else:
                chat_manager.add_character(char_name, char)
                chat_manager.add_message("System", f"Character '{char_name}' added.", visible=True)
                refresh_added_characters()
        else:
            chat_manager.add_message("System", f"Character '{char_name}' not found.", visible=True)

        update_chat_display()
        update_next_speaker_label()
        character_dropdown.value = None

def remove_character(name: str):
    chat_manager.remove_character(name)
    chat_manager.add_message("System", f"Character '{name}' removed.", visible=True)
    refresh_added_characters()
    update_chat_display()
    update_next_speaker_label()

async def automatic_conversation():
    while True:
        await asyncio.sleep(2)
        if chat_manager.automatic_running:
            next_char = chat_manager.next_speaker()
            if next_char:
                await generate_character_message(next_char)
                chat_manager.advance_turn()
                update_next_speaker_label()

async def next_character_response():
    if chat_manager.automatic_running:
        return
    next_char = chat_manager.next_speaker()
    if next_char:
        await generate_character_message(next_char)
        chat_manager.advance_turn()
        update_next_speaker_label()

async def generate_character_message(character_name: str):
    prompt = chat_manager.build_prompt_for_character(character_name)
    # Indicate that character is "thinking"
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

    # Safety check to avoid IndexError if chat_history was cleared by summarization
    if chat_manager.chat_history:
        chat_manager.chat_history[-1]["message"] = formatted_message
    update_chat_display()

async def send_user_message():
    if not user_input.value:
        return

    chat_manager.add_message(chat_manager.you_name, user_input.value, visible=True)
    update_chat_display()
    user_input.value = ''
    user_input.update()

    if not chat_manager.automatic_running:
        update_next_speaker_label()

def update_chat_display():
    chat_display.clear()
    for entry in chat_manager.chat_history:
        name = entry["sender"]
        message = entry["message"]
        timestamp = entry["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"**{name}** [{timestamp}]:\n\n{message}"
        with chat_display:
            ui.markdown(formatted_message)

def start_ui():
    main_page()
    ui.run(reload=False)
