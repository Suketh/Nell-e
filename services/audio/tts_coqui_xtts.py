import os, tempfile
from contextlib import contextmanager
from pathlib import Path
from io import BytesIO
import wave

import soundfile as sf
import torch
import torchaudio
from TTS.api import TTS as CoquiTTS
from TTS.utils.generic_utils import get_user_data_dir


MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
MODEL_DIRNAME = "tts_models--multilingual--multi-dataset--xtts_v2"


def _coqui_tos_agreed() -> bool:
    if os.environ.get("COQUI_TOS_AGREED") == "1":
        return True
    tos_path = Path(get_user_data_dir("tts")) / MODEL_DIRNAME / "tos_agreed.txt"
    return tos_path.exists()


@contextmanager
def _trusted_torch_load():
    original_torch_load = torch.load

    def patched_torch_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_torch_load(*args, **kwargs)

    torch.load = patched_torch_load
    try:
        yield
    finally:
        torch.load = original_torch_load


@contextmanager
def _patched_torchaudio_load():
    original_torchaudio_load = torchaudio.load

    def safe_torchaudio_load(path, *args, **kwargs):
        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
        audio = torch.from_numpy(data.T.copy())
        return audio, int(sample_rate)

    torchaudio.load = safe_torchaudio_load
    try:
        yield
    finally:
        torchaudio.load = original_torchaudio_load

class TTS:
    """Coqui XTTS v2 wrapper with optional voice cloning.
    Put a 5–10s British female WAV at assets/voices/british_female.wav for best results.
    """
    def __init__(self, language: str = "en", voice_sample: str | None = None):
        self.language = language
        self._temp_voice_sample = None
        if not _coqui_tos_agreed():
            raise RuntimeError(
                "Coqui XTTS requires an accepted CPML license before the model can be downloaded. "
                "Accept the license first or use the pyttsx3 engine."
            )
        with _trusted_torch_load(), _patched_torchaudio_load():
            try:
                self.tts = CoquiTTS(model_name=MODEL_NAME, progress_bar=False, gpu=True)
            except Exception:
                self.tts = CoquiTTS(model_name=MODEL_NAME, progress_bar=False, gpu=False)
        self.voice_sample = self._prepare_voice_sample(voice_sample)
        self.voice_sample_path = voice_sample

    def _prepare_voice_sample(self, voice_sample: str | None):
        if not voice_sample or not os.path.exists(voice_sample):
            return None
        sample_path = Path(voice_sample)
        if sample_path.suffix.lower() == ".wav":
            return str(sample_path)

        data, sample_rate = sf.read(str(sample_path), dtype="float32")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            sf.write(temp_file.name, data, sample_rate)
            self._temp_voice_sample = temp_file.name
        return self._temp_voice_sample

    def speak(self, text: str):
        data, sr = self._synthesize_array(text)
        try:
            import sounddevice as sd
            sd.play(data, sr, blocking=True)
        finally:
            pass

    def warmup(self):
        return None

    def close(self):
        return None

    def set_voice_sample(self, voice_sample: str | None):
        if self._temp_voice_sample and os.path.exists(self._temp_voice_sample):
            try:
                os.remove(self._temp_voice_sample)
            except OSError:
                pass
        self._temp_voice_sample = None
        self.voice_sample_path = voice_sample
        self.voice_sample = self._prepare_voice_sample(voice_sample)

    def synthesize_wav_bytes(self, text: str) -> bytes:
        data, sr = self._synthesize_array(text)
        pcm = (data.clip(-1.0, 1.0) * 32767).astype("int16").tobytes()
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1 if len(data.shape) == 1 else int(data.shape[1]))
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(sr))
            wav_file.writeframes(pcm)
        return buffer.getvalue()

    def _synthesize_array(self, text: str):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        try:
            with _patched_torchaudio_load():
                if self.voice_sample:
                    self.tts.tts_to_file(text=text, file_path=wav_path, speaker_wav=self.voice_sample, language=self.language)
                else:
                    self.tts.tts_to_file(text=text, file_path=wav_path, language=self.language)
            data, sr = sf.read(wav_path, dtype="float32")
            return data, sr
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass

    def __del__(self):
        if self._temp_voice_sample and os.path.exists(self._temp_voice_sample):
            try:
                os.remove(self._temp_voice_sample)
            except OSError:
                pass
