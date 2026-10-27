"""Lesson engine — manages lesson tree, question flow, and AI evaluation."""

import json
import os
from typing import Optional
from core.logger import setup_logger
from core.db_manager import DBManager
from core.ai_controller import AIController

logger = setup_logger("LessonEngine")


def _get_lessons_json_path() -> str:
    """Get path to lessons.json file."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "data", "lessons.json")


def load_lessons_from_json() -> dict:
    """Load lesson tree from JSON file.
    
    Falls back to empty dict if file not found or invalid JSON.
    Non-technical users can edit lessons/data/lessons.json to add/modify lessons.
    """
    json_path = _get_lessons_json_path()
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            lessons = json.load(f)
        logger.info("Lessons loaded from JSON: %d levels", len(lessons))
        return lessons
    except FileNotFoundError:
        logger.warning("Lessons JSON not found at %s, using empty lessons", json_path)
        return {}
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in lessons file: %s", e)
        return {}


class LessonEngine:
    """Manages lesson progression, AI evaluation, and progress tracking."""

    def __init__(self, db: DBManager, ai: AIController):
        self.db = db
        self.ai = ai
        self.lesson_tree = load_lessons_from_json()
        self._current_state: dict = {}

    def get_available_lessons(self) -> list[dict]:
        """Return all available lessons grouped by level."""
        lessons = []
        for level, topics in self.lesson_tree.items():
            for topic_name, topic_data in topics.items():
                lessons.append({
                    "level": level,
                    "topic": topic_name,
                    "lesson_id": topic_data["id"],
                    "theory": topic_data["theory"],
                    "total_questions": len(topic_data["questions"]),
                })
        return lessons

    def start_lesson(self, lesson_id: str) -> Optional[dict]:
        """Start a lesson and return initial state."""
        logger.info("Starting lesson: %s", lesson_id)
        if not lesson_id or not isinstance(lesson_id, str):
            logger.error("Invalid lesson_id: %s", lesson_id)
            return None
        if not self.lesson_tree:
            logger.error("Lesson tree is empty - cannot start lesson")
            return None
        for level, topics in self.lesson_tree.items():
            for topic_name, topic_data in topics.items():
                if topic_data["id"] == lesson_id:
                    questions = topic_data.get("questions", [])
                    if not questions:
                        logger.warning("Lesson %s has no questions", lesson_id)
                        return None
                    self._current_state = {
                        "lesson_id": lesson_id,
                        "level": level,
                        "topic": topic_name,
                        "theory": topic_data.get("theory", ""),
                        "questions": questions,
                        "current_index": 0,
                        "score": 0,
                        "history": [],
                    }
                    logger.info("Lesson initialized: %d questions, level=%s, topic=%s",
                               len(questions), level, topic_name)
                    return {
                        "level": level,
                        "topic": topic_name,
                        "theory": topic_data.get("theory", ""),
                        "question": questions[0].get("q", ""),
                        "total": len(questions),
                    }
        logger.warning("Lesson not found: %s", lesson_id)
        return None

    def submit_answer(self, answer: str) -> dict:
        """Submit an answer and get evaluation + next question."""
        state = self._current_state
        if not state:
            logger.error("No active lesson when submitting answer")
            return {"error": "No active lesson"}

        if state["current_index"] >= len(state["questions"]):
            logger.warning("All questions already answered for lesson %s", state["lesson_id"])
            return {"error": "Lesson already completed"}

        question_data = state["questions"][state["current_index"]]
        question_text = question_data.get("q", "")
        expected_answers = question_data.get("answers", [])
        question_type = question_data.get("type", "standard")
        is_correct = self._evaluate_answer(expected_answers, answer, question_type)
        score = 100 if is_correct else max(0, 50 - len(answer) * 2)

        logger.debug("Answer evaluation: correct=%s, score=%d, expected=%s",
                    is_correct, score, expected_answers[:3])

        # Record word in vocabulary
        words = answer.split()
        for word in words:
            clean = word.strip(".,!?;:\"'()[]")
            if len(clean) > 2:
                self.db.upsert_word(clean, correct=is_correct)

        state["score"] += score
        state["history"].append({
            "question": question_text,
            "answer": answer,
            "correct": is_correct,
            "score": score,
        })

        state["current_index"] += 1
        completed = state["current_index"] >= len(state["questions"])

        result = {
            "correct": is_correct,
            "score": score,
            "total_score": state["score"],
            "completed": completed,
        }

        if completed:
            avg_score = state["score"] / len(state["questions"])
            result["final_score"] = round(avg_score, 1)
            logger.info("Saving lesson result: lesson_id=%s, score=%.1f, completed=True",
                       state["lesson_id"], avg_score)
            self.db.save_lesson_result(
                lesson_id=state["lesson_id"],
                level=state["level"],
                topic=state["topic"],
                score=avg_score,
                completed=True,
            )
            self.db.add_activity(len(state["questions"]))  # ~1 min per question
            result["activity_minutes"] = len(state["questions"])
        else:
            next_data = state["questions"][state["current_index"]]
            result["question"] = next_data["q"]
            result["next"] = state["current_index"] + 1
            result["total"] = len(state["questions"])

        return result

    def _evaluate_answer(
        self, expected_answers: list, user_answer: str, question_type: str = "standard"
    ) -> bool:
        """Check if user answer matches any expected answer (case-insensitive).

        Supports: standard (exact/partial/word match), error-correction (finds error pattern).
        """
        if not user_answer or not user_answer.strip():
            logger.debug("Empty answer submitted")
            return False

        if not expected_answers:
            # Open-ended question — accept any non-trivial answer
            clean = user_answer.strip().lower()
            word_count = len(clean.split())
            is_valid = word_count >= 2
            logger.debug("Open-ended answer: %d words, accepted=%s", word_count, is_valid)
            return is_valid

        clean = user_answer.strip().lower()
        # Remove common punctuation
        clean = clean.strip(".,!?;:\"'()[]")

        for expected in expected_answers:
            exp = expected.strip().lower()
            if not exp:
                continue
            # Exact match
            if clean == exp:
                logger.debug("Answer matched exactly: '%s' == '%s'", clean, exp)
                return True
            # Partial match — user answer contains expected
            if exp in clean and len(clean) >= len(exp) * 0.5:
                logger.debug("Answer matched partially: '%s' contains '%s'", clean, exp)
                return True
            # Word-based matching for flexible answers
            clean_words = set(clean.split())
            exp_words = set(exp.split())
            if exp_words and exp_words.issubset(clean_words):
                logger.debug("Answer matched by words: %s", exp_words)
                return True

        # Error-correction specific: check for common correction patterns
        if question_type == "error-correction":
            # Accept answers that contain common grammar corrections
            correction_patterns = ["doesn't", "don't", "doesn't", "goes", "went",
                                   "didn't", "isn't", "aren't", "wasn't", "weren't",
                                   "correct", "error", "mistake"]
            for pattern in correction_patterns:
                if pattern in clean:
                    logger.debug("Error-correction: detected pattern '%s'", pattern)
                    return True

        logger.debug("Answer not matched: '%s' vs expected %s", clean, expected_answers)
        return False

    def get_current_state(self) -> Optional[dict]:
        return self._current_state.copy() if self._current_state else None

    def reset(self) -> None:
        self._current_state = {}
