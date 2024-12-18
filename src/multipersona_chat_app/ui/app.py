from nicegui import ui
from llm.ollama_client import OllamaClient
from models.interaction import Interaction  # Ensure this imports the Interaction model
import asyncio

# Initialize the LLM client with the configuration file
llm_client = OllamaClient('src/multipersona_chat_app/config/llm_config.yaml', output_model=Interaction)

chat_history = []
user_input = None
chat_display = None

def main_page():
    global user_input, chat_display
    with ui.column().classes('w-full max-w-2xl mx-auto'):
        ui.label('Multipersona Chat Application').classes('text-2xl font-bold mb-4')

        chat_display = ui.column().classes('space-y-2 p-4')  # Initialize the chat display column

        with ui.row().classes('w-full items-center'):
            user_input = ui.input(placeholder='Enter your message...').classes('flex-grow')
            ui.button('Send', on_click=send_message).classes('ml-2')

def update_chat_display():
    """Update the chat display with the current chat history."""
    chat_display.clear()
    for sender, message in chat_history:
        with chat_display:
            ui.chat_message(
                text=message,
                name=sender,
                sent=(sender == 'You')
            )

async def send_message():
    if user_input is None:
        print("Error: user_input is not initialized.")
        return

    user_message = user_input.value
    if not user_message:
        return

    # Add user's message to the chat history and update the UI immediately
    chat_history.append(('You', user_message))
    update_chat_display()
    user_input.value = ''  # Clear the input field
    user_input.update()

    # Indicate that the bot is typing
    chat_history.append(('Bot', '...'))
    update_chat_display()

    try:
        # Send the message to the LLM and get the response asynchronously
        interaction = await asyncio.to_thread(llm_client.generate, prompt=user_message)
        bot_message = interaction.dialogue if interaction else "No response."
    except Exception as e:
        bot_message = f"Error: {str(e)}"

    # Update the bot's message
    chat_history[-1] = ('Bot', bot_message)
    update_chat_display()

def start_ui():
    """Start the NiceGUI app."""
    main_page()
    ui.run(reload=False)

if __name__ in {'__main__', '__mp_main__'}:
    start_ui()
