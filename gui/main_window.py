"""Main window with tab-based navigation."""

import json
import os
from core.logger import setup_logger
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QShortcut, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QTabWidget,
    QToolBar,
    QLabel,
    QMainWindow,
    QStatusBar,
    QMessageBox,
)

from core.db_manager import DBManager
from core.ai_controller import AIController
from core.lesson_engine import LessonEngine
from gui.lesson_widget import LessonWidget
from gui.voice_chat_widget import VoiceChatWidget
from gui.progress_widget import ProgressWidget

logger = setup_logger("MainWindow")


class MainWindow(QMainWindow):
    """Main application window with three tabs: Lessons, Voice Chat, Progress."""

    def __init__(self):
        super().__init__()
        logger.info("Initializing MainWindow...")
        self.setWindowTitle("English Trainer")
        self.resize(900, 650)

        # Initialize core components
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "config", "settings.json"
        )
        try:
            self.db = DBManager()
            logger.info("Database initialized: %s", self.db.db_path)

            self.ai = AIController(config_path)
            logger.info("AI Controller initialized")

            self.lesson_engine = LessonEngine(self.db, self.ai)
            logger.info("Lesson Engine initialized with %d lessons",
                        len(self.lesson_engine.get_available_lessons()))
        except FileNotFoundError:
            logger.critical("Settings file not found: %s", config_path)
            self._show_critical_error(
                "Configuration Error",
                f"Settings file not found:\n{config_path}\n\n"
                f"Please ensure 'config/settings.json' exists in the application directory.",
            )
            return
        except Exception as e:
            logger.critical("Failed to initialize core components: %s", e)
            self._show_critical_error(
                "Initialization Error",
                f"Failed to start English Trainer:\n\n{e}\n\n"
                f"Please check the log file at 'data/english_trainer.log' "
                f"for details.",
            )
            return

        # UI setup
        self._setup_toolbar()
        self._setup_tabs()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._check_ai_connection()

    def _setup_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        # Lessons action
        lessons_action = QAction("📚 Lessons", self)
        lessons_action.setToolTip("Lessons")
        lessons_action.triggered.connect(lambda: self.tabs.setCurrentIndex(0))
        toolbar.addAction(lessons_action)

        # Voice Chat action
        chat_action = QAction("🎤 Voice Chat", self)
        chat_action.setToolTip("Voice Chat")
        chat_action.triggered.connect(lambda: self.tabs.setCurrentIndex(1))
        toolbar.addAction(chat_action)

        # Progress action
        progress_action = QAction("📊 Progress", self)
        progress_action.setToolTip("Progress & Statistics")
        progress_action.triggered.connect(lambda: self.tabs.setCurrentIndex(2))
        toolbar.addAction(progress_action)

    def _setup_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.lesson_widget = LessonWidget(self.lesson_engine, self.db)
        self.voice_chat_widget = VoiceChatWidget(self.ai, self.db)
        self.progress_widget = ProgressWidget(self.db)

        self.tabs.addTab(self.lesson_widget, "Lessons")
        self.tabs.addTab(self.voice_chat_widget, "Voice Chat")
        self.tabs.addTab(self.progress_widget, "Progress & Stats")

        # Restore selector when switching to Lessons tab
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _setup_statusbar(self) -> None:
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.streak_label = QLabel("Streak: 0 days")
        self.statusbar.addPermanentWidget(self.streak_label)
        self._update_streak()

    def _setup_shortcuts(self) -> None:
        """Setup keyboard shortcuts for navigation."""
        logger.debug("Setting up keyboard shortcuts")

        # Ctrl+1 - Lessons
        shortcut_lessons = QShortcut(QKeySequence("Ctrl+1"), self)
        shortcut_lessons.activated.connect(lambda: self.tabs.setCurrentIndex(0))

        # Ctrl+2 - Voice Chat
        shortcut_chat = QShortcut(QKeySequence("Ctrl+2"), self)
        shortcut_chat.activated.connect(lambda: self.tabs.setCurrentIndex(1))

        # Ctrl+3 - Progress
        shortcut_progress = QShortcut(QKeySequence("Ctrl+3"), self)
        shortcut_progress.activated.connect(lambda: self.tabs.setCurrentIndex(2))

        logger.info("Keyboard shortcuts configured: Ctrl+1=Lessons, Ctrl+2=Voice Chat, Ctrl+3=Progress")

    def _check_ai_connection(self) -> None:
        """Check AI connections on startup and show warning if needed."""
        try:
            # Check Ollama
            success, message = self.ai.ollama.check_connection()
            if not success:
                logger.warning("Ollama connection issue: %s", message)
                QMessageBox.warning(
                    self,
                    "Ollama Connection Warning",
                    f"Could not connect to Ollama:\n\n{message}\n\n"
                    f"Please ensure Ollama is running at {self.ai.ollama.host}",
                )
            elif message != "Connected":
                logger.info("Ollama status: %s", message)
                QMessageBox.information(
                    self,
                    "Ollama Notice",
                    f"Ollama: {message}",
                )
            else:
                logger.info("Ollama connection verified at startup")
        except Exception as e:
            logger.error("Error checking Ollama connection: %s", e)

    def _on_tab_changed(self, index: int) -> None:
        """Restore lesson selector when switching to Lessons tab."""
        tab_names = ["Lessons", "Voice Chat", "Progress & Stats"]
        logger.info("Tab changed to: %s (index %d)", tab_names[index], index)
        if index == 0:
            self.lesson_widget._restore_selector()

    def _update_streak(self) -> None:
        streak = self.db.get_streak()
        self.streak_label.setText(f"Streak: {streak} day{'s' if streak != 1 else ''}")
        logger.debug("Streak updated: %d days", streak)

    def _show_critical_error(self, title: str, message: str) -> None:
        """Show a critical error dialog and close the application."""
        logger.error("Critical error: %s — %s", title, message)
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        QApplication.instance().quit()

    def closeEvent(self, event):
        """Cleanup on close."""
        logger.info("Application closing...")
        if hasattr(self, "db") and self.db:
            self.db.close()
            logger.info("Database closed")
        event.accept()
