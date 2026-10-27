"""Shared pytest fixtures."""

import os
import sys
import tempfile
import json
import pytest

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_config():
    """Create a temporary settings.json for testing."""
    config = {
        "ollama": {
            "host": "http://localhost:11434",
            "model": "llama-3-8b-instruct:q4_k_m",
            "temperature": 0.7,
        },
        "whisper": {
            "model_size": "small",
            "compute_type": "int8",
            "device": "cpu",
        },
        "tts": {
            "model": None,
            "voice": "af_heart",
        },
        "prompts": {
            "lesson": "Test lesson prompt",
            "chat": "Test chat prompt",
        },
        "app": {
            "name": "English Trainer Test",
            "version": "0.1.0",
        },
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(config, f)
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database."""
    from core.db_manager import DBManager

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = DBManager(tmp.name)
    yield db
    db.close()
    os.unlink(tmp.name)
