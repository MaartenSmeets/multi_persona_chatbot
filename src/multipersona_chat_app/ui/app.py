import os
import uuid
import asyncio
import yaml
from datetime import datetime
from nicegui import ui, app, run

from llm.ollama_client import OllamaClient
from models.interaction import Interaction
from models.character import Character
from chats.chat_manager import ChatManager

# Initialize global variables
llm_client = None
chat_manager = None

user_input = None
you_name_input = None
character_dropdown = None
added_characters_container = None
next_speaker_label = None
next_button = None
settings_dropdown = None
session_dropdown = None
chat_display = None  # Ensure it's accessible globally

CHARACTERS_DIR = "src/multipersona_chat_app/characters"
ALL_CHARACTERS = {}
ALL_SETTINGS = []
DB_PATH = os.path.join("output", "conversations.db")

def load_settings():
    """Load settings from the YAML configuration file."""
    settings_path = os.path.join("src", "multipersona_chat_app", "config", "settings.yaml")
    try:
        with open(settings_path, 'r') as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"Error loading settings: {e}")
        return []

def get_available_characters(directory):
    """Retrieve all available characters from the specified directory."""
    characters = {}
    try:
        for filename in os.listdir(directory):
            if filename.endswith('.yaml'):
                yaml_path = os.path.join(directory, filename)
                try:
                    char = Character.from_yaml(yaml_path)
                    characters[char.name] = char
                except Exception as e:
                    print(f"Error loading character from {yaml_path}: {e}")
    except FileNotFoundError:
        print(f"Characters directory '{directory}' not found.")
    return characters

def init_chat_manager(session_id: str):
    """Initialize the ChatManager and LLM client with the given session ID."""
    global chat_manager, llm_client
    chat_manager = ChatManager(you_name="You", session_id=session_id)
    llm_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=Interaction)

def refresh_added_characters():
    """Refresh the UI component that displays added characters."""
    if added_characters_container is not None:
        added_characters_container.clear()
        for char_name in chat_manager.get_character_names():
            with added_characters_container:
                with ui.card().classes('p-2 flex items-center'):
                    ui.label(char_name).classes('flex-grow')
                    ui.button(
                        'Remove',
                        on_click=lambda _, name=char_name: remove_character(name),
                    ).classes('ml-2 bg-red-500 text-white')
    else:
        print("Error: added_characters_container is not initialized.")

def update_next_speaker_label():
    """Update the label that shows who the next speaker is."""
    ns = chat_manager.next_speaker()
    if ns:
        next_speaker_label.text = f"Next speaker: {ns}"
    else:
        next_speaker_label.text = "No characters available."
    next_speaker_label.update()

def populate_session_dropdown():
    """Populate the session dropdown with available sessions and select the current one."""
    sessions = chat_manager.db.get_all_sessions()
    session_names = [s['name'] for s in sessions]
    session_dropdown.options = session_names
    current = [s for s in sessions if s['session_id'] == chat_manager.session_id]
    if current:
        session_dropdown.value = current[0]['name']
    else:
        session_dropdown.value = None  # No session selected

def on_session_select(event):
    """Handle the event when a session is selected from the dropdown."""
    selected_name = event.value
    sessions = chat_manager.db.get_all_sessions()
    for s in sessions:
        if s['name'] == selected_name:
            load_session(s['session_id'])
            return

def create_new_session(_):
    """Create a new session and load it."""
    new_id = str(uuid.uuid4())
    chat_manager.db.create_session(new_id, f"Session {new_id}")
    load_session(new_id)

def delete_session(_):
    """Delete the selected session and handle UI updates."""
    sessions = chat_manager.db.get_all_sessions()
    if session_dropdown.value:
        to_delete = [s for s in sessions if s['name'] == session_dropdown.value]
        if to_delete:
            sid = to_delete[0]['session_id']
            chat_manager.db.delete_session(sid)
            # If the current session is deleted, create and load a new one
            if sid == chat_manager.session_id:
                remaining_sessions = chat_manager.db.get_all_sessions()
                if remaining_sessions:
                    new_session = remaining_sessions[0]
                    load_session(new_session['session_id'])
                else:
                    new_id = str(uuid.uuid4())
                    chat_manager.db.create_session(new_id, f"Session {new_id}")
                    load_session(new_id)
            else:
                populate_session_dropdown()

def load_session(session_id: str):
    """Load a session by its ID and update the UI accordingly."""
    global chat_manager
    you_name = chat_manager.you_name
    setting = chat_manager.current_setting
    init_chat_manager(session_id)  # Reinitialize chat_manager with the new session
    chat_manager.set_you_name(you_name)
    chat_manager.set_current_setting(setting)
    refresh_added_characters()
    show_chat_display.refresh()
    update_next_speaker_label()
    populate_session_dropdown()

def select_setting(event):
    """Handle the event when a setting is selected from the dropdown."""
    chosen_name = event.value
    for s in ALL_SETTINGS:
        if s['name'] == chosen_name:
            chat_manager.set_current_setting(s['description'])
            break

def toggle_automatic_chat(e):
    """Toggle the automatic chat feature on or off."""
    if e.value:
        if not chat_manager.get_character_names():
            chat_manager.add_message("System", "No characters added. Please add characters to start automatic chat.", visible=True, message_type="system")
            show_chat_display.refresh()
            e.value = False
            return
        chat_manager.start_automatic_chat()
    else:
        chat_manager.stop_automatic_chat()
    next_button.enabled = not chat_manager.automatic_running
    next_button.update()

def set_you_name(_=None):
    """Set the user's name based on the input field."""
    if you_name_input.value.strip():
        chat_manager.set_you_name(you_name_input.value.strip())
        show_chat_display.refresh()

@ui.refreshable
def show_chat_display():
    """Refresh the chat display area with the latest messages."""
    chat_display.clear()
    msgs = chat_manager.db.get_messages(chat_manager.session_id)
    with chat_display:
        for entry in msgs:
            name = entry["sender"]
            message = entry["message"]
            timestamp = entry["timestamp"]
            dt = datetime.fromisoformat(timestamp)
            human_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
            if entry.get("message_type") == "system":
                formatted_message = f"**{name}** [{human_timestamp}]:\n\n*{message}*"
            elif entry.get("message_type") == "character":
                formatted_message = f"**{name}** [{human_timestamp}]:\n\n{message}"
            else:
                formatted_message = f"**{name}** [{human_timestamp}]:\n\n{message}"
            ui.markdown(formatted_message)

async def automatic_conversation():
    """Handle automatic conversation between characters."""
    while True:
        await asyncio.sleep(2)
        if chat_manager.automatic_running:
            next_char = chat_manager.next_speaker()
            if next_char:
                await generate_character_message(next_char)
                chat_manager.advance_turn()
                update_next_speaker_label()

async def next_character_response():
    """Generate the next character's response manually."""
    if chat_manager.automatic_running:
        return
    next_char = chat_manager.next_speaker()
    if next_char:
        await generate_character_message(next_char)
        chat_manager.advance_turn()
        update_next_speaker_label()

async def generate_character_introduction_message(character_name: str):
    """Generate an introduction message for a new character."""
    (system_prompt, user_prompt) = chat_manager.build_prompt_for_character(character_name)
    user_prompt += "\n\nYou have just arrived in the conversation. Introduce yourself in detail, describing your physical appearance, attire, and how it fits with the setting and with any prior context that may be relevant."

    try:
        interaction = await run.io_bound(llm_client.generate, prompt=user_prompt, system=system_prompt)
        if isinstance(interaction, Interaction):
            formatted_message = f"*{interaction.action}*\n{interaction.dialogue}"
        else:
            formatted_message = str(interaction) if interaction else "No introduction."
    except Exception as e:
        formatted_message = f"Error generating introduction: {str(e)}"

    chat_manager.add_message(character_name, formatted_message, visible=True, message_type="character")
    show_chat_display.refresh()

async def generate_character_message(character_name: str):
    """Generate a message from a character."""
    (system_prompt, user_prompt) = chat_manager.build_prompt_for_character(character_name)

    try:
        interaction = await run.io_bound(llm_client.generate, prompt=user_prompt, system=system_prompt)
        if isinstance(interaction, Interaction):
            formatted_message = f"*{interaction.action}*\n{interaction.dialogue}"
        else:
            formatted_message = str(interaction) if interaction else "No response."
    except Exception as e:
        formatted_message = f"Error: {str(e)}"

    chat_manager.add_message(character_name, formatted_message, visible=True, message_type="character")
    show_chat_display.refresh()

async def send_user_message():
    """Send the user's message to the chat."""
    if not user_input.value.strip():
        return

    chat_manager.add_message(chat_manager.you_name, user_input.value.strip(), visible=True, message_type="user")
    show_chat_display.refresh()
    user_input.value = ''
    user_input.update()

    if not chat_manager.automatic_running:
        update_next_speaker_label()

async def add_character_from_dropdown(event):
    """Add a character to the chat based on dropdown selection."""
    if not event.value:
        return
    char_name = event.value
    char = ALL_CHARACTERS.get(char_name, None)
    if char:
        if char_name not in chat_manager.get_character_names():
            chat_manager.add_character(char_name, char)
            refresh_added_characters()

            # Check if character has already spoken before introducing
            msgs = chat_manager.db.get_messages(chat_manager.session_id)
            previously_spoken = any(m for m in msgs if m["sender"] == char_name)
            if not previously_spoken:
                await generate_character_introduction_message(char_name)
            else:
                show_chat_display.refresh()

    update_next_speaker_label()
    character_dropdown.value = None
    character_dropdown.update()

def remove_character(name: str):
    """Remove a character from the chat."""
    chat_manager.remove_character(name)
    refresh_added_characters()
    show_chat_display.refresh()
    update_next_speaker_label()

def main_page():
    """Set up the main UI components of the application."""
    global user_input, you_name_input, character_dropdown, added_characters_container
    global next_speaker_label, next_button, settings_dropdown, session_dropdown, chat_display
    global ALL_CHARACTERS, ALL_SETTINGS

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
            ).classes('flex-grow')

            ui.button("New Session", on_click=create_new_session).classes('ml-2')
            ui.button("Delete Session", on_click=delete_session).classes('ml-2 bg-red-500 text-white')

        # Configure "Your Name"
        with ui.row().classes('w-full items-center mb-4'):
            ui.label("Your name:").classes('w-1/4')
            you_name_input = ui.input(value=chat_manager.you_name).classes('flex-grow')
            ui.button("Set", on_click=set_you_name).classes('ml-2')

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

        # Next Speaker Label
        next_speaker_label = ui.label("Next speaker:").classes('text-sm text-gray-700')
        update_next_speaker_label()

        # Next Button (for manual progression)
        next_button = ui.button("Next", on_click=lambda: asyncio.create_task(next_character_response()))
        next_button.props('outline')
        next_button.enabled = not chat_manager.automatic_running
        next_button.update()

        # Chat Display
        chat_display = ui.column().classes('space-y-2 p-4 bg-gray-100 rounded h-96 overflow-y-auto')
        show_chat_display()

        # User Input Field and Send Button
        with ui.row().classes('w-full items-center mt-4'):
            user_input = ui.input(placeholder='Enter your message...').classes('flex-grow')
            ui.button('Send', on_click=lambda: asyncio.create_task(send_user_message())).classes('ml-2')

        # Now assign the on_change handler and set the default session value
        session_dropdown.on('change', on_session_select)
        session_dropdown.value = chat_manager.get_session_name()  # Set default selected session

def start_ui():
    """Initialize the application and start the UI."""
    default_session = str(uuid.uuid4())
    cm_temp = ChatManager()
    sessions = cm_temp.db.get_all_sessions()
    if not sessions:
        cm_temp.db.create_session(default_session, f"Session {default_session}")
        init_chat_manager(default_session)
    else:
        init_chat_manager(sessions[0]['session_id'])

    main_page()

    # Start the background automatic conversation task
    app.on_startup(lambda: asyncio.create_task(automatic_conversation()))

    ui.run(reload=False)

if __name__ == "__main__":
    start_ui()
