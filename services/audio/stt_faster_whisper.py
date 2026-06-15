import os
import tempfile
import wave


class FasterWhisperSTT:
    def __init__(self, conf):
        self.conf = conf
        model_name = conf.get("model", "medium")
        device = conf.get("device", "cpu")
        compute_type = conf.get("compute_type", "int8") if device == "cpu" else conf.get("compute_type", "float16")
        try:
            from faster_whisper import WhisperModel
        except Exception as e:
            raise RuntimeError(
                "Kunde inte ladda faster-whisper. Kontrollera kompatibla versioner av faster-whisper och ctranslate2."
            ) from e
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, wav_bytes: bytes):
        with tempfile.TemporaryDirectory() as d:
            wav_path = os.path.join(d, "in.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(wav_bytes)

            segments, _ = self.model.transcribe(
                wav_path,
                language=self.conf.get("language"),
                vad_filter=bool(self.conf.get("vad", True)),
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text
