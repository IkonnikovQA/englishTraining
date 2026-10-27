"""setup.py for PyInstaller packaging."""

from PyInstaller.__main__ import run
import os
import sys

if __name__ == "__main__":
    args = [
        'main.py',
        '--name=EnglishTrainer',
        '--onedir',  # Single folder distribution
        '--windowed',  # No console window
        '--add-data',
        f'config{os.path.sep}settings.json;config',
        '--hidden-import', 'PySide6.QtMultimedia',
        '--hidden-import', 'pyqtgraph',
    ]
    run(args)
