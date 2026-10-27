"""Async AI controller — wraps Ollama, Faster-Whisper, and Kokoro TTS in QThreads."""

import json
import os
import tempfile
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel
from kokoro_onnx import Kokoro
import onnxruntime

# Ollama is optional at import time — user may not have it installed
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

from core.logger import setup_logger

logger = setup_logger("AIController")


class OllamaWorker:
    """Runs Ollama requests in a background thread."""

    def __init__(self, host: str, model: str, temperature: float = 0.7):
        self.host = host
        self.model = model
        self.temperature = temperature

    def chat(self, system_prompt: str, user_message: str) -> str:
        if not OLLAMA_AVAILABLE:
            logger.error("Ollama Python package not installed")
            return "[ERROR: ollama Python package not installed]"
        try:
            logger.debug("Sending request to Ollama: model=%s", self.model)
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                options={"temperature": self.temperature},
            )
            result = response["message"]["content"]
            logger.debug("Ollama response received, length=%d", len(result))
            return result
        except Exception as e:
            logger.error("Ollama chat failed: %s", e)
            return f"[ERROR: {e}]"

    def check_connection(self) -> tuple[bool, str]:
        """Check if Ollama server is reachable. Returns (success, message)."""
        if not OLLAMA_AVAILABLE:
            return False, "Ollama Python package not installed"
        try:
            models = ollama.list()
            available_models = [m.get("name", "") for m in models.get("models", [])]
            logger.info("Ollama connection OK, available models: %s", available_models)
            if self.model not in " ".join(available_models):
                logger.warning("Requested model '%s' not found in Ollama", self.model)
                return True, f"Connected but model '{self.model}' not found. Available: {', '.join(available_models[:3])}"
            return True, "Connected"
        except Exception as e:
            logger.error("Ollama connection check failed: %s", e)
            return False, f"Cannot connect to Ollama at {self.host}: {e}"


class WhisperWorker:
    """Runs Faster-Whisper STT in a background thread."""

    def __init__(self, model_size: str = "small", compute_type: str = "int8"):
        self.model_size = model_size
        self.compute_type = compute_type
        self._model = None
        self._audio_dir = os.path.join(tempfile.gettempdir(), "english_trainer_audio")
        os.makedirs(self._audio_dir, exist_ok=True)

    def _get_model(self):
        if self._model is None:
            logger.info("Loading Whisper model: size=%s, compute_type=%s", self.model_size, self.compute_type)
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type=self.compute_type,
            )
            logger.info("Whisper model loaded successfully")
        return self._model

    def transcribe(self, audio_path: str) -> str:
        if not os.path.exists(audio_path):
            logger.error("Audio file not found: %s", audio_path)
            return "[ERROR: audio file not found]"
        try:
            logger.debug("Transcribing audio: %s", audio_path)
            model = self._get_model()
            segments, _ = model.transcribe(audio_path, beam_size=5)
            text = "".join(seg.text for seg in segments)
            result = text.strip()
            logger.debug("Transcription complete: %d chars", len(result))
            return result
        except Exception as e:
            logger.error("Whisper transcription failed: %s", e)
            return f"[ERROR: {e}]"

    def transcribe_bytes(self, audio_bytes: bytes) -> str:
        """Transcribe raw audio bytes (WAV/MP3)."""
        path = os.path.join(self._audio_dir, "temp_recording.wav")
        with open(path, "wb") as f:
            f.write(audio_bytes)
        try:
            return self.transcribe(path)
        finally:
            if os.path.exists(path):
                os.unlink(path)


class KokoroWorker:
    """Runs Kokoro TTS in a background thread."""

    def __init__(self, model_path: Optional[str] = None, voice: str = "af_heart"):
        self.model_path = model_path
        self.voice = voice
        self._kokoro = None

    def _get_kokoro(self):
        if self._kokoro is None:
            if self.model_path and os.path.exists(self.model_path):
                logger.info("Loading Kokoro TTS from: %s", self.model_path)
                self._kokoro = Kokoro.from_file(self.model_path, self.voice)
            else:
                logger.info("Loading Kokoro TTS from package (voice=%s)", self.voice)
                self._kokoro = Kokoro()
            logger.info("Kokoro TTS loaded successfully")
        return self._kokoro

    def synthesize(self, text: str, output_path: Optional[str] = None) -> bytes:
        """Return WAV bytes. If output_path given, also save to file."""
        try:
            kokoro = self._get_kokoro()
            audio = kokoro.generate(text, voice=self.voice)
            # audio is numpy float32, convert to WAV bytes
            import io
            import struct

            buf = io.BytesIO()
            # Simple WAV header + PCM data
            sample_rate = 24000
            buf.write(b"RIFF")
            buf.write(struct.pack("<I", 36 + len(audio) * 2))
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
            buf.write(struct.pack("<I", len(audio) * 2))
            for sample in audio:
                val = int(np.clip(sample * 32767, -32768, 32767))
                buf.write(struct.pack("<h", val))

            wav_bytes = buf.getvalue()
            buf.close()

            if output_path:
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(wav_bytes)

            return wav_bytes
        except Exception as e:
            print(f"[TTS ERROR: {e}]")
            return b""


class AIController:
    """Facade that manages all AI workers."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "config", "settings.json"
            )
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        ollama_cfg = config["ollama"]
        whisper_cfg = config["whisper"]
        tts_cfg = config["tts"]
        prompts_cfg = config["prompts"]

        self.ollama = OllamaWorker(
            host=ollama_cfg["host"],
            model=ollama_cfg["model"],
            temperature=ollama_cfg.get("temperature", 0.7),
        )
        self.whisper = WhisperWorker(
            model_size=whisper_cfg["model_size"],
            compute_type=whisper_cfg["compute_type"],
        )
        self.kokoro = KokoroWorker(
            model_path=tts_cfg.get("model"),
            voice=tts_cfg.get("voice", "af_heart"),
        )
        self.prompts = prompts_cfg

    def ask_lesson(self, user_answer: str, context: dict) -> dict:
        """Ask Ollama to evaluate an answer and return next question."""
        system = self.prompts["lesson"]
        history = context.get("history", [])
        theory = context.get("theory", "")
        user_msg = (
            f"Теория: {theory}\n"
            f"Предыдущие ответы: {history}\n"
            f"Текущий ответ пользователя: {user_answer}"
        )
        response = self.ollama.chat(system, user_msg)
        # Parse response — expects JSON with score, feedback, next_question
        try:
            result = json.loads(response)
        except json.JSONDecodeError:
            result = {
                "score": 50,
                "feedback": response,
                "next_question": response,
            }
        return result

    def chat_roleplay(self, scenario: str, user_text: str, history: list) -> str:
        """Chat as a roleplay character via Ollama."""
        system = self.prompts["chat"].replace("[Сценарий]", scenario)
        history_str = "\n".join(f"{h['role']}: {h['text']}" for h in history[-6:])
        user_msg = f"Предыстория:\n{history_str}\n\nПользователь: {user_text}"
        return self.ollama.chat(system, user_msg)

    def transcribe_audio(self, audio_path: str) -> str:
        return self.whisper.transcribe(audio_path)

    def synthesize_speech(self, text: str, output_path: Optional[str] = None) -> bytes:
        return self.kokoro.synthesize(text, output_path)
