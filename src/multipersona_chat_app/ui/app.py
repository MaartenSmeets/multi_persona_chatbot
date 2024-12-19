import os
from nicegui import ui, app
from llm.ollama_client import OllamaClient
from models.interaction import Interaction
from models.character import Character
from chats.chat_manager import ChatManager
import asyncio
import yaml
import uuid
from datetime import datetime

llm_client = None
chat_manager = None

user_input = None
chat_display = None
you_name_input = None
character_dropdown = None
added_characters_container = None  
next_speaker_label = None
next_button = None
settings_dropdown = None
session_dropdown = None

CHARACTERS_DIR = "src/multipersona_chat_app/characters"
ALL_CHARACTERS = {}
ALL_SETTINGS = []
DB_PATH = os.path.join("output", "conversations.db")

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

def init_chat_manager(session_id: str):
    global chat_manager, llm_client
    chat_manager = ChatManager(you_name="You", session_id=session_id)
    llm_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=Interaction)

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

def populate_session_dropdown():
    sessions = chat_manager.db.get_all_sessions()
    session_dropdown.options = [s['name'] for s in sessions]
    current = [s for s in sessions if s['session_id'] == chat_manager.session_id]
    if current:
        session_dropdown.value = current[0]['name']

def on_session_select(event):
    sessions = chat_manager.db.get_all_sessions()
    selected_name = event.value
    for s in sessions:
        if s['name'] == selected_name:
            load_session(s['session_id'])
            return

def create_new_session(_):
    new_id = str(uuid.uuid4())
    chat_manager.db.create_session(new_id, f"Session {new_id}")
    load_session(new_id)

def delete_session(_):
    sessions = chat_manager.db.get_all_sessions()
    if session_dropdown.value:
        to_delete = [s for s in sessions if s['name'] == session_dropdown.value]
        if to_delete:
            sid = to_delete[0]['session_id']
            chat_manager.db.delete_session(sid)
            # If current session is deleted, create a new one
            if sid == chat_manager.session_id:
                new_id = str(uuid.uuid4())
                chat_manager.db.create_session(new_id, f"Session {new_id}")
                load_session(new_id)
            else:
                populate_session_dropdown()

def load_session(session_id: str):
    global chat_manager
    you_name = chat_manager.you_name
    setting = chat_manager.current_setting
    chat_manager = ChatManager(you_name=you_name, session_id=session_id)
    chat_manager.set_current_setting(setting)
    refresh_added_characters()
    update_chat_display()
    update_next_speaker_label()
    populate_session_dropdown()

def select_setting(event):
    chosen_name = event.value
    for s in ALL_SETTINGS:
        if s['name'] == chosen_name:
            chat_manager.set_current_setting(s['description'])
            break

def toggle_automatic_chat(e):
    if e.value:
        if not chat_manager.get_character_names():
            chat_manager.add_message("System", "No characters added. Please add characters to start automatic chat.", visible=True, message_type="system")
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

async def add_character_from_dropdown(event):
    if event.value:
        char_name = event.value
        char = ALL_CHARACTERS.get(char_name, None)
        if char:
            if char_name not in chat_manager.get_character_names():
                chat_manager.add_character(char_name, char)
                refresh_added_characters()
                await generate_character_introduction_message(char_name)
        update_chat_display()
        update_next_speaker_label()
        character_dropdown.value = None

def remove_character(name: str):
    chat_manager.remove_character(name)
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

async def generate_character_introduction_message(character_name: str):
    (system_prompt, user_prompt) = chat_manager.build_prompt_for_character(character_name)
    user_prompt += "\n\nYou have just arrived in the conversation. Introduce yourself, describing your physical appearance, attire, and how it fits with the setting and with any prior context that may be relevant."

    try:
        interaction = await asyncio.to_thread(llm_client.generate, prompt=user_prompt, system=system_prompt)
        if isinstance(interaction, Interaction):
            affect = interaction.affect
            purpose = interaction.purpose
            formatted_message = f"*{interaction.action}*\n{interaction.dialogue}"
        else:
            affect = None
            purpose = None
            formatted_message = str(interaction) if interaction else "No introduction."
    except Exception as e:
        formatted_message = f"Error generating introduction: {str(e)}"
        affect = None
        purpose = None

    chat_manager.add_message(character_name, formatted_message, visible=True, message_type="character", affect=affect, purpose=purpose)
    update_chat_display()

async def generate_character_message(character_name: str):
    (system_prompt, user_prompt) = chat_manager.build_prompt_for_character(character_name)

    try:
        interaction = await asyncio.to_thread(llm_client.generate, prompt=user_prompt, system=system_prompt)
        if isinstance(interaction, Interaction):
            affect = interaction.affect
            purpose = interaction.purpose
            formatted_message = f"*{interaction.action}*\n{interaction.dialogue}"
        else:
            affect = None
            purpose = None
            formatted_message = str(interaction) if interaction else "No response."
    except Exception as e:
        formatted_message = f"Error: {str(e)}"
        affect = None
        purpose = None

    chat_manager.add_message(character_name, formatted_message, visible=True, message_type="character", affect=affect, purpose=purpose)
    update_chat_display()

async def send_user_message():
    if not user_input.value:
        return

    chat_manager.add_message(chat_manager.you_name, user_input.value, visible=True, message_type="user")
    update_chat_display()
    user_input.value = ''
    user_input.update()

    if not chat_manager.automatic_running:
        update_next_speaker_label()

def update_chat_display():
    chat_display.clear()
    msgs = chat_manager.db.get_messages(chat_manager.session_id)
    for entry in msgs:
        name = entry["sender"]
        message = entry["message"]
        timestamp = entry["timestamp"]
        # Convert timestamp to a more human-friendly format
        dt = datetime.fromisoformat(timestamp)
        human_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
        formatted_message = f"**{name}** [{human_timestamp}]:\n\n{message}"
        with chat_display:
            ui.markdown(formatted_message)

def main_page():
    global user_input, chat_display, you_name_input, character_dropdown, added_characters_container, next_speaker_label, next_button, ALL_CHARACTERS, ALL_SETTINGS, settings_dropdown, session_dropdown

    ALL_CHARACTERS = get_available_characters(CHARACTERS_DIR)
    ALL_SETTINGS = load_settings()

    with ui.column().classes('w-full max-w-2xl mx-auto'):
        ui.label('Multipersona Chat Application').classes('text-2xl font-bold mb-4')

        # Session Management
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Session:").classes('w-1/4')
            session_dropdown = ui.select(
                options=[s['name'] for s in chat_manager.db.get_all_sessions()],
                label="Choose a session",
                on_change=on_session_select
            ).classes('flex-grow')

            ui.button("New Session", on_click=create_new_session).classes('ml-2')
            ui.button("Delete Session", on_click=delete_session).classes('ml-2 bg-red-500 text-white')

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
                on_change=lambda e: asyncio.create_task(add_character_from_dropdown(e)),
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
    update_chat_display()
    populate_session_dropdown()

def start_ui():
    default_session = str(uuid.uuid4())
    cm_temp = ChatManager()
    sessions = cm_temp.db.get_all_sessions()
    if not sessions:
        cm_temp.db.create_session(default_session, f"Session {default_session}")
        init_chat_manager(default_session)
    else:
        init_chat_manager(sessions[0]['session_id'])

    main_page()
    ui.run(reload=False)
