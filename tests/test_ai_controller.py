"""Unit tests for AIController (mocked)."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai_controller import OllamaWorker, WhisperWorker, KokoroWorker, AIController


class TestOllamaWorker(unittest.TestCase):
    def test_chat_success(self):
        worker = OllamaWorker("http://localhost:11434", "llama-3-8b-instruct")
        with patch("core.ai_controller.ollama") as mock_ollama:
            mock_ollama.chat.return_value = {
                "message": {"content": "Hello! How can I help you?"}
            }
            result = worker.chat("You are a teacher.", "Hello")
            self.assertEqual(result, "Hello! How can I help you?")
            mock_ollama.chat.assert_called_once()

    def test_chat_error(self):
        worker = OllamaWorker("http://localhost:11434", "llama-3-8b-instruct")
        with patch("core.ai_controller.ollama") as mock_ollama:
            mock_ollama.chat.side_effect = Exception("Connection refused")
            result = worker.chat("System", "User")
            self.assertIn("ERROR", result)

    def test_chat_without_package(self):
        with patch("core.ai_controller.OLLAMA_AVAILABLE", False):
            worker = OllamaWorker("http://localhost:11434", "llama-3-8b-instruct")
            result = worker.chat("System", "User")
            self.assertIn("ollama Python package not installed", result)


class TestWhisperWorker(unittest.TestCase):
    def test_transcribe_success(self):
        worker = WhisperWorker(model_size="small", compute_type="int8")
        mock_segments = [MagicMock(text="Hello world. ")]
        with patch("os.path.exists", return_value=True), \
             patch("core.ai_controller.WhisperModel") as MockWhisper:
            instance = MockWhisper.return_value
            instance.transcribe.return_value = (mock_segments, None)
            result = worker.transcribe("/tmp/test.wav")
            self.assertEqual(result, "Hello world.")
            MockWhisper.assert_called_once_with(
                "small", device="cpu", compute_type="int8"
            )

    def test_transcribe_error(self):
        worker = WhisperWorker()
        with patch("core.ai_controller.WhisperModel") as MockWhisper:
            MockWhisper.return_value.transcribe.side_effect = Exception("File not found")
            result = worker.transcribe("/nonexistent.wav")
            self.assertIn("ERROR", result)

    def test_transcribe_bytes(self):
        worker = WhisperWorker()
        mock_segments = [MagicMock(text="Test transcription")]
        with patch.object(worker, "transcribe") as mock_transcribe:
            mock_transcribe.return_value = "Test transcription"
            result = worker.transcribe_bytes(b"fake audio data")
            self.assertEqual(result, "Test transcription")


class TestKokoroWorker(unittest.TestCase):
    def test_synthesize_error(self):
        worker = KokoroWorker()
        with patch.object(worker, "_get_kokoro") as mock_kokoro:
            mock_kokoro.return_value.generate.side_effect = Exception("Model not found")
            result = worker.synthesize("Hello")
            self.assertEqual(result, b"")

    def test_synthesize_returns_bytes(self):
        worker = KokoroWorker()
        import numpy as np

        mock_audio = np.array([0.1, 0.2, -0.1], dtype=np.float32)
        with patch.object(worker, "_get_kokoro") as mock_kokoro:
            mock_kokoro.return_value.generate.return_value = mock_audio
            result = worker.synthesize("Hello", output_path=None)
            self.assertIsInstance(result, bytes)
            self.assertGreater(len(result), 0)


class TestAIController(unittest.TestCase):
    def test_init(self, config_path=None):
        """Test that AIController initializes with config."""
        import tempfile
        import json

        config = {
            "ollama": {"host": "http://localhost:11434", "model": "test", "temperature": 0.5},
            "whisper": {"model_size": "small", "compute_type": "int8", "device": "cpu"},
            "tts": {"model": None, "voice": "af_heart"},
            "prompts": {"lesson": "Lesson prompt", "chat": "Chat prompt"},
            "app": {"name": "Test", "version": "0.1"},
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(config, f)
            tmp = f.name

        try:
            controller = AIController(tmp)
            self.assertIsNotNone(controller.ollama)
            self.assertIsNotNone(controller.whisper)
            self.assertIsNotNone(controller.kokoro)
            self.assertEqual(controller.prompts["lesson"], "Lesson prompt")
        finally:
            os.unlink(tmp)

    def test_ask_lesson_parse_json(self):
        controller = AIController.__new__(AIController)
        controller.ollama = MagicMock()
        controller.ollama.chat.return_value = '{"score": 85, "feedback": "Good!", "next_question": "Next?"}'
        controller.prompts = {"lesson": "Test"}

        result = controller.ask_lesson("My answer", {"history": [], "theory": "Theory text"})
        self.assertEqual(result["score"], 85)
        self.assertEqual(result["feedback"], "Good!")

    def test_ask_lesson_fallback(self):
        controller = AIController.__new__(AIController)
        controller.ollama = MagicMock()
        controller.ollama.chat.return_value = "This is not JSON, just text response"
        controller.prompts = {"lesson": "Test"}

        result = controller.ask_lesson("My answer", {"history": [], "theory": ""})
        self.assertEqual(result["score"], 50)
        self.assertIn("not JSON", result["feedback"])

    def test_chat_roleplay(self):
        controller = AIController.__new__(AIController)
        controller.ollama = MagicMock()
        controller.ollama.chat.return_value = "That will be $20, sir."
        controller.prompts = {"chat": "You are in a shop."}

        result = controller.chat_roleplay("shop", "How much is this?", [])
        self.assertEqual(result, "That will be $20, sir.")

    def test_transcribe_audio(self):
        controller = AIController.__new__(AIController)
        controller.whisper = MagicMock()
        controller.whisper.transcribe.return_value = "Transcribed text"

        result = controller.transcribe_audio("/tmp/test.wav")
        self.assertEqual(result, "Transcribed text")

    def test_synthesize_speech(self):
        controller = AIController.__new__(AIController)
        controller.kokoro = MagicMock()
        controller.kokoro.synthesize.return_value = b"fake wav bytes"

        result = controller.synthesize_speech("Hello world")
        self.assertEqual(result, b"fake wav bytes")


if __name__ == "__main__":
    unittest.main()
