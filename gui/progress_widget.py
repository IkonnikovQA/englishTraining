"""Progress widget — vocabulary, activity charts, accuracy trends, and streak."""

import csv
import json
import os
from datetime import date, timedelta
from typing import Optional

import pyqtgraph as pg
from core.logger import setup_logger
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.db_manager import DBManager

logger = setup_logger("ProgressWidget")


class ProgressWidget(QWidget):
    """Widget for the Progress & Statistics tab."""

    def __init__(self, db: DBManager):
        super().__init__()
        logger.info("Initializing ProgressWidget...")
        self.db = db

        layout = QVBoxLayout(self)

        # Streak counter (big display)
        streak_group = QGroupBox("🔥 Current Streak")
        streak_layout = QVBoxLayout()
        self.streak_label = QLabel("0 days")
        self.streak_label.setFont(QFont("Arial", 32, QFont.Weight.Bold))
        self.streak_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        streak_layout.addWidget(self.streak_label)
        streak_group.setLayout(streak_layout)
        layout.addWidget(streak_group)

        # Export button
        export_layout = QVBoxLayout()
        self.export_btn = QPushButton("📥 Export Progress to CSV")
        self.export_btn.clicked.connect(self._export_to_csv)
        self.export_json_btn = QPushButton("📥 Export Progress to JSON")
        self.export_json_btn.clicked.connect(self._export_to_json)
        export_layout.addWidget(self.export_btn)
        export_layout.addWidget(self.export_json_btn)
        layout.addLayout(export_layout)

        # Tabs for different views
        tabs = QTabWidget()

        # Activity chart tab
        activity_tab = self._create_activity_tab()
        tabs.addTab(activity_tab, "Activity")

        # Accuracy chart tab
        accuracy_tab = self._create_accuracy_tab()
        tabs.addTab(accuracy_tab, "Accuracy")

        # Vocabulary tab
        vocab_tab = self._create_vocabulary_tab()
        tabs.addTab(vocab_tab, "Vocabulary")

        layout.addWidget(tabs, 1)

        self._refresh_all()

    def _refresh_all(self) -> None:
        self._update_streak()
        self._update_activity_chart()
        self._update_accuracy_chart()
        self._update_vocabulary()

    # ── Streak ───────────────────────────────────────────────────────

    def _update_streak(self) -> None:
        streak = self.db.get_streak()
        self.streak_label.setText(f"{streak} day{'s' if streak != 1 else ''}")
        logger.debug("Streak: %d days", streak)
        if streak >= 7:
            self.streak_label.setStyleSheet("color: #FF9800;")
        elif streak >= 3:
            self.streak_label.setStyleSheet("color: #4CAF50;")
        else:
            self.streak_label.setStyleSheet("color: #888;")

    # ── Activity Chart ───────────────────────────────────────────────

    def _create_activity_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.activity_plot = pg.PlotWidget(title="Minutes Spent Learning (Last 90 Days)")
        self.activity_plot.setLabel("left", "Minutes")
        self.activity_plot.setLabel("bottom", "Date")
        self.activity_plot.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(self.activity_plot)

        return tab

    def _update_activity_chart(self) -> None:
        data = self.db.get_activity_by_date()
        x_vals = []
        x_labels = []
        y_vals = []

        for row in data:
            try:
                d = date.fromisoformat(row["activity_date"])
                x_vals.append(d.toordinal())
                x_labels.append(d)
                y_vals.append(row["total_minutes"])
            except (ValueError, KeyError):
                continue

        if not x_vals:
            self.activity_plot.clear()
            self.activity_plot.setLabel("left", "No activity data yet")
            return

        self.activity_plot.clear()
        self.activity_plot.plot(
            x_vals, y_vals, pen="g", symbol="o", symbolPen="g", symbolSize=6
        )
        # Auto-range
        self.activity_plot.setXRange(x_vals[0], x_vals[-1])

    # ── Accuracy Chart ───────────────────────────────────────────────

    def _create_accuracy_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.accuracy_plot = pg.PlotWidget(title="Accuracy Over Time")
        self.accuracy_plot.setLabel("left", "Correct Answers %")
        self.accuracy_plot.setLabel("bottom", "Date")
        self.accuracy_plot.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(self.accuracy_plot)

        return tab

    def _update_accuracy_chart(self) -> None:
        data = self.db.get_accuracy_over_time()
        x_vals = []
        y_vals = []

        for row in data:
            try:
                d = date.fromisoformat(row["day"])
                total = row["total"]
                passed = row["passed"]
                accuracy = (passed / total * 100) if total > 0 else 0
                x_vals.append(d.toordinal())
                y_vals.append(accuracy)
            except (ValueError, KeyError, ZeroDivisionError):
                continue

        if not x_vals:
            self.accuracy_plot.clear()
            self.accuracy_plot.setLabel("left", "No lesson data yet")
            return

        self.accuracy_plot.clear()
        self.accuracy_plot.plot(
            x_vals, y_vals, pen="b", symbol="o", symbolPen="b", symbolSize=6
        )
        self.accuracy_plot.setXRange(x_vals[0], x_vals[-1])

    # ── Vocabulary ───────────────────────────────────────────────────

    def _create_vocabulary_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Stats
        word_counts = self.db.get_word_count_by_status()
        stats_label = QLabel(
            f"Total words: {sum(word_counts.values())}  |  "
            f"Learning: {word_counts.get('learning', 0)}  |  "
            f"Mastered: {word_counts.get('mastered', 0)}"
        )
        stats_label.setFont(QFont("Arial", 11))
        layout.addWidget(stats_label)

        # Word list
        self.vocab_list = QListWidget()
        self.vocab_list.setWordWrap(False)
        layout.addWidget(self.vocab_list)

        return tab

    def _update_vocabulary(self) -> None:
        words = self.db.get_vocabulary()
        self.vocab_list.clear()

        for w in words:
            status_icon = "📘" if w["status"] == "learning" else "✅"
            item_text = f"{status_icon} {w['word']}"
            if w.get("translation"):
                item_text += f" — {w['translation']}"
            item_text += f"  (✓{w['correct_count']} ✗{w['wrong_count']})"

            item = QListWidgetItem(item_text)
            if w["status"] == "mastered":
                item.setForeground(Qt.GlobalColor.darkGreen)
            self.vocab_list.addItem(item)

    # ── Export ────────────────────────────────────────────────────────

    def _export_to_csv(self) -> None:
        """Export all progress data to CSV file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Progress", "", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)

                # Lesson progress
                writer.writerow(["=== Lesson Progress ==="])
                writer.writerow(["Lesson ID", "Level", "Topic", "Score", "Completed", "Date"])
                lessons = self.db.get_lesson_progress()
                for lesson in lessons:
                    writer.writerow([
                        lesson.get("lesson_id", ""),
                        lesson.get("level", ""),
                        lesson.get("topic", ""),
                        lesson.get("score", ""),
                        "Yes" if lesson.get("completed") else "No",
                        lesson.get("created_at", ""),
                    ])

                # Vocabulary
                writer.writerow([])
                writer.writerow(["=== Vocabulary ==="])
                writer.writerow(["Word", "Translation", "Status", "Correct", "Wrong", "Last Seen"])
                words = self.db.get_vocabulary()
                for word in words:
                    writer.writerow([
                        word.get("word", ""),
                        word.get("translation", ""),
                        word.get("status", ""),
                        word.get("correct_count", 0),
                        word.get("wrong_count", 0),
                        word.get("last_seen", ""),
                    ])

                # Activity log
                writer.writerow([])
                writer.writerow(["=== Activity Log ==="])
                writer.writerow(["Date", "Minutes"])
                activity = self.db.get_activity_by_date()
                for act in activity:
                    writer.writerow([act.get("activity_date", ""), act.get("total_minutes", 0)])

            logger.info("Progress exported to CSV: %s", file_path)
            self._show_export_message(f"Exported to CSV:\n{file_path}")
        except Exception as e:
            logger.error("CSV export failed: %s", e)
            self._show_error(f"Export failed: {e}")

    def _export_to_json(self) -> None:
        """Export all progress data to JSON file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Progress", "", "JSON Files (*.json)"
        )
        if not file_path:
            return

        try:
            data = {
                "export_date": date.today().isoformat(),
                "app": "English Trainer",
                "version": "0.1.0",
                "summary": {
                    "streak": self.db.get_streak(),
                    "total_lessons": len(self.db.get_lesson_progress()),
                    "total_words": len(self.db.get_vocabulary()),
                    "word_counts": self.db.get_word_count_by_status(),
                },
                "lesson_progress": self.db.get_lesson_progress(),
                "vocabulary": self.db.get_vocabulary(),
                "activity_log": self.db.get_activity_by_date(),
            }

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info("Progress exported to JSON: %s", file_path)
            self._show_export_message(f"Exported to JSON:\n{file_path}")
        except Exception as e:
            logger.error("JSON export failed: %s", e)
            self._show_error(f"Export failed: {e}")

    def _show_export_message(self, message: str) -> None:
        """Show success message for export."""
        label = QLabel(message)
        label.setStyleSheet(
            "background: #E8F5E9; color: #2E7D32; padding: 10px; "
            "border-radius: 5px; font-weight: bold;"
        )
        self.layout().insertWidget(0, label)
        self.layout().removeWidget(label)
        self.layout().insertWidget(0, label)
        # Auto-remove after 5 seconds
        label.timer = self.timerEvent if hasattr(self, 'timerEvent') else None
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(5000, label.deleteLater)

    def _show_error(self, message: str) -> None:
        """Show error message."""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Export Error", f"Export failed:\n\n{message}")
