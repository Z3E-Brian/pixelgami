import io
import wave
import numpy as np
import requests
from loguru import logger
from .asr_interface import ASRInterface


class VoiceRecognition(ASRInterface):
    """Asistente: Whisper en la GPU con whisper-server de whisper.cpp (Vulkan), ver servidor.sh."""

    def __init__(self, url: str = "http://127.0.0.1:12395/inference") -> None:
        self.url = url

    def transcribe_np(self, audio: np.ndarray) -> str:
        audio_integer = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        audio_buffer = io.BytesIO()
        with wave.open(audio_buffer, "wb") as wf:
            wf.setnchannels(self.NUM_CHANNELS)
            wf.setsampwidth(self.SAMPLE_WIDTH)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(audio_integer.tobytes())
        r = requests.post(
            self.url,
            files={"file": ("audio.wav", audio_buffer.getvalue(), "audio/wav")},
            data={"response_format": "json", "temperature": "0.0"},
            timeout=30,
        )
        r.raise_for_status()
        texto = r.json().get("text", "").strip()
        logger.info(f"whisper-server: {texto}")
        return texto
