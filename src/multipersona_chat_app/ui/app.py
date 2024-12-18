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

CHARACTERS_DIR = "src/multipersona_chat_app/characters"  # Adjust path as needed


def get_yaml_files(directory):
    """Retrieve a list of YAML files from the specified directory."""
    try:
        return [f for f in os.listdir(directory) if f.endswith('.yaml')]
    except FileNotFoundError:
        return []


def main_page():
    global user_input, chat_display, you_name_input, character_dropdown

    with ui.column().classes('w-full max-w-2xl mx-auto'):
        ui.label('Multipersona Chat Application').classes('text-2xl font-bold mb-4')

        # Configure "You" name
        with ui.row().classes('w-full items-center'):
            ui.label("Your name:")
            you_name_input = ui.input(value=chat_manager.you_name)
            ui.button("Set", on_click=lambda: set_you_name(you_name_input.value))

        # Add characters
        with ui.row().classes('w-full items-center'):
            ui.label("Select Character:")
            character_dropdown = ui.select(get_yaml_files(CHARACTERS_DIR), on_change=add_character_from_dropdown)

        # Toggle automatic chat
        with ui.row().classes('w-full items-center'):
            auto_switch = ui.switch('Automatic Chat', value=False, on_change=toggle_automatic_chat)
            ui.button("Stop", on_click=lambda: chat_manager.stop_automatic_chat())

        chat_display = ui.column().classes('space-y-2 p-4 bg-gray-100 rounded')

        with ui.row().classes('w-full items-center'):
            user_input = ui.input(placeholder='Enter your message...').classes('flex-grow')
            ui.button('Send', on_click=lambda: asyncio.create_task(send_user_message())).classes('ml-2')

    # Schedule the background task for automatic conversation
    app.on_startup(lambda: asyncio.create_task(automatic_conversation()))


def toggle_automatic_chat(e):
    if e.value:
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
            chat_manager.add_character(char.name, char)
            chat_manager.add_message("System", f"Character '{char.name}' added.", visible=False)
            update_chat_display()
        except Exception as e:
            chat_manager.add_message("System", f"Failed to add character: {e}", visible=False)


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
        bot_message = interaction.dialogue if interaction else "No response."
    except Exception as e:
        bot_message = f"Error: {str(e)}"

    # Replace placeholder message with final response
    chat_manager.chat_history[-1]["message"] = bot_message
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
        # Include timestamp in UI, not in prompts
        with chat_display:
            ui.chat_message(
                text=f"{message}\n[{timestamp}]",
                name=name,
                sent=(name == chat_manager.you_name)
            )


def start_ui():
    main_page()
    ui.run(reload=False)


if __name__ in {'__main__', '__mp_main__'}:
    start_ui()
