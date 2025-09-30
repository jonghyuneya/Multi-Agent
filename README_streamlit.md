# Orchestrator Streamlit App

This Streamlit application provides a web interface for the orchestrator system that processes user questions through various tools (TypoService, IntentClassifier, NaverAPI, Summarizer).

## Features

- 🤖 Chat interface with the orchestrator
- ⏰ Real-time time information display
- 🔧 Tool integration (TypoService, IntentClassifier, NaverAPI, Summarizer)
- 💬 Chat history management
- 🌏 Asia/Seoul timezone support

## How to Run

### Option 1: Using the run script
```bash
python run_streamlit.py
```

### Option 2: Direct Streamlit command
```bash
streamlit run streamlit_app.py
```

### Option 3: With custom port
```bash
streamlit run streamlit_app.py --server.port 8502
```

## Prerequisites

Make sure you have installed all required dependencies:

```bash
pip install -r install.txt
# or manually:
pip install streamlit langchain_openai langgraph pydantic langchain_core langchain_community langsmith pytz
```

## Usage

1. Open your browser and go to `http://localhost:8501`
2. Type your question in the chat input
3. The system will:
   - Fix typos if needed (TypoService)
   - Classify your intent (IntentClassifier)
   - Search for information (NaverAPI)
   - Provide a summary (Summarizer)
4. View the response with sources and timestamps

## Configuration

- The system uses Asia/Seoul timezone for time information
- NaverAPI requires API keys (configure in `key.py`)
- OpenAI API key required for LLM functionality

## Files

- `streamlit_app.py` - Main Streamlit application
- `run_streamlit.py` - Helper script to run the app
- `graphBuilder.py` - Orchestrator graph definition
- `classes.py` - AgentState model
- `tools.py` - Tool definitions
- `orchestrator_system_prompt.json` - System prompt configuration
