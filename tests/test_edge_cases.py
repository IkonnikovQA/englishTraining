"""Additional tests for edge cases and new features."""

import os
import sys
import tempfile
import json
import csv
import pytest
from unittest.mock import MagicMock, patch, mock_open

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lesson_engine import LessonEngine, load_lessons_from_json
from core.ai_controller import OllamaWorker, WhisperWorker


class TestLessonEngineEdgeCases:
    """Test edge cases in LessonEngine."""

    @pytest.fixture
    def engine(self, temp_db):
        mock_ai = MagicMock()
        return LessonEngine(temp_db, mock_ai)

    def test_start_lesson_empty_id(self, engine):
        """Test starting with empty lesson_id."""
        result = engine.start_lesson("")
        assert result is None

    def test_start_lesson_none_id(self, engine):
        """Test starting with None lesson_id."""
        result = engine.start_lesson(None)
        assert result is None

    def test_start_lesson_empty_tree(self, temp_db):
        """Test starting lesson when lesson tree is empty."""
        mock_ai = MagicMock()
        engine = LessonEngine(temp_db, mock_ai)
        engine.lesson_tree = {}
        result = engine.start_lesson("ANY_ID")
        assert result is None

    def test_submit_answer_no_active_lesson(self, engine):
        """Test submitting answer without active lesson."""
        engine.reset()
        result = engine.submit_answer("test answer")
        assert "error" in result
        assert result["error"] == "No active lesson"

    def test_submit_answer_completed_lesson(self, engine):
        """Test submitting answer after lesson is completed."""
        engine.start_lesson("A1_NUMBERS")
        # Complete the lesson (5 questions)
        for _ in range(5):
            engine.submit_answer("answer")
        # Try to submit another answer
        result = engine.submit_answer("too late")
        assert "error" in result
        assert result["error"] == "Lesson already completed"

    def test_evaluate_answer_empty_string(self, engine):
        """Test evaluating empty answer."""
        result = engine._evaluate_answer(["expected"], "")
        assert result is False

    def test_evaluate_answer_whitespace_only(self, engine):
        """Test evaluating whitespace-only answer."""
        result = engine._evaluate_answer(["expected"], "   ")
        assert result is False

    def test_evaluate_answer_single_word_closed(self, engine):
        """Test single word answer to closed question."""
        result = engine._evaluate_answer(["hello world"], "hello")
        assert result is False  # Too short

    def test_evaluate_answer_word_subset(self, engine):
        """Test word-based matching for flexible answers."""
        result = engine._evaluate_answer(["hello world"], "hello world today")
        assert result is True  # Contains all expected words

    def test_evaluate_answer_empty_expected(self, engine):
        """Test with empty expected answers in list."""
        result = engine._evaluate_answer(["", "valid"], "valid")
        assert result is True

    def test_evaluate_answer_open_ended_single_word(self, engine):
        """Test open-ended question with single word."""
        result = engine._evaluate_answer([], "word")
        assert result is False  # Need at least 2 words

    def test_evaluate_answer_open_ended_two_words(self, engine):
        """Test open-ended question with two words."""
        result = engine._evaluate_answer([], "two words")
        assert result is True

    def test_load_lessons_from_json_nonexistent(self):
        """Test loading from non-existent file."""
        with patch("core.lesson_engine._get_lessons_json_path") as mock_path:
            mock_path.return_value = "/nonexistent/path.json"
            result = load_lessons_from_json()
            assert result == {}

    def test_load_lessons_from_json_invalid(self):
        """Test loading from invalid JSON file."""
        with patch("builtins.open", mock_open(read_data="{invalid json")):
            result = load_lessons_from_json()
            assert result == {}


class TestOllamaWorkerConnection:
    """Test OllamaWorker connection checking."""

    def test_check_connection_success(self):
        """Test successful connection check."""
        worker = OllamaWorker("http://localhost:11434", "llama-3-8b-instruct")
        with patch("core.ai_controller.ollama") as mock_ollama:
            mock_ollama.list.return_value = {
                "models": [{"name": "llama-3-8b-instruct:q4_k_m"}]
            }
            success, message = worker.check_connection()
            assert success is True
            assert message == "Connected"

    def test_check_connection_model_not_found(self):
        """Test connection when model is not available."""
        worker = OllamaWorker("http://localhost:11434", "nonexistent-model")
        with patch("core.ai_controller.ollama") as mock_ollama:
            mock_ollama.list.return_value = {"models": [{"name": "other-model"}]}
            success, message = worker.check_connection()
            assert success is True
            assert "not found" in message.lower()

    def test_check_connection_failed(self):
        """Test connection failure."""
        worker = OllamaWorker("http://localhost:11434", "llama-3-8b-instruct")
        with patch("core.ai_controller.ollama") as mock_ollama:
            mock_ollama.list.side_effect = Exception("Connection refused")
            success, message = worker.check_connection()
            assert success is False
            assert "Cannot connect" in message

    def test_check_connection_without_package(self):
        """Test connection check without ollama package."""
        worker = OllamaWorker("http://localhost:11434", "llama-3-8b-instruct")
        with patch("core.ai_controller.OLLAMA_AVAILABLE", False):
            success, message = worker.check_connection()
            assert success is False
            assert "not installed" in message


class TestWhisperWorkerEdgeCases:
    """Test WhisperWorker edge cases."""

    def test_transcribe_file_not_found(self):
        """Test transcription with non-existent file."""
        worker = WhisperWorker()
        result = worker.transcribe("/nonexistent/audio.wav")
        assert "ERROR" in result
        assert "not found" in result.lower()


class TestLessonEngineDBInteraction:
    """Test LessonEngine database interactions."""

    @pytest.fixture
    def engine(self, temp_db):
        mock_db = MagicMock()
        mock_db.get_vocabulary.return_value = []
        mock_db.get_lesson_progress.return_value = []
        mock_ai = MagicMock()
        return LessonEngine(mock_db, mock_ai)

    def test_upsert_word_on_answer(self, engine):
        """Test that words are upserted when answering."""
        engine.start_lesson("A1_GREETINGS")
        engine.submit_answer("hello")
        # Check that upsert_word was called
        assert engine.db.upsert_word.called

    def test_add_activity_on_completion(self, engine):
        """Test that activity is added when lesson completes."""
        engine.start_lesson("A1_NUMBERS")
        for _ in range(5):
            engine.submit_answer("answer")
        # Check that add_activity was called
        assert engine.db.add_activity.called

    def test_save_lesson_result_on_completion(self, engine):
        """Test that lesson result is saved on completion."""
        engine.start_lesson("A1_NUMBERS")
        for _ in range(5):
            engine.submit_answer("answer")
        # Check that save_lesson_result was called
        assert engine.db.save_lesson_result.called

    def test_partial_score_calculation(self, engine):
        """Test score calculation for mixed answers."""
        engine.start_lesson("A1_GREETINGS")
        # First question - correct
        r1 = engine.submit_answer("hello")
        assert r1["score"] == 100
        # Second question - incorrect short answer
        r2 = engine.submit_answer("x")
        assert r2["score"] < 50  # 50 - len("x") * 2 = 48
        # Check total score
        state = engine.get_current_state()
        assert state["score"] == r1["score"] + r2["score"]
