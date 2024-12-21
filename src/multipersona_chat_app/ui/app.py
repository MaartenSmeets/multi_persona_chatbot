# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/ui/app.py

import os
import uuid
import asyncio
import yaml
from datetime import datetime
from nicegui import ui, app, run
import logging
from typing import List, Dict
from llm.ollama_client import OllamaClient
from models.interaction import Interaction
from models.character import Character
from chats.chat_manager import ChatManager
from utils import load_settings, get_available_characters

logger = logging.getLogger(__name__)

llm_client = None
introduction_llm_client = None  # Dedicated for intros
chat_manager = None

user_input = None
you_name_input = None
character_dropdown = None
added_characters_container = None
next_speaker_label = None
next_button = None
settings_dropdown = None
session_dropdown = None
chat_display = None
auto_timer = None
current_location_label = None
llm_busy_label = None

CHARACTERS_DIR = "src/multipersona_chat_app/characters"
ALL_CHARACTERS = {}
ALL_SETTINGS = []

# Track which characters have given their introduction
introductions_given = {}

llm_busy = False

def init_chat_manager(session_id: str, settings: List[Dict]):
    global chat_manager, llm_client, introduction_llm_client
    logger.debug(f"Initializing ChatManager with session_id: {session_id}")
    chat_manager = ChatManager(you_name="You", session_id=session_id, settings=settings)
    try:
        # Normal conversation client (expects structured JSON -> Interaction model)
        llm_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=Interaction)
        logger.info("LLM Client initialized successfully (structured).")
    except Exception as e:
        logger.error(f"Error initializing LLM Client: {e}")

    try:
        # Introduction client (unstructured, no output model)
        introduction_llm_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=None)
        logger.info("Introduction LLM Client initialized successfully (unstructured).")
    except Exception as e:
        logger.error(f"Error initializing Introduction LLM Client: {e}")

def refresh_added_characters():
    logger.debug("Refreshing added characters in UI.")
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
        logger.info("Added characters refreshed in UI.")
    else:
        logger.error("added_characters_container is not initialized.")

def update_next_speaker_label():
    ns = chat_manager.next_speaker()
    if ns:
        if next_speaker_label is not None:
            next_speaker_label.text = f"Next speaker: {ns}"
            next_speaker_label.update()
        else:
            logger.error("next_speaker_label is not initialized.")
    else:
        if next_speaker_label is not None:
            next_speaker_label.text = "No characters available."
            next_speaker_label.update()
        else:
            logger.error("next_speaker_label is not initialized.")

def populate_session_dropdown():
    logger.debug("Populating session dropdown.")
    sessions = chat_manager.db.get_all_sessions()
    session_names = [s['name'] for s in sessions]
    session_dropdown.options = session_names
    current = [s for s in sessions if s['session_id'] == chat_manager.session_id]
    if current:
        session_dropdown.value = current[0]['name']
        logger.info(f"Session dropdown set to current session: {current[0]['name']}")
    else:
        session_dropdown.value = None

def on_session_select(event):
    selected_name = event.value
    logger.info(f"Session selected: {selected_name}")
    sessions = chat_manager.db.get_all_sessions()
    for s in sessions:
        if s['name'] == selected_name:
            load_session(s['session_id'])
            return
    logger.warning(f"Selected session name '{selected_name}' not found.")

def create_new_session(_):
    new_id = str(uuid.uuid4())
    session_name = f"Session {new_id}"
    logger.info(f"Creating new session: {session_name} with ID: {new_id}")
    chat_manager.db.create_session(new_id, session_name)

    intimate_setting = next((s for s in ALL_SETTINGS if s['name'] == "Intimate Setting"), None)
    if intimate_setting:
        chat_manager.set_current_setting(
            intimate_setting['name'],
            intimate_setting['description'],
            intimate_setting['start_location']
        )
        settings_dropdown.value = intimate_setting['name']
        settings_dropdown.update()
    else:
        logger.error("'Intimate Setting' not found in settings. No default setting applied.")

    load_session(new_id)

def delete_session(_):
    logger.info("Attempting to delete selected session.")
    sessions = chat_manager.db.get_all_sessions()
    if session_dropdown.value:
        to_delete = [s for s in sessions if s['name'] == session_dropdown.value]
        if to_delete:
            sid = to_delete[0]['session_id']
            logger.info(f"Deleting session: {to_delete[0]['name']} with ID: {sid}")
            chat_manager.db.delete_session(sid)
            if sid == chat_manager.session_id:
                remaining_sessions = chat_manager.db.get_all_sessions()
                if remaining_sessions:
                    new_session = remaining_sessions[0]
                    logger.info(f"Loading remaining session: {new_session['name']} with ID: {new_session['session_id']}")
                    load_session(new_session['session_id'])
                else:
                    new_id = str(uuid.uuid4())
                    new_session_name = f"Session {new_id}"
                    chat_manager.db.create_session(new_id, new_session_name)
                    intimate_setting = next((s for s in ALL_SETTINGS if s['name'] == "Intimate Setting"), None)
                    if intimate_setting:
                        chat_manager.set_current_setting(
                            intimate_setting['name'],
                            intimate_setting['description'],
                            intimate_setting['start_location']
                        )
                        settings_dropdown.value = intimate_setting['name']
                        settings_dropdown.update()
                    else:
                        logger.error("'Intimate Setting' not found. No default setting on new session.")
                    logger.info(f"No remaining sessions. Created and loading new session: {new_session_name}")
                    load_session(new_id)
            else:
                populate_session_dropdown()
        else:
            logger.warning(f"Session to delete '{session_dropdown.value}' not found.")
    else:
        logger.warning("No session selected to delete.")

def load_session(session_id: str):
    logger.debug(f"Loading session with ID: {session_id}")
    chat_manager.session_id = session_id
    chat_manager.characters = {}
    introductions_given.clear()

    current_setting_name = chat_manager.db.get_current_setting(session_id)
    setting = next((s for s in ALL_SETTINGS if s['name'] == current_setting_name), None)
    if setting:
        chat_manager.set_current_setting(
            setting['name'],
            setting['description'],
            setting['start_location']
        )
        settings_dropdown.value = setting['name']
        settings_dropdown.update()
    else:
        intimate_setting = next((s for s in ALL_SETTINGS if s['name'] == "Intimate Setting"), None)
        if intimate_setting:
            chat_manager.set_current_setting(
                intimate_setting['name'],
                intimate_setting['description'],
                intimate_setting['start_location']
            )
            settings_dropdown.value = intimate_setting['name']
            settings_dropdown.update()
        else:
            logger.error("No setting found and 'Intimate Setting' not available.")

    session_chars = chat_manager.db.get_session_characters(session_id)
    for c_name in session_chars:
        if c_name in ALL_CHARACTERS:
            chat_manager.add_character(c_name, ALL_CHARACTERS[c_name])
            introductions_given[c_name] = False
        else:
            logger.warning(f"Character '{c_name}' found in DB but not in ALL_CHARACTERS.")

    refresh_added_characters()
    show_chat_display.refresh()
    update_next_speaker_label()
    populate_session_dropdown()
    display_current_location()
    logger.info(f"Session loaded: {session_id}")

def select_setting(event):
    chosen_name = event.value
    logger.info(f"Setting selected: {chosen_name}")
    setting = next((s for s in ALL_SETTINGS if s['name'] == chosen_name), None)
    if setting:
        try:
            chat_manager.set_current_setting(
                setting['name'],
                setting['description'],
                setting['start_location']
            )
            settings_dropdown.value = setting['name']
            settings_dropdown.update()
            display_current_location()
        except Exception as pe:
            logger.error(f"Error while setting current setting: {pe}")
            ui.notify(str(pe), type='error')
    else:
        logger.warning(f"Selected setting '{chosen_name}' not found.")

def toggle_automatic_chat(e):
    state = "enabled" if e.value else "disabled"
    logger.info(f"Automatic chat toggled {state}.")
    if e.value:
        if not chat_manager.get_character_names():
            logger.warning("No characters added. Cannot start automatic chat.")
            ui.notify("No characters added. Cannot start automatic chat.", type='warning')
            e.value = False
            return
        chat_manager.start_automatic_chat()
        if auto_timer:
            auto_timer.active = True
            logger.info("Automatic chat started.")
    else:
        chat_manager.stop_automatic_chat()
        if auto_timer:
            auto_timer.active = False
            logger.info("Automatic chat stopped.")
    next_button.enabled = not chat_manager.automatic_running
    next_button.update()

def set_you_name(_=None):
    name = you_name_input.value.strip()
    if name:
        logger.info(f"Setting user name to: {name}")
        chat_manager.set_you_name(name)
        show_chat_display.refresh()
    else:
        logger.warning("Attempted to set empty user name.")

@ui.refreshable
def show_chat_display():
    logger.debug("Refreshing chat display.")
    chat_display.clear()
    msgs = chat_manager.db.get_messages(chat_manager.session_id)
    with chat_display:
        for entry in msgs:
            name = entry["sender"]
            message = entry["message"]
            timestamp = entry["created_at"]
            dt = datetime.fromisoformat(timestamp)
            human_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
            if entry.get("message_type") == "system":
                formatted_message = f"**{name}** [{human_timestamp}]:\n\n*{message}*"
            elif entry.get("message_type") == "character":
                formatted_message = f"**{name}** [{human_timestamp}]:\n\n{message}"
            else:
                formatted_message = f"**{name}** [{human_timestamp}]:\n\n{message}"
            ui.markdown(formatted_message)
    logger.debug("Chat display refreshed.")

@ui.refreshable
def display_current_location():
    if chat_manager.current_location:
        current_location_label.text = f"Current Location: {chat_manager.current_location}"
    else:
        current_location_label.text = "Current Location: Not set."
    current_location_label.update()

async def automatic_conversation():
    if chat_manager.automatic_running:
        logger.debug("Automatic conversation active. Generating next message.")
        next_char = chat_manager.next_speaker()
        if next_char:
            await generate_character_message(next_char)
            chat_manager.advance_turn()
            update_next_speaker_label()

async def next_character_response():
    if chat_manager.automatic_running:
        logger.debug("Automatic conversation is running. Manual next response ignored.")
        return
    next_char = chat_manager.next_speaker()
    if next_char:
        logger.info(f"Generating response for character: {next_char}")
        await generate_character_message(next_char)
        chat_manager.advance_turn()
        update_next_speaker_label()

async def generate_character_introduction_message(character_name: str):
    logger.info(f"Generating introduction message for character: {character_name}")

    # BUILD THE SEPARATE, UNSTRUCTURED INTRO PROMPTS:
    (system_prompt, introduction_prompt) = chat_manager.build_introduction_prompts_for_character(character_name)

    global llm_busy
    llm_busy = True
    llm_busy_label.visible = True
    llm_busy_label.update()

    try:
        introduction_response = await run.io_bound(
            introduction_llm_client.generate,
            prompt=introduction_prompt,
            system=system_prompt
        )
        # introduction_response will be a raw string or None
        if isinstance(introduction_response, str) and introduction_response.strip():
            formatted_message = introduction_response.strip()
            chat_manager.add_message(
                character_name,
                formatted_message,
                visible=True,
                message_type="character",
            )
            introductions_given[character_name] = True
            logger.info(f"Introduction message generated for {character_name}.")
        else:
            logger.warning(f"Invalid or no response received for introduction of {character_name}. Not storing.")
    except Exception as e:
        logger.error(f"Error generating introduction for {character_name}: {e}")
    finally:
        llm_busy = False
        llm_busy_label.visible = False
        llm_busy_label.update()

    show_chat_display.refresh()

async def generate_character_message(character_name: str):
    logger.info(f"Generating message for character: {character_name}")
    # Check if this character has introduced themselves
    msgs = chat_manager.db.get_messages(chat_manager.session_id)
    char_spoken_before = any(m for m in msgs if m["sender"] == character_name and m["message_type"] == "character")

    if character_name not in introductions_given:
        introductions_given[character_name] = False

    # If not introduced yet, do the introduction
    if not introductions_given[character_name] and not char_spoken_before:
        await generate_character_introduction_message(character_name)
        return

    (system_prompt, user_prompt) = chat_manager.build_prompt_for_character(character_name)

    global llm_busy
    llm_busy = True
    llm_busy_label.visible = True
    llm_busy_label.update()

    try:
        interaction = await run.io_bound(
            llm_client.generate,
            prompt=user_prompt,
            system=system_prompt
        )
        if isinstance(interaction, Interaction):
            # Validate the structured fields
            if (not interaction.purpose.strip()
                or not interaction.affect.strip()
                or not interaction.action.strip()):
                logger.warning("Received incomplete interaction fields. Not storing message.")
            else:
                formatted_message = f"*{interaction.action}*\n{interaction.dialogue}"
                msg_id = chat_manager.add_message(
                    character_name,
                    formatted_message,
                    visible=True,
                    message_type="character",
                    affect=interaction.affect,
                    purpose=interaction.purpose
                )
                if interaction.new_location.strip():
                    await chat_manager.handle_new_location_for_character(character_name, interaction.new_location, msg_id)
                logger.debug(f"Message generated for {character_name}: {interaction.dialogue}")
        else:
            logger.warning(f"No valid interaction or no response for {character_name}. Not storing.")
    except Exception as e:
        logger.error(f"Error generating message for {character_name}: {e}")
    finally:
        llm_busy = False
        llm_busy_label.visible = False
        llm_busy_label.update()

    show_chat_display.refresh()

async def send_user_message():
    message = user_input.value.strip()
    if not message:
        logger.warning("Attempted to send empty user message. Not allowed.")
        return

    logger.info(f"User sent message: {message}")
    chat_manager.add_message(
        chat_manager.you_name,
        message,
        visible=True,
        message_type="user"
    )
    show_chat_display.refresh()
    user_input.value = ''
    user_input.update()

    if not chat_manager.automatic_running:
        update_next_speaker_label()

async def add_character_from_dropdown(event):
    if not event.value:
        return
    char_name = event.value
    logger.info(f"Adding character from dropdown: {char_name}")
    char = ALL_CHARACTERS.get(char_name, None)
    if char:
        if char_name not in chat_manager.get_character_names():
            chat_manager.add_character(char_name, char)
            chat_manager.db.add_character_to_session(chat_manager.session_id, char_name)
            introductions_given[char_name] = False
            refresh_added_characters()
            logger.info(f"Character '{char_name}' added to chat.")
            show_chat_display.refresh()
        else:
            logger.warning(f"Character '{char_name}' is already added.")
    else:
        logger.error(f"Character '{char_name}' not found in ALL_CHARACTERS.")

    update_next_speaker_label()
    character_dropdown.value = None
    character_dropdown.update()

def remove_character(name: str):
    logger.info(f"Removing character: {name}")
    chat_manager.remove_character(name)
    chat_manager.db.remove_character_from_session(chat_manager.session_id, name)
    if name in introductions_given:
        del introductions_given[name]
    refresh_added_characters()
    show_chat_display.refresh()
    update_next_speaker_label()

def main_page():
    global user_input, you_name_input, character_dropdown, added_characters_container
    global next_speaker_label, next_button, settings_dropdown, session_dropdown, chat_display
    global current_location_label, llm_busy_label
    global ALL_CHARACTERS, ALL_SETTINGS

    logger.debug("Setting up main UI page.")
    ALL_CHARACTERS = get_available_characters(CHARACTERS_DIR)
    ALL_SETTINGS = load_settings()

    with ui.grid(columns=2).style('grid-template-columns: 1fr 2fr; height: 100vh;'):
        with ui.card().style('height: 100vh; overflow-y: auto;'):
            ui.label('Multipersona Chat Application').classes('text-2xl font-bold mb-4')

            with ui.row().classes('w-full items-center mb-4'):
                ui.label("Session:").classes('w-1/4')
                global session_dropdown
                session_dropdown = ui.select(
                    options=[s['name'] for s in chat_manager.db.get_all_sessions()],
                    label="Choose a session",
                ).classes('flex-grow')

                ui.button("New Session", on_click=create_new_session).classes('ml-2')
                ui.button("Delete Session", on_click=delete_session).classes('ml-2 bg-red-500 text-white')

            with ui.row().classes('w-full items-center mb-4'):
                ui.label("Your name:").classes('w-1/4')
                you_name_input = ui.input(value=chat_manager.you_name).classes('flex-grow')
                ui.button("Set", on_click=set_you_name).classes('ml-2')

            with ui.row().classes('w-full items-center mb-4'):
                ui.label("Select Setting:").classes('w-1/4')
                settings_dropdown = ui.select(
                    options=[s['name'] for s in ALL_SETTINGS],
                    on_change=select_setting,
                    label="Choose a setting"
                ).classes('flex-grow')

            with ui.row().classes('w-full items-center mb-2'):
                ui.label("Current Location:").classes('w-1/4')
                current_location_label = ui.label(
                    chat_manager.current_location if chat_manager.current_location else "Not set."
                ).classes('flex-grow text-gray-700')

            with ui.row().classes('w-full items-center mb-4'):
                ui.label("Select Character:").classes('w-1/4')
                global character_dropdown
                character_dropdown = ui.select(
                    options=list(ALL_CHARACTERS.keys()),
                    on_change=lambda e: asyncio.create_task(add_character_from_dropdown(e)),
                    label="Choose a character"
                ).classes('flex-grow')

            with ui.column().classes('w-full mb-4'):
                ui.label("Added Characters:").classes('font-semibold mb-2')
                global added_characters_container
                added_characters_container = ui.row().classes('flex-wrap gap-2')
                refresh_added_characters()

            with ui.row().classes('w-full items-center mb-4'):
                auto_switch = ui.switch('Automatic Chat', value=False, on_change=toggle_automatic_chat).classes('mr-2')
                ui.button("Stop", on_click=lambda: chat_manager.stop_automatic_chat()).classes('ml-auto')

            global next_speaker_label
            next_speaker_label = ui.label("Next speaker:").classes('text-sm text-gray-700')
            update_next_speaker_label()

            global next_button
            next_button = ui.button("Next", on_click=lambda: asyncio.create_task(next_character_response()))
            next_button.props('outline')
            next_button.enabled = not chat_manager.automatic_running
            next_button.update()

            global llm_busy_label
            llm_busy_label = ui.label("LLM is busy...").classes('text-red-500')
            llm_busy_label.visible = False

        with ui.card().style('height: 100vh; display: flex; flex-direction: column;'):
            global chat_display
            chat_display = ui.column().style('flex-grow: 1; overflow-y: auto;')
            show_chat_display()

            with ui.row().classes('w-full items-center p-4').style('flex-shrink: 0;'):
                global user_input
                user_input = ui.input(placeholder='Enter your message...').classes('flex-grow')
                ui.button('Send', on_click=lambda: asyncio.create_task(send_user_message())).classes('ml-2')

    session_dropdown.on('change', on_session_select)
    session_dropdown.value = chat_manager.get_session_name()
    session_dropdown.update()

    logger.debug("Main UI page setup complete.")

def start_ui():
    logger.info("Starting UI initialization.")
    default_session = str(uuid.uuid4())
    settings = load_settings()
    init_chat_manager(default_session, settings)

    main_page()

    sessions = chat_manager.db.get_all_sessions()
    if not sessions:
        logger.info("No existing sessions found. Creating default session.")
        chat_manager.db.create_session(default_session, f"Session {default_session}")
        intimate_setting = next((s for s in settings if s['name'] == "Intimate Setting"), None)
        if intimate_setting:
            chat_manager.set_current_setting(
                intimate_setting['name'],
                intimate_setting['description'],
                intimate_setting['start_location']
            )
            settings_dropdown.value = intimate_setting['name']
            settings_dropdown.update()
        else:
            logger.error("'Intimate Setting' not found. Cannot set a default setting.")
        load_session(default_session)
    else:
        first_session = sessions[0]
        logger.info(f"Loading existing session: {first_session['name']} with ID: {first_session['session_id']}")
        load_session(first_session['session_id'])

    global auto_timer
    auto_timer = ui.timer(interval=2.0, callback=lambda: asyncio.create_task(automatic_conversation()), active=False)
    logger.info("UI timer for automatic conversation set up.")

    ui.run(reload=False)
    logger.info("UI is running.")
