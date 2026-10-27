"""Voice chat widget — push-to-talk, transcription, AI response, and TTS playback."""

import io
import os
import tempfile
import wave
import threading
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.ai_controller import AIController
from core.db_manager import DBManager
from core.logger import setup_logger

logger = setup_logger("VoiceChatWidget")

# Optional PyAudio — may not be installed on all systems
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    logger.warning("PyAudio not available — microphone recording will fall back to text input")


# ── Background threads ──────────────────────────────────────────────


class ChatWorker(QThread):
    """Runs AI chat in background."""

    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, ai: AIController, scenario: str, user_text: str, history: list):
        super().__init__()
        self.ai = ai
        self.scenario = scenario
        self.user_text = user_text
        self.history = history

    def run(self):
        try:
            response = self.ai.chat_roleplay(
                self.scenario, self.user_text, self.history
            )
            self.response_ready.emit(response)
        except Exception as e:
            self.error_occurred.emit(str(e))


class TTSWorker(QThread):
    """Runs TTS synthesis in background."""

    audio_ready = pyqtSignal(bytes)

    def __init__(self, ai: AIController, text: str):
        super().__init__()
        self.ai = ai
        self.text = text

    def run(self):
        try:
            wav_bytes = self.ai.kokoro.synthesize(self.text)
            self.audio_ready.emit(wav_bytes)
        except Exception as e:
            print(f"TTS error: {e}")


class RecordingWorker(QThread):
    """Records audio from microphone and saves as WAV bytes."""

    recording_ready = pyqtSignal(bytes)
    recording_failed = pyqtSignal(str)

    def __init__(self, sample_rate: int = 16000, channels: int = 1, chunk: int = 1024):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk = chunk
        self._is_recording = False

    def run(self):
        if not PYAUDIO_AVAILABLE:
            self.recording_failed.emit("PyAudio not installed")
            return

        try:
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk,
            )
            self._is_recording = True
            frames = []

            while self._is_recording:
                try:
                    data = stream.read(self.chunk, exception_on_overflow=False)
                    frames.append(data)
                except Exception:
                    break

            stream.stop_stream()
            stream.close()
            audio.terminate()

            # Encode as WAV
            wav_bytes = self._encode_wav(frames, self.sample_rate)
            self.recording_ready.emit(wav_bytes)

        except Exception as e:
            logger.error("Recording failed: %s", e)
            self.recording_failed.emit(str(e))

    def stop(self):
        self._is_recording = False

    @staticmethod
    def _encode_wav(frames, sample_rate):
        """Encode raw PCM frames to WAV bytes."""
        buf = io.BytesIO()
        num_samples = len(frames)
        total_samples = num_samples * 2  # 16-bit = 2 bytes
        buf.write(b"RIFF")
        buf.write(struct.pack("<I", 36 + total_samples))
        buf.write(b"WAVE")
        buf.write(b"fmt ")
        buf.write(struct.pack("<I", 16))
        buf.write(struct.pack("<H", 1))  # PCM
        buf.write(struct.pack("<H", 1))  # mono
        buf.write(struct.pack("<I", sample_rate))
        buf.write(struct.pack("<I", sample_rate * 2))
        buf.write(struct.pack("<H", 2))  # block align
        buf.write(struct.pack("<H", 16))  # bits per sample
        buf.write(b"data")
        buf.write(struct.pack("<I", total_samples))
        for frame in frames:
            buf.write(frame)
        return buf.getvalue()


import struct


class VoiceChatWidget(QWidget):
    """Widget for the Voice Chat tab."""

    SCENARIOS = [
        "At a restaurant",
        "At the airport",
        "Shopping",
        "Hotel check-in",
        "Job interview",
        "Free conversation",
    ]

    def __init__(self, ai: AIController, db: DBManager):
        super().__init__()
        self.ai = ai
        self.db = db
        self.chat_history: list[dict] = []
        self._tts_thread: Optional[TTSWorker] = None
        self._chat_thread: Optional[ChatWorker] = None
        self._recording_thread: Optional[RecordingWorker] = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Scenario selector
        scenario_group = QGroupBox("Scenario")
        scenario_layout = QVBoxLayout()
        self.scenario_combo = QComboBox()
        self.scenario_combo.addItems(self.SCENARIOS)
        scenario_layout.addWidget(self.scenario_combo)
        scenario_group.setLayout(scenario_layout)
        layout.addWidget(scenario_group)

        # Chat display
        chat_group = QGroupBox("Chat")
        chat_layout = QVBoxLayout()
        self.chat_list = QListWidget()
        self.chat_list.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.chat_list)
        chat_layout.addWidget(scroll)
        chat_group.setLayout(chat_layout)
        layout.addWidget(chat_group, 1)

        # Controls
        controls = QHBoxLayout()
        self.ptt_button = QPushButton("⬇ HOLD TO TALK ⬇")
        self.ptt_button.setDown(False)
        self.ptt_button.setCheckable(True)
        self.ptt_button.pressed.connect(self._start_recording)
        self.ptt_button.released.connect(self._stop_recording)
        self.ptt_button.setStyleSheet(
            "QPushButton { padding: 12px 30px; font-size: 16px; font-weight: bold; "
            "background: #f44336; color: white; border: none; border-radius: 8px; }"
            "QPushButton:pressed { background: #d32f2f; }"
        )
        controls.addWidget(self.ptt_button)

        self.status_label = QLabel("Press and hold the button to speak")
        self.status_label.setFont(QFont("Arial", 10))
        self.status_label.setStyleSheet("color: #888;")
        controls.addWidget(self.status_label)
        layout.addLayout(controls)

        # Warn if PyAudio not available
        if not PYAUDIO_AVAILABLE:
            self.status_label.setText(
                "Microphone unavailable — install PyAudio for voice input"
            )
            self.status_label.setStyleSheet("color: #FF9800; font-weight: bold;")

    def _start_recording(self) -> None:
        if not PYAUDIO_AVAILABLE:
            self._fallback_to_text_input()
            return

        self.status_label.setText("🔴 Recording... Speak now!")
        self.status_label.setStyleSheet("color: #f44336; font-weight: bold;")
        self.ptt_button.setChecked(True)

        # Start recording in background thread
        self._recording_thread = RecordingWorker()
        self._recording_thread.recording_ready.connect(self._on_recording_complete)
        self._recording_thread.recording_failed.connect(self._on_recording_error)
        self._recording_thread.start()

    def _stop_recording(self) -> None:
        self.status_label.setText("Processing audio...")
        self.ptt_button.setChecked(False)

        if self._recording_thread and self._recording_thread.isRunning():
            self._recording_thread.stop()

    def _on_recording_complete(self, wav_bytes: bytes) -> None:
        """Handle recorded audio and transcribe with Whisper."""
        logger.info("Recording complete, transcribing with Whisper...")
        self.status_label.setText("🔊 Transcribing...")

        # Save to temp file for Whisper
        temp_path = os.path.join(
            tempfile.gettempdir(), "english_trainer_recording.wav"
        )
        with open(temp_path, "wb") as f:
            f.write(wav_bytes)

        try:
            text = self.ai.transcribe_audio(temp_path)
            if text.startswith("[ERROR:"):
                logger.error("Transcription error: %s", text)
                self.status_label.setText("Transcription failed")
                self._fallback_to_text_input()
                return

            if text.strip():
                self._send_message(text.strip())
            else:
                logger.warning("Empty transcription — falling back to text input")
                self.status_label.setText("Could not detect speech")
                self._fallback_to_text_input()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def _on_recording_error(self, error: str) -> None:
        logger.error("Recording error: %s", error)
        self.status_label.setText("Recording failed — using text input")
        self._fallback_to_text_input()

    def _fallback_to_text_input(self) -> None:
        """Fallback to text input when microphone is unavailable."""
        from PyQt6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(
            self, "Voice Chat", "Enter what you said:"
        )
        if ok and text.strip():
            self._send_message(text.strip())

    def _send_message(self, text: str) -> None:
        """Send user message and get AI response."""
        logger.info("User message: '%s'", text)

        # Add user message to chat
        item = QListWidgetItem(f"👤 You: {text}")
        item.setFont(QFont("Arial", 11))
        self.chat_list.addItem(item)
        self.chat_list.scrollToBottom()

        # Save to DB
        scenario = self.scenario_combo.currentText()
        self.db.save_chat_message(scenario, "user", text)
        self.chat_history.append({"role": "user", "text": text})
        logger.debug("Chat message saved to DB: scenario=%s", scenario)

        # Disable button during AI response
        self.ptt_button.setEnabled(False)
        self.status_label.setText("🤖 AI is thinking...")

        # Start AI chat in background
        self._chat_thread = ChatWorker(self.ai, scenario, text, self.chat_history)
        self._chat_thread.response_ready.connect(self._on_ai_response)
        self._chat_thread.error_occurred.connect(self._on_chat_error)
        self._chat_thread.start()

    def _on_ai_response(self, response: str) -> None:
        """Handle AI response and play TTS."""
        logger.info("AI response received (length=%d)", len(response))

        # Clean up possible error markers
        clean_response = response
        if clean_response.startswith("[ERROR:"):
            logger.error("AI error response: %s", clean_response)
            clean_response = "Sorry, I couldn't connect to the AI. Make sure Ollama is running."

        # Add AI message to chat
        item = QListWidgetItem(f"🤖 AI: {clean_response}")
        item.setFont(QFont("Arial", 11))
        self.chat_list.addItem(item)
        self.chat_list.scrollToBottom()

        # Save to DB
        scenario = self.scenario_combo.currentText()
        self.db.save_chat_message(scenario, "ai", clean_response)
        self.chat_history.append({"role": "ai", "text": clean_response})

        # Play TTS in background
        self._tts_thread = TTSWorker(self.ai, clean_response)
        self._tts_thread.audio_ready.connect(self._play_audio)
        self._tts_thread.start()

        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("color: #4CAF50;")
        self.ptt_button.setEnabled(True)

    def _on_chat_error(self, error: str) -> None:
        logger.error("Chat error: %s", error)
        item = QListWidgetItem(f"⚠ Error: {error}")
        item.setFont(QFont("Arial", 11))
        item.setForeground(Qt.GlobalColor.red)
        self.chat_list.addItem(item)
        self.ptt_button.setEnabled(True)
        self.status_label.setText("Error — check Ollama connection")

    def _play_audio(self, wav_bytes: bytes) -> None:
        """Play WAV audio bytes using PySide6's audio support."""
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaContent
            from PyQt6.QtCore import QUrl

            # Save to temp file for playback
            path = tempfile.mktemp(suffix=".wav")
            with open(path, "wb") as f:
                f.write(wav_bytes)

            media = QMediaContent(QUrl.fromLocalFile(path))
            output = QAudioOutput()
            output.setVolume(0.8)
            output.play(media)

            # Cleanup after playback
            def cleanup():
                if os.path.exists(path):
                    os.unlink(path)

            from PyQt6.QtCore import QTimer
            QTimer.singleShot(5000, cleanup)
        except ImportError:
            pass  # QtMultimedia not available, skip audio playback
