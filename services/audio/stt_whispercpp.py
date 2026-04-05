import subprocess, tempfile, wave, os

class WhisperCppSTT:
    def __init__(self, conf):
        self.conf = conf
        self.binary = conf.get("binary") or ("main.exe" if os.name == "nt" else "./main")

    def transcribe(self, wav_bytes: bytes):
        with tempfile.TemporaryDirectory() as d:
            wav = os.path.join(d, "in.wav")
            with wave.open(wav, 'wb') as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
                wf.writeframes(wav_bytes)
            out = subprocess.check_output([self.binary, "-f", wav, "-l", self.conf.get("language", "sv")])
        return out.decode("utf-8").strip()
