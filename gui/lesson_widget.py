"""Lesson widget — lesson selection, theory display, and answer input."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.logger import setup_logger
from core.lesson_engine import LessonEngine
from core.db_manager import DBManager

logger = setup_logger("LessonWidget")


class LessonWidget(QWidget):
    """Widget for the Lessons tab."""

    def __init__(self, engine: LessonEngine, db: DBManager):
        super().__init__()
        logger.info("Initializing LessonWidget...")
        self.engine = engine
        self.db = db
        self._current_lesson = None

        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(10)

        # Lesson selector
        self.selector_group = QGroupBox("Available Lessons")
        selector_layout = QVBoxLayout()
        self.level_combo = QComboBox()
        self.level_combo.addItems(["A1", "A2", "B1", "B2"])
        self.level_combo.currentTextChanged.connect(self._populate_topics)

        self.topic_combo = QComboBox()
        self.topic_combo.setMinimumWidth(200)

        start_btn = QPushButton("Start Lesson")
        start_btn.clicked.connect(self._start_lesson)
        start_btn.setStyleSheet(
            "QPushButton { padding: 8px 20px; font-size: 14px; background: #4CAF50; color: white; border: none; border-radius: 4px; }"
        )

        selector_layout.addWidget(QLabel("Level:"))
        selector_layout.addWidget(self.level_combo)
        selector_layout.addWidget(QLabel("Topic:"))
        selector_layout.addWidget(self.topic_combo)
        selector_layout.addWidget(start_btn)
        self.selector_group.setLayout(selector_layout)
        self.main_layout.addWidget(self.selector_group)

        # Populate topics for default level
        self._populate_topics("A1")

        # Scrollable lesson area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setMinimumHeight(400)
        self.lesson_content = QWidget()
        self.content_layout = QVBoxLayout(self.lesson_content)
        self.scroll_area.setWidget(self.lesson_content)
        self.main_layout.addWidget(self.scroll_area)

        # Initially show empty state
        self._show_empty_state()

    def _restore_selector(self) -> None:
        """Always show selector when switching to Lessons tab."""
        logger.info("Restoring lesson selector")
        self.engine.reset()
        self.selector_group.setVisible(True)
        self._show_empty_state()

    def _populate_topics(self, level: str) -> None:
        self.topic_combo.clear()
        tree = self.engine.lesson_tree.get(level, {})
        self.topic_combo.addItems(tree.keys())

    def _show_empty_state(self) -> None:
        self.selector_group.setVisible(True)
        self._clear_content()
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel("Select a lesson and click 'Start' to begin learning.")
        label.setFont(QFont("Arial", 14))
        label.setStyleSheet("color: #888;")
        self.content_layout.addWidget(label)

    def _clear_content(self) -> None:
        """Clear all widgets from the content layout."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _start_lesson(self) -> None:
        level = self.level_combo.currentText()
        topic = self.topic_combo.currentText()
        logger.info("Attempting to start lesson: level=%s, topic=%s", level, topic)

        if not topic:
            logger.warning("No topic selected")
            QMessageBox.warning(self, "Warning", "Please select a topic.")
            return

        tree = self.engine.lesson_tree.get(level, {})
        lesson_id = tree.get(topic, {}).get("id")
        if not lesson_id:
            logger.error("Lesson ID not found for topic: %s", topic)
            QMessageBox.warning(self, "Warning", f"Lesson not found for topic: {topic}")
            return

        result = self.engine.start_lesson(lesson_id)
        if not result:
            logger.error("Failed to start lesson: %s", lesson_id)
            QMessageBox.warning(self, "Error", "Failed to start lesson.")
            return

        self._current_lesson = result
        logger.info("Lesson started: %s (%s) - %d questions",
                    lesson_id, topic, result["total"])
        self.selector_group.setVisible(False)
        self._render_lesson(result)

    def _render_lesson(self, state: dict) -> None:
        self._clear_content()
        self.content_layout.setSpacing(12)

        # Header
        header = QLabel(f"{state['level']} — {state['topic']}")
        header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.content_layout.addWidget(header)

        # Theory
        theory_box = QGroupBox("Theory")
        theory_layout = QVBoxLayout()
        theory_text = QTextEdit()
        theory_text.setReadOnly(True)
        theory_text.setMarkdown(state["theory"])
        theory_text.setMaximumHeight(120)
        theory_layout.addWidget(theory_text)
        theory_box.setLayout(theory_layout)
        self.content_layout.addWidget(theory_box)

        # Question area
        self.question_label = QLabel(f"Q1/{state['total']}: {state['question']}")
        self.question_label.setFont(QFont("Arial", 13))
        self.question_label.setWordWrap(True)
        self.content_layout.addWidget(self.question_label)

        # Answer input
        self.answer_input = QLineEdit()
        self.answer_input.setPlaceholderText("Type your answer in English...")
        self.answer_input.returnPressed.connect(self._submit_answer)
        self.answer_input.setStyleSheet(
            "QLineEdit { padding: 8px; font-size: 14px; border: 2px solid #ddd; border-radius: 4px; }"
        )
        self.content_layout.addWidget(self.answer_input)

        # Submit button
        submit_btn = QPushButton("Submit Answer")
        submit_btn.clicked.connect(self._submit_answer)
        submit_btn.setStyleSheet(
            "QPushButton { padding: 8px 20px; font-size: 14px; background: #2196F3; color: white; border: none; border-radius: 4px; }"
        )
        self.content_layout.addWidget(submit_btn)

        # Feedback
        self.feedback_label = QLabel("")
        self.feedback_label.setFont(QFont("Arial", 12))
        self.feedback_label.setWordWrap(True)
        self.content_layout.addWidget(self.feedback_label)

        # Score display
        self.score_label = QLabel(f"Score: 0 / {state['total']}")
        self.score_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.content_layout.addWidget(self.score_label)

        self.answer_input.setFocus()

        # Force update
        self.lesson_content.updateGeometry()
        self.scroll_area.update()

    def _submit_answer(self) -> None:
        if not self.answer_input.isEnabled():
            logger.debug("Answer input disabled, ignoring submit")
            return

        answer = self.answer_input.text().strip()
        if not answer:
            logger.debug("Empty answer, ignoring submit")
            return

        logger.info("User submitted answer: '%s'", answer)

        result = self.engine.submit_answer(answer)
        if "error" in result:
            logger.error("Lesson engine error: %s", result["error"])
            QMessageBox.critical(self, "Error", result["error"])
            return

        if result["completed"]:
            logger.info("Lesson completed! Final score: %.1f/100",
                       result["final_score"])
            self.feedback_label.setText(
                f"🎉 Lesson complete! Final score: {result['final_score']}/100"
            )
            self.feedback_label.setStyleSheet(
                "color: #2196F3; font-weight: bold; font-size: 14px;"
            )
            self.answer_input.setEnabled(False)

            # Restart button
            restart_btn = QPushButton("Start New Lesson")
            restart_btn.clicked.connect(self._show_empty_state)
            restart_btn.setStyleSheet(
                "QPushButton { padding: 8px 20px; font-size: 14px; background: #FF9800; color: white; border: none; border-radius: 4px; }"
            )
            self.content_layout.addWidget(restart_btn)
            return

        # Non-completed: update feedback
        status = "✓" if result["correct"] else "✗"
        logger.info("Answer %s: +%d pts (question %d/%d)",
                   status, result["score"], result.get("next", 0), result["total"])

        if result["correct"]:
            self.feedback_label.setText(f"✓ Correct! (+{result['score']} pts)")
            self.feedback_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.feedback_label.setText(f"✗ Incorrect. (+{result['score']} pts)")
            self.feedback_label.setStyleSheet("color: #f44336; font-weight: bold;")

        self.score_label.setText(
            f"Score: {result.get('next', 0)} / {result['total']}"
        )

        self.answer_input.clear()
        self.question_label.setText(
            f"Q{result['next']}/{result['total']}: {result['question']}"
        )
        self.answer_input.setFocus()
