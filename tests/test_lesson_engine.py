"""Unit tests for LessonEngine."""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lesson_engine import LessonEngine


class TestLessonEngine(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_ai = MagicMock()
        self.engine = LessonEngine(self.mock_db, self.mock_ai)

    def test_get_available_lessons(self):
        lessons = self.engine.get_available_lessons()
        self.assertGreater(len(lessons), 0)
        # Check structure
        for lesson in lessons:
            self.assertIn("level", lesson)
            self.assertIn("topic", lesson)
            self.assertIn("lesson_id", lesson)
            self.assertIn("theory", lesson)
            self.assertIn("total_questions", lesson)

    def test_start_lesson_valid(self):
        result = self.engine.start_lesson("A1_GREETINGS")
        self.assertIsNotNone(result)
        self.assertEqual(result["level"], "A1")
        self.assertEqual(result["topic"], "Greetings")
        self.assertIn("theory", result)
        self.assertIn("question", result)
        self.assertIn("total", result)

    def test_start_lesson_invalid(self):
        result = self.engine.start_lesson("NONEXISTENT")
        self.assertIsNone(result)

    def test_submit_answer_correct(self):
        self.engine.start_lesson("A1_NUMBERS")
        result = self.engine.submit_answer("seven")
        self.assertTrue(result["correct"])
        self.assertEqual(result["score"], 100)
        self.assertFalse(result["completed"])
        self.assertIn("question", result)

    def test_submit_answer_incorrect(self):
        self.engine.start_lesson("A1_NUMBERS")
        result = self.engine.submit_answer("привет")
        self.assertFalse(result["correct"])
        self.assertGreater(result["score"], 0)

    def test_submit_answer_number_15(self):
        self.engine.start_lesson("A1_NUMBERS")
        # First answer "seven" is correct
        self.engine.submit_answer("seven")
        # Second question is about 15
        result = self.engine.submit_answer("fifteen")
        self.assertTrue(result["correct"])

    def test_submit_answer_wrong_number(self):
        self.engine.start_lesson("A1_NUMBERS")
        result = self.engine.submit_answer("hello")
        self.assertFalse(result["correct"])

    def test_submit_answer_no_lesson(self):
        self.engine.reset()
        result = self.engine.submit_answer("test")
        self.assertIn("error", result)

    def test_lesson_completion(self):
        """Test that completing all questions triggers DB save."""
        self.engine.start_lesson("A1_NUMBERS")
        # A1_NUMBERS has 5 questions
        for i in range(5):
            result = self.engine.submit_answer(f"answer {i}")
        # After 5th answer, should be completed
        self.assertTrue(result["completed"])
        self.assertIn("final_score", result)
        # Verify DB was called
        self.mock_db.save_lesson_result.assert_called_once()
        self.mock_db.add_activity.assert_called_once()

    def test_get_current_state(self):
        self.engine.start_lesson("A1_GREETINGS")
        state = self.engine.get_current_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["lesson_id"], "A1_GREETINGS")
        # Questions are now dicts with 'q' and 'answers'
        self.assertIn("q", state["questions"][0])

    def test_reset(self):
        self.engine.start_lesson("A1_GREETINGS")
        self.engine.reset()
        state = self.engine.get_current_state()
        self.assertIsNone(state)

    def test_evaluate_answer(self):
        """Test answer matching logic."""
        # Exact match
        self.assertTrue(self.engine._evaluate_answer(["hello"], "hello"))
        self.assertTrue(self.engine._evaluate_answer(["hi"], "Hi"))
        # Partial match
        self.assertTrue(self.engine._evaluate_answer(["good morning"], "good morning!"))
        # No match
        self.assertFalse(self.engine._evaluate_answer(["hello"], "привет"))
        self.assertFalse(self.engine._evaluate_answer(["seven"], "hello"))
        # Open-ended (empty answers list)
        self.assertTrue(self.engine._evaluate_answer([], "This is a proper sentence"))
        self.assertFalse(self.engine._evaluate_answer([], "x"))

    def test_lesson_tree_structure(self):
        """Verify all levels and topics are accessible."""
        lessons = self.engine.get_available_lessons()
        levels = {l["level"] for l in lessons}
        self.assertEqual(levels, {"A1", "A2", "B1", "B2"})

        topics_by_level = {}
        for l in lessons:
            topics_by_level.setdefault(l["level"], []).append(l["topic"])

        self.assertIn("Greetings", topics_by_level["A1"])
        self.assertIn("Present Simple", topics_by_level["A2"])
        self.assertIn("Past Simple", topics_by_level["B1"])
        self.assertIn("Conditionals", topics_by_level["B2"])


if __name__ == "__main__":
    unittest.main()
