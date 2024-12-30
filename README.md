# Multi-Persona Chatbot

This repository contains a multi-persona chatbot application built with Python and [NiceGUI](https://nicegui.io). Each character in the chatbot can have its own persona, unique backstory, and plan of action. The application supports customizable prompts, location and appearance tracking, and automated summarization of conversations.

## Features

- **Multiple Characters**: Each character is configured through YAML files and has its own system prompts, dynamic templates, and personal plans.
- **Location & Appearance Tracking**: Characters’ locations and appearances can be updated dynamically based on the conversation.
- **Context-Based Summaries**: Conversations are summarized periodically to keep the session manageable without losing important context.
- **Interactive UI**: Built with NiceGUI for an intuitive interface. Users can add characters, switch settings, send messages, and generate automated responses or introductions.

## How It Works

1. **Session Management**  
   - Each conversation session is stored in a local SQLite database. You can create, load, or delete sessions via the UI.
   - The application saves messages, character data, location changes, and plan updates in a structured way.

2. **Characters and Settings**  
   - Characters are defined in YAML files. A character file includes:
     - Name, appearance, and description.
     - Optional system prompts and dynamic prompt templates to customize behavior.
   - Settings (environments) are also loaded from a YAML file (`settings.yaml`). Each setting describes a location or scenario for the session.

3. **LLM Integration**  
   - Communication and text generation rely on the OllamaClient (a local or remote LLM endpoint).  
   - Calls to the LLM are cached by default for efficiency, and can be bypassed by disabling caching in the prompt call.

4. **Interaction Validation**  
   - Each character’s generated interaction undergoes validation. If it doesn’t align with the prompt requirements or system rules, it can be corrected automatically before being displayed.

5. **Automated Summaries**  
   - After a configurable threshold of messages, the conversation is summarized from each character’s perspective. This summary is stored and older messages become hidden (but not lost).

## Getting Started

1. **Install Dependencies**  
   Install required Python packages (for example, via `pip`):
   
   ```
   pip install -r requirements.txt
   ```

   Make sure [Ollama](https://ollama.com/) is installed and the model referenced in llm_config.yaml is available.

2. **Load or Provide Configuration**  
   - Place your character definition YAML files under `src/multipersona_chat_app/characters`.
   - Place your settings in `src/multipersona_chat_app/config/settings.yaml`.
   - The application also uses `llm_config.yaml` and `chat_manager_config.yaml` in the `config` folder for LLM and ChatManager settings.

3. **Run the Application**  
   - From the project’s root folder, run:
     
     ```
     python -m src.multipersona_chat_app.main
     ```
     
   - This launches the NiceGUI server and opens the chat UI in your browser.

4. **Using the Chat UI**  
   - Create or select a session in the UI.
   - Enter your preferred username.
   - Choose a setting (environment) from the dropdown list.
   - Add characters to the session from the provided YAML definitions.
   - Send messages or enable “Automatic Chat” for characters to interact on their own.
   - The **Next** button prompts the next character to speak if automatic mode is off.

## Notes

- **Database**: All session data is stored in `output/conversations.db`.  
- **Cache**: LLM calls are cached in `output/llm_cache`. Clearing this will force the application to regenerate responses.  
- **Logging**: Logs are saved in `output/app.log`.

## Contributing

1. **Pull Requests**  
   - Fork the repository and create a feature branch.  
   - Submit pull requests with clear descriptions.

2. **Bug Reports**  
   - Report issues by opening a new GitHub issue.  
   - Include steps to reproduce and any relevant logs or stack traces.

We appreciate any feedback and contributions to enhance the chatbot’s features and usability!
