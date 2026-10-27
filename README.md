# English Trainer — Local AI Language Learning App

Desktop application for learning English with local AI. Fully offline, no paid APIs.

## Requirements

- **Python 3.10+** (install from [python.org](https://www.python.org/downloads/) or via [pyenv](https://github.com/pyenv/pyenv))
- **Ollama** — [ollama.com](https://ollama.com) (run locally, pull `llama-3-8b-instruct`)
- **Hardware**: i5/i9 CPU, 32 GB RAM (Whisper runs on CPU)

## Quick Start

```bash
# 1. Install Python 3.10+
# 2. Install Ollama and pull model:
ollama pull llama-3-8b-instruct

# 3. Create virtual environment:
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate   # Linux/Mac

# 4. Install dependencies:
pip install -r requirements.txt

# 5. Run:
python main.py
```

## Features

- **📚 Lessons** — Structured lessons from A1 to B2 with AI evaluation
- **🎤 Voice Chat** — Push-to-talk conversations with AI roleplay scenarios
- **📊 Progress** — Vocabulary tracking, activity charts, accuracy trends, streak counter

## Logging

All application events are logged to `data/english_trainer.log`:

- Application start/stop
- Lesson starts, answers, completions
- Database operations
- Chat messages and AI responses
- Errors and warnings

Log format:
```
2026-10-06 23:24:23 | INFO     | LessonWidget | _start_lesson:114 | Attempting to start lesson: level=A1, topic=Greetings
```

Logs rotate automatically (5 MB max, 5 backup files).

## Architecture

```
main.py                  # Entry point
core/
├── db_manager.py        # SQLite CRUD & progress tracking
├── ai_controller.py     # Ollama/Whisper/Kokoro wrappers
└── lesson_engine.py     # Lesson tree, evaluation, scoring
gui/
├── main_window.py       # Tab-based main window
├── lesson_widget.py     # Lesson UI
├── voice_chat_widget.py # Voice chat UI
└── progress_widget.py   # Stats & charts
config/settings.json     # Model config & prompts
```

## Configuration

Edit `config/settings.json` to change:
- Ollama host/model/temperature
- Whisper model size & compute type
- TTS voice selection
- System prompts for lessons and chat

## License

MIT
