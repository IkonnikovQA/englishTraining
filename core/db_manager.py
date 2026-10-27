"""Database manager for English Trainer — SQLite CRUD and progress tracking."""

import sqlite3
import json
import os
from datetime import date, datetime, timedelta
from typing import Optional
from core.logger import setup_logger

logger = setup_logger("DBManager")


class DBManager:
    """Singleton-like manager for all SQLite operations."""

    _instance: Optional["DBManager"] = None

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), "..", "data", "lessons.db")
        self.db_path = os.path.abspath(db_path)
        logger.info("Initializing DBManager: %s", self.db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Default user
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO users (name) VALUES (?)", ("Default",))

        # Lesson progress table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lesson_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                lesson_id TEXT NOT NULL,
                level TEXT NOT NULL,
                topic TEXT NOT NULL,
                score REAL,
                completed BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Vocabulary table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                translation TEXT,
                status TEXT DEFAULT 'learning',
                correct_count INTEGER DEFAULT 0,
                wrong_count INTEGER DEFAULT 0,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Activity log table (minutes per day)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                activity_date DATE NOT NULL,
                minutes REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, activity_date)
            )
        """)

        # Chat messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                scenario TEXT,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Lesson Progress ──────────────────────────────────────────────

    def save_lesson_result(
        self,
        lesson_id: str,
        level: str,
        topic: str,
        score: float,
        completed: bool = False,
    ) -> int:
        logger.info("Saving lesson result: lesson=%s, level=%s, score=%.1f, completed=%s",
                    lesson_id, level, score, completed)
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO lesson_progress (user_id, lesson_id, level, topic, score, completed)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (1, lesson_id, level, topic, score, completed),
        )
        conn.commit()
        return cursor.lastrowid

    def get_lesson_progress(self) -> list[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM lesson_progress WHERE user_id = 1 ORDER BY created_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_accuracy_over_time(self) -> list[dict]:
        """Return daily accuracy stats for line chart."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                DATE(created_at) as day,
                COUNT(*) as total,
                SUM(CASE WHEN score >= 70 THEN 1 ELSE 0 END) as passed
            FROM lesson_progress
            WHERE user_id = 1
            GROUP BY DATE(created_at)
            ORDER BY day ASC
            """
        )
        return [dict(row) for row in cursor.fetchall()]

    # ── Vocabulary ───────────────────────────────────────────────────

    def upsert_word(
        self, word: str, translation: Optional[str] = None, correct: bool = True
    ) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, correct_count, wrong_count FROM vocabulary WHERE word = ?",
            (word.lower(),),
        )
        row = cursor.fetchone()
        if row is None:
            init_correct = 1 if correct else 0
            init_wrong = 1 if not correct else 0
            status = "mastered" if init_correct >= 5 and init_wrong == 0 else "learning"
            cursor.execute(
                "INSERT INTO vocabulary (word, translation, status, correct_count, wrong_count) VALUES (?, ?, ?, ?, ?)",
                (word.lower(), translation, status, init_correct, init_wrong),
            )
        else:
            correct_count = row["correct_count"] + (1 if correct else 0)
            wrong_count = row["wrong_count"] + (1 if not correct else 0)
            status = "mastered" if correct_count >= 5 and wrong_count == 0 else "learning"
            cursor.execute(
                """UPDATE vocabulary SET correct_count = ?, wrong_count = ?,
                   status = ?, last_seen = CURRENT_TIMESTAMP WHERE id = ?""",
                (correct_count, wrong_count, status, row["id"]),
            )
        conn.commit()

    def get_vocabulary(self, status: Optional[str] = None) -> list[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        if status:
            cursor.execute(
                "SELECT * FROM vocabulary WHERE status = ? ORDER BY word ASC", (status,)
            )
        else:
            cursor.execute("SELECT * FROM vocabulary ORDER BY word ASC")
        return [dict(row) for row in cursor.fetchall()]

    def get_word_count_by_status(self) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status, COUNT(*) as cnt FROM vocabulary GROUP BY status"
        )
        return {row["status"]: row["cnt"] for row in cursor.fetchall()}

    # ── Activity Log ─────────────────────────────────────────────────

    def add_activity(self, minutes: float) -> None:
        today = date.today().isoformat()
        logger.debug("Adding activity: %s, %d minutes", today, minutes)
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO activity_log (user_id, activity_date, minutes)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, activity_date)
               DO UPDATE SET minutes = minutes + ?""",
            (1, today, minutes, minutes),
        )
        conn.commit()

    def get_activity_by_date(self) -> list[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT activity_date, SUM(minutes) as total_minutes
               FROM activity_log
               WHERE user_id = 1
               GROUP BY activity_date
               ORDER BY activity_date DESC
               LIMIT 90"""
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_activity_by_weekday(self) -> list[dict]:
        """Aggregate minutes by day of week for bar chart."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                CASE CAST(strftime('%w', activity_date) AS INTEGER)
                    WHEN 0 THEN 'Sun' WHEN 1 THEN 'Mon'
                    WHEN 2 THEN 'Tue' WHEN 3 THEN 'Wed'
                    WHEN 4 THEN 'Thu' WHEN 5 THEN 'Fri'
                    WHEN 6 THEN 'Sat'
                END as weekday,
                SUM(minutes) as total_minutes
            FROM activity_log
            WHERE user_id = 1
            GROUP BY strftime('%w', activity_date)
            ORDER BY CAST(strftime('%w', activity_date) AS INTEGER)
            """
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_streak(self) -> int:
        """Count consecutive days of activity ending today (or yesterday)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT activity_date FROM activity_log
               WHERE user_id = 1
               ORDER BY activity_date DESC LIMIT 365"""
        )
        rows = cursor.fetchall()
        if not rows:
            return 0

        dates = {row["activity_date"] for row in rows}
        streak = 0
        today = date.today()
        # Start from today or yesterday
        check = today if today.isoformat() in dates else (today - timedelta(days=1))
        while check.isoformat() in dates:
            streak += 1
            check -= timedelta(days=1)
        return streak

    # ── Chat Messages ────────────────────────────────────────────────

    def save_chat_message(
        self, scenario: Optional[str], role: str, text: str
    ) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO chat_messages (user_id, scenario, role, text)
               VALUES (?, ?, ?, ?)""",
            (1, scenario, role, text),
        )
        conn.commit()

    def get_chat_history(self, scenario: Optional[str] = None) -> list[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        if scenario:
            cursor.execute(
                "SELECT * FROM chat_messages WHERE user_id = 1 AND scenario = ? ORDER BY created_at ASC",
                (scenario,),
            )
        else:
            cursor.execute(
                "SELECT * FROM chat_messages WHERE user_id = 1 ORDER BY created_at DESC LIMIT 50"
            )
        return [dict(row) for row in cursor.fetchall()]
