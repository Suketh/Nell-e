import os
from importlib import import_module


class FW_STT:
    def __init__(
        self,
        model_size: str = "small.en",
        device: str = "auto",
        language: str = "en",
        beam_size: int = 5,
        vad_filter: bool = True,
        hotwords: str = "",
    ):
        dev = "cpu"
        if device == "cuda":
            dev = "cuda"
        elif device == "auto":
            try:
                torch = import_module("torch")
                if torch.cuda.is_available():
                    dev = "cuda"
            except Exception:
                if os.environ.get("CUDA_VISIBLE_DEVICES") not in (None, "", "-1"):
                    dev = "cuda"

        compute_type = "float16" if dev == "cuda" else "int8"
        try:
            whisper_module = import_module("faster_whisper")
            whisper_model_class = getattr(whisper_module, "WhisperModel")
        except Exception as exc:
            raise RuntimeError("faster_whisper is not available in the current Python environment.") from exc

        try:
            self.model = whisper_model_class(model_size, device=dev, compute_type=compute_type)
        except Exception:
            self.model = whisper_model_class(model_size, device="cpu", compute_type="int8")
            dev = "cpu"
            compute_type = "int8"

        self.language = language
        self.device = dev
        self.compute_type = compute_type
        self.beam_size = max(1, int(beam_size))
        self.vad_filter = bool(vad_filter)
        self.hotwords = str(hotwords or "").strip()

    def transcribe_bytes(self, wav_path_or_bytes: str | bytes | bytearray) -> str:
        if isinstance(wav_path_or_bytes, (bytes, bytearray)):
            return ""
        segments, _info = self.model.transcribe(
            wav_path_or_bytes,
            language=self.language,
            vad_filter=self.vad_filter,
            beam_size=self.beam_size,
            condition_on_previous_text=False,
            temperature=0.0,
            hotwords=self.hotwords or None,
        )
        return "".join(seg.text for seg in segments).strip()
