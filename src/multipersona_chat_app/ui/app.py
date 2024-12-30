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
from templates import (
    CharacterIntroductionOutput,
    INTRODUCTION_TEMPLATE,
    CHARACTER_INTRODUCTION_SYSTEM_PROMPT_TEMPLATE
)

logger = logging.getLogger(__name__)

llm_client = None
introduction_llm_client = None
chat_manager = None

user_input = None
you_name_input = None
character_dropdown = None
added_characters_container = None
next_speaker_label = None
next_button = None
settings_dropdown = None
setting_description_label = None
session_dropdown = None
chat_display = None
auto_timer = None
current_location_label = None
llm_status_label = None

notification_queue = asyncio.Queue()

def consume_notifications():
    """
    Synchronous function called by ui.timer.
    It checks the queue and displays notifications in the current UI context.
    """
    while not notification_queue.empty():
        message, msg_type = notification_queue.get_nowait()
        ui.notify(message, type=msg_type)

def init_chat_manager(session_id: str, settings: List[Dict]):
    global chat_manager, llm_client, introduction_llm_client
    logger.debug(f"Initializing ChatManager with session_id: {session_id}")
    chat_manager = ChatManager(you_name="You", session_id=session_id, settings=settings)
    try:
        llm_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=Interaction)
        logger.info("LLM Client initialized successfully (structured).")
    except Exception as e:
        logger.error(f"Error initializing LLM Client: {e}")

    try:
        introduction_llm_client = OllamaClient(
            'src/multipersona_chat_app/config/llm_config.yaml',
            output_model=CharacterIntroductionOutput
        )
        logger.info("Introduction LLM Client initialized successfully (structured).")
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
                        on_click=lambda _, name=char_name: asyncio.create_task(remove_character_async(name)),
                    ).classes('ml-2 bg-red-500 text-white')
        logger.info("Added characters refreshed in UI.")
    else:
        logger.error("added_characters_container is not initialized.")

@ui.refreshable
def show_character_details():
    global character_details_display
    if character_details_display is not None:
        character_details_display.clear()
        char_names = chat_manager.get_character_names()
        if not char_names:
            with character_details_display:
                ui.label("No characters added yet.")
        else:
            with character_details_display:
                for c_name in char_names:
                    with ui.card().classes('w-full mb-4 p-4 bg-gray-50'):
                        ui.label(c_name).classes('text-lg font-bold mb-2 text-blue-600')
                        
                        loc = chat_manager.db.get_character_location(chat_manager.session_id, c_name)
                        with ui.row().classes('mb-2'):
                            ui.icon('location_on').classes('text-gray-600 mr-2')
                            ui.label(f"Location: {loc if loc.strip() else '(Unknown location)'}"
                                   ).classes('text-sm text-gray-700')
                        
                        appearance = chat_manager.db.get_character_appearance(chat_manager.session_id, c_name)
                        with ui.row().classes('mb-2'):
                            ui.icon('checkroom').classes('text-gray-600 mr-2')
                            ui.label(f"Appearance: {appearance if appearance.strip() else '(Unknown appearance)'}"
                                   ).classes('text-sm text-gray-700')

                        # Show plan info
                        plan_data = chat_manager.db.get_character_plan(chat_manager.session_id, c_name)
                        if plan_data:
                            with ui.row().classes('mt-2'):
                                ui.icon('flag').classes('text-gray-600 mr-2')
                                ui.label(f"Goal: {plan_data['goal']}")
                            with ui.row().classes('mb-2'):
                                ui.icon('list').classes('text-gray-600 mr-2')
                                ui.label(f"Steps: {plan_data['steps']}")
                        else:
                            with ui.row().classes('mb-2'):
                                ui.label("No plan found (it may be generated soon).")
    else:
        logger.error("character_details_display is not initialized.")

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

    # Default to the first setting in ALL_SETTINGS if available
    if ALL_SETTINGS:
        default_setting = ALL_SETTINGS[0]
        chat_manager.set_current_setting(
            default_setting['name'],
            default_setting['description'],
            default_setting['start_location']
        )
        settings_dropdown.value = default_setting['name']
        settings_dropdown.update()
    else:
        logger.error("No settings found. No default setting applied.")

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
                # If we're deleting the session currently in use, pick another or create new
                remaining_sessions = chat_manager.db.get_all_sessions()
                if remaining_sessions:
                    new_session = remaining_sessions[0]
                    logger.info(f"Loading remaining session: {new_session['name']} with ID: {new_session['session_id']}")
                    load_session(new_session['session_id'])
                else:
                    new_id = str(uuid.uuid4())
                    new_session_name = f"Session {new_id}"
                    chat_manager.db.create_session(new_id, new_session_name)
                    if ALL_SETTINGS:
                        default_setting = ALL_SETTINGS[0]
                        chat_manager.set_current_setting(
                            default_setting['name'],
                            default_setting['description'],
                            default_setting['start_location']
                        )
                        settings_dropdown.value = default_setting['name']
                        settings_dropdown.update()
                    else:
                        logger.error("No settings found. No default setting applied.")

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
        # If we don't find a matching setting, default to the first if any
        if ALL_SETTINGS:
            default_setting = ALL_SETTINGS[0]
            chat_manager.set_current_setting(
                default_setting['name'],
                default_setting['description'],
                default_setting['start_location']
            )
            settings_dropdown.value = default_setting['name']
            settings_dropdown.update()
        else:
            logger.error("No setting found to fall back to.")

    session_chars = chat_manager.db.get_session_characters(session_id)
    for c_name in session_chars:
        if c_name in ALL_CHARACTERS:
            chat_manager.add_character(c_name, ALL_CHARACTERS[c_name])
        else:
            logger.warning(f"Character '{c_name}' found in DB but not in ALL_CHARACTERS.")

    refresh_added_characters()
    show_chat_display.refresh()
    show_character_details.refresh()
    update_next_speaker_label()
    populate_session_dropdown()
    display_current_location()
    logger.info(f"Session loaded: {session_id}")

async def select_setting(event):
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
            setting_description_label.text = setting['description']
            setting_description_label.update()
            display_current_location()
            show_character_details.refresh()
        except Exception as pe:
            logger.error(f"Error while setting current setting: {pe}")
            await notification_queue.put((str(pe), 'error'))
    else:
        logger.warning(f"Selected setting '{chosen_name}' not found.")

async def toggle_automatic_chat(e):
    state = "enabled" if e.value else "disabled"
    logger.info(f"Automatic chat toggled {state}.")
    if e.value:
        if not chat_manager.get_character_names():
            logger.warning("No characters added. Cannot start automatic chat.")
            await notification_queue.put(("No characters added. Cannot start automatic chat.", 'warning'))
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
            show_character_details.refresh()

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
        show_character_details.refresh()

async def generate_character_introduction_message(character_name: str):
    global llm_busy
    llm_busy = True
    llm_status_label.text = f"Generating introduction for {character_name}..."
    llm_status_label.visible = True
    llm_status_label.update()

    try:
        logger.info(f"Building introduction for character: {character_name}")
        await chat_manager.generate_character_introduction_message(character_name)
    except Exception as e:
        logger.error(f"Error generating introduction for {character_name}: {e}", exc_info=True)
        await notification_queue.put((f"Error generating introduction for {character_name}: {e}", 'error'))

    llm_busy = False
    llm_status_label.text = ""
    llm_status_label.visible = False
    llm_status_label.update()

    show_chat_display.refresh()
    show_character_details.refresh()

async def generate_character_message(character_name: str):
    global llm_busy
    logger.info(f"Generating message for character: {character_name}")

    llm_busy = True
    llm_status_label.text = f"Generating next message for {character_name}..."
    llm_status_label.visible = True
    llm_status_label.update()

    # If character hasn't introduced themselves yet, do that first
    char_spoken_before = any(
        m for m in chat_manager.db.get_messages(chat_manager.session_id)
        if m["sender"] == character_name and m["message_type"] == "character"
    )
    if not char_spoken_before:
        await generate_character_introduction_message(character_name)
        llm_busy = False
        llm_status_label.text = ""
        llm_status_label.visible = False
        llm_status_label.update()
        return

    try:
        system_prompt, formatted_prompt = chat_manager.build_prompt_for_character(character_name)

        # Generate an Interaction from LLM (async background)
        interaction = await run.io_bound(
            llm_client.generate,
            prompt=formatted_prompt,
            system=system_prompt,
            use_cache=False
        )

        if not interaction:
            logger.warning(f"No response for {character_name}. Not storing.")
        else:
            # Validate & possibly correct the interaction
            validated = await chat_manager.validate_and_possibly_correct_interaction(
                character_name, system_prompt, formatted_prompt, interaction
            )
            if validated:
                final_interaction = validated
                formatted_message = f"*{final_interaction.action}*\n{final_interaction.dialogue}"
                msg_id = await chat_manager.add_message(
                    character_name,
                    formatted_message,
                    visible=True,
                    message_type="character",
                    affect=final_interaction.affect,
                    purpose=final_interaction.purpose,
                    why_purpose=final_interaction.why_purpose,
                    why_affect=final_interaction.why_affect,
                    why_action=final_interaction.why_action,
                    why_dialogue=final_interaction.why_dialogue,
                    why_new_location=final_interaction.why_new_location,
                    why_new_appearance=final_interaction.why_new_appearance,
                    new_location=final_interaction.new_location.strip() if final_interaction.new_location.strip() else None,
                    new_appearance=final_interaction.new_appearance.strip() if final_interaction.new_appearance.strip() else None
                )
                if final_interaction.new_location.strip():
                    await chat_manager.handle_new_location_for_character(character_name, final_interaction.new_location, msg_id)
                if final_interaction.new_appearance.strip():
                    await chat_manager.handle_new_appearance_for_character(character_name, final_interaction.new_appearance, msg_id)
                logger.debug(f"Valid message stored for {character_name}: {final_interaction.dialogue}")
            else:
                logger.warning(f"Interaction for {character_name} could not be validated or corrected. Not storing.")
    except Exception as e:
        logger.error(f"Error generating message for {character_name}: {e}")
        await notification_queue.put((f"Error generating message for {character_name}: {e}", 'error'))
    finally:
        llm_busy = False
        llm_status_label.text = ""
        llm_status_label.visible = False
        llm_status_label.update()

    show_chat_display.refresh()
    show_character_details.refresh()

async def send_user_message():
    message = user_input.value.strip()
    if not message:
        logger.warning("Attempted to send empty user message. Not allowed.")
        return

    logger.info(f"User sent message: {message}")
    await chat_manager.add_message(
        chat_manager.you_name,
        message,
        visible=True,
        message_type="user"
    )
    show_chat_display.refresh()
    show_character_details.refresh()
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
            refresh_added_characters()
            logger.info(f"Character '{char_name}' added to chat.")
            show_chat_display.refresh()
            show_character_details.refresh()
        else:
            logger.warning(f"Character '{char_name}' is already added.")
    else:
        logger.error(f"Character '{char_name}' not found in ALL_CHARACTERS.")

    update_next_speaker_label()
    character_dropdown.value = None
    character_dropdown.update()

async def remove_character_async(name: str):
    logger.info(f"Removing character: {name}")
    chat_manager.remove_character(name)
    chat_manager.db.remove_character_from_session(chat_manager.session_id, name)
    refresh_added_characters()
    show_chat_display.refresh()
    show_character_details.refresh()
    update_next_speaker_label()

def main_page():
    global user_input, you_name_input, character_dropdown, added_characters_container
    global next_speaker_label, next_button, settings_dropdown, setting_description_label
    global session_dropdown, chat_display
    global current_location_label, llm_status_label
    global ALL_CHARACTERS, ALL_SETTINGS, character_details_display

    logger.debug("Setting up main UI page.")
    ALL_CHARACTERS = get_available_characters("src/multipersona_chat_app/characters")
    ALL_SETTINGS = load_settings()

    with ui.grid(columns=2).style('grid-template-columns: 1fr 2fr; height: 100vh;'):
        with ui.card().style('height: 100vh; overflow-y: auto;'):
            ui.label('Multipersona Chat Application').classes('text-2xl font-bold mb-4')

            with ui.row().classes('w-full items-center mb-4'):
                ui.label("Session:").classes('w-1/4')
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
                ui.label("Setting Description:").classes('w-1/4')
                setting_description_label = ui.label("(Not set)").classes('flex-grow text-gray-700')

            with ui.row().classes('w-full items-center mb-2'):
                ui.label("Session-Level Location:").classes('w-1/4')
                current_location_label = ui.label(
                    chat_manager.current_location if chat_manager.current_location else "Not set."
                ).classes('flex-grow text-gray-700')

            character_details_display = ui.column().classes('mb-4')
            show_character_details()

            with ui.row().classes('w-full items-center mb-4'):
                ui.label("Select Character:").classes('w-1/4')
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

            global llm_status_label
            llm_status_label = ui.label("").classes('text-orange-600')
            llm_status_label.visible = False

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

    global auto_timer
    auto_timer = ui.timer(interval=2.0, callback=lambda: asyncio.create_task(automatic_conversation()), active=False)
    logger.info("UI timer for automatic conversation set up.")

    ui.timer(1.0, consume_notifications, active=True)

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
        if ALL_SETTINGS:
            default_setting = ALL_SETTINGS[0]
            chat_manager.set_current_setting(
                default_setting['name'],
                default_setting['description'],
                default_setting['start_location']
            )
            settings_dropdown.value = default_setting['name']
            settings_dropdown.update()
        else:
            logger.error("No settings found. Cannot set a default setting.")
        load_session(default_session)
    else:
        first_session = sessions[0]
        logger.info(f"Loading existing session: {first_session['name']} with ID: {first_session['session_id']}")
        load_session(first_session['session_id'])

    global auto_timer
    auto_timer = ui.timer(interval=2.0, callback=lambda: asyncio.create_task(automatic_conversation()), active=False)
    logger.info("UI timer for automatic conversation set up.")

    ui.timer(1.0, consume_notifications, active=True)

    ui.run(reload=False)
    logger.info("UI is running.")
