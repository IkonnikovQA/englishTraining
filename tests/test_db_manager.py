"""Unit tests for DBManager."""

import os
import unittest
import tempfile
from core.db_manager import DBManager


class TestDBManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = DBManager(self.tmp.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_default_user_created(self):
        self.assertEqual(len(self.db.get_vocabulary()), 0)
        progress = self.db.get_lesson_progress()
        self.assertIsInstance(progress, list)

    def test_save_and_get_lesson_progress(self):
        self.db.save_lesson_result("L1", "A1", "Greetings", 85.0, True)
        rows = self.db.get_lesson_progress()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["score"], 85.0)
        self.assertTrue(rows[0]["completed"])

    def test_accuracy_over_time(self):
        from datetime import date, timedelta
        for i in range(3):
            d = date.today() - timedelta(days=i)
            self.db.save_lesson_result(f"L{i}", "A1", "Test", 80.0 + i * 5, True)
        stats = self.db.get_accuracy_over_time()
        self.assertGreaterEqual(len(stats), 1)

    def test_vocabulary_upsert(self):
        self.db.upsert_word("hello", "привет", True)
        self.db.upsert_word("hello", None, True)
        self.db.upsert_word("hello", None, True)
        self.db.upsert_word("hello", None, True)
        self.db.upsert_word("hello", None, True)
        words = self.db.get_vocabulary()
        self.assertEqual(len(words), 1)
        self.assertEqual(words[0]["status"], "mastered")

    def test_vocabulary_wrong_count(self):
        self.db.upsert_word("world", "мир", False)
        self.db.upsert_word("world", None, True)
        words = self.db.get_vocabulary()
        self.assertEqual(words[0]["correct_count"], 1)
        self.assertEqual(words[0]["wrong_count"], 1)
        self.assertEqual(words[0]["status"], "learning")

    def test_activity_log(self):
        self.db.add_activity(15.0)
        self.db.add_activity(30.0)
        rows = self.db.get_activity_by_date()
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["total_minutes"], 45.0)

    def test_streak_zero(self):
        self.assertEqual(self.db.get_streak(), 0)

    def test_streak_one(self):
        self.db.add_activity(10.0)
        self.assertEqual(self.db.get_streak(), 1)

    def test_chat_messages(self):
        self.db.save_chat_message("shop", "user", "How much is this?")
        self.db.save_chat_message("shop", "ai", "It's 5 dollars.")
        history = self.db.get_chat_history("shop")
        self.assertEqual(len(history), 2)

    def test_word_count_by_status(self):
        self.db.upsert_word("cat", "кот", True)
        self.db.upsert_word("dog", "собака", False)
        counts = self.db.get_word_count_by_status()
        self.assertIn("learning", counts)
        self.assertGreater(counts["learning"], 0)


if __name__ == "__main__":
    unittest.main()
