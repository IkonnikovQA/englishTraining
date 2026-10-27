"""Main entry point for English Trainer."""

import sys
from core.logger import setup_logger
from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow

logger = setup_logger("EnglishTrainer.main")


def main():
    logger.info("=" * 60)
    logger.info("English Trainer starting...")
    logger.info("Python: %s", sys.version)

    app = QApplication(sys.argv)
    app.setApplicationName("English Trainer")
    app.setOrganizationName("EnglishTrainer")

    window = MainWindow()
    window.show()

    logger.info("Application launched successfully")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
