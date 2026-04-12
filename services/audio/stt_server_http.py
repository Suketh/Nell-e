import subprocess
import time
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlparse

import requests


class ServerHttpSTT:
    def __init__(self, conf):
        server_conf = conf.get("server", {})
        self.url = server_conf.get("url", "http://127.0.0.1:8765/transcribe")
        self.timeout = float(server_conf.get("timeout", 45))
        raw_language = conf.get("language") or server_conf.get("language")
        normalized_language = str(raw_language or "").strip().lower()
        self.language = None if normalized_language in {"", "auto"} else normalized_language
        self.api_key = server_conf.get("api_key", "")
        self.provider = server_conf.get("provider", "local_voxtral")
        self.autostart = bool(server_conf.get("autostart", True))
        self.preload_on_init = bool(server_conf.get("preload_on_init", False))
        self.start_timeout = float(server_conf.get("start_timeout", 180))
        self.whisper_model = conf.get("model", "small")
        self.whisper_device = conf.get("device", "cpu")
        self.whisper_compute_type = conf.get("compute_type", "int8")
        self.python_executable = server_conf.get("python_executable", ".voxtral-venv\\Scripts\\python.exe")
        self.script_path = server_conf.get("script_path", "server/stt_server.py")
        self.model_path = server_conf.get("model_path", "models/Voxtral-Mini-4B-Realtime-2602")
        self.device = server_conf.get("device", "auto")
        self.dtype = server_conf.get("dtype", "auto")
        self.fallback_provider = server_conf.get("fallback_provider", "faster_whisper")
        self.fallback_model = server_conf.get("fallback_model", "small")
        self.fallback_device = server_conf.get("fallback_device", "cpu")
        self.fallback_compute_type = server_conf.get("fallback_compute_type", "")
        self.log_path = Path(server_conf.get("log_path", "data/voxtral_server.log"))
        self.host = server_conf.get("host", urlparse(self.url).hostname or "127.0.0.1")
        self.port = int(server_conf.get("port", urlparse(self.url).port or 8765))
        self.health_url = server_conf.get("health_url", f"http://{self.host}:{self.port}/health")
        self._server_process = None
        self._log_handle = None
        self._ready = False
        self._startup_error = ""
        self._status_text = "Listening offline"
        self._last_status = {
            "provider": "",
            "text_length": 0,
            "ok": False,
            "detail": "",
            "timestamp": 0.0,
        }

        if self.autostart and self.preload_on_init:
            self.warmup()

    def transcribe(self, wav_bytes: bytes):
        self._ensure_server()
        headers = {
            "Content-Type": "application/octet-stream",
            "X-Audio-Format": "pcm_s16le",
            "X-Audio-Sample-Rate": "16000",
            "X-Audio-Channels": "1",
            "X-STT-Provider": self.provider,
        }
        if self.language:
            headers["X-STT-Language"] = str(self.language)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            self.url,
            data=wav_bytes,
            headers=headers,
            timeout=self.timeout,
        )
        if not response.ok:
            detail = ""
            try:
                payload = response.json()
                detail = str(payload.get("detail", "") or payload.get("error", "") or "").strip()
            except Exception:
                detail = (response.text or "").strip()
            message = f"STT server error {response.status_code}"
            if detail:
                message += f": {detail}"
            self._last_status = {
                "provider": "",
                "text_length": 0,
                "ok": False,
                "detail": message,
                "timestamp": time.time(),
            }
            raise RuntimeError(message)
        payload = response.json()
        text = str(payload.get("text", "") or "").strip()
        if not text:
            self._last_status = {
                "provider": str(payload.get("provider", "") or ""),
                "text_length": 0,
                "ok": False,
                "detail": "STT server returned an empty transcript.",
                "timestamp": time.time(),
            }
            raise RuntimeError("STT server returned an empty transcript.")
        self._last_status = {
            "provider": str(payload.get("provider", "") or ""),
            "text_length": len(text),
            "ok": True,
            "detail": "",
            "timestamp": time.time(),
        }
        return text

    def warmup(self):
        self._ensure_server()

    def is_ready(self) -> bool:
        if self._ready:
            return True
        self._ready = self._server_ready()
        return self._ready

    def get_status_text(self) -> str:
        if self.is_ready():
            provider = self.provider.replace("_", " ").strip()
            if provider:
                return f"Listening ready ({provider})"
            return "Listening ready"
        if self._startup_error:
            return f"Listening unavailable: {self._startup_error}"
        return self._status_text

    def set_language(self, language: str | None):
        normalized = (language or "").strip().lower()
        if normalized in {"", "auto"}:
            self.language = None
            return
        self.language = normalized or None

    def get_language(self) -> str:
        return str(self.language or "auto").strip().lower()

    def get_debug_status(self) -> dict:
        return dict(self._last_status)

    def close(self):
        if self._server_process and self._server_process.poll() is None:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
        self._server_process = None
        self._ready = False
        if self._log_handle is not None:
            with suppress(Exception):
                self._log_handle.close()
        self._log_handle = None

    def _ensure_server(self):
        if self._server_ready():
            self._ready = True
            self._startup_error = ""
            self._status_text = self.get_status_text()
            return

        if not self.autostart:
            self._ready = False
            self._startup_error = f"STT server is not reachable at {self.url}"
            raise RuntimeError(f"STT server is not reachable at {self.url}")

        if self._server_process and self._server_process.poll() is not None:
            self._server_process = None

        if self._server_process is None:
            python_path = Path(self.python_executable)
            if not python_path.exists():
                raise FileNotFoundError(f"STT server python executable not found: {python_path}")
            script_path = Path(self.script_path)
            if not script_path.exists():
                raise FileNotFoundError(f"STT server script not found: {script_path}")

            command = [
                str(python_path),
                str(script_path),
                "--host",
                self.host,
                "--port",
                str(self.port),
                "--provider",
                self.provider,
            ]
            if self.provider == "faster_whisper":
                command.extend(
                    [
                        "--model",
                        str(self.whisper_model),
                        "--device",
                        str(self.whisper_device),
                    ]
                )
                if self.whisper_compute_type:
                    command.extend(["--compute-type", str(self.whisper_compute_type)])
            if self.provider == "local_voxtral":
                command.extend(
                    [
                        "--voxtral-model-path",
                        str(self.model_path),
                        "--voxtral-device",
                        str(self.device),
                        "--voxtral-dtype",
                        str(self.dtype),
                    ]
                )
                if self.fallback_provider:
                    command.extend(["--fallback-provider", str(self.fallback_provider)])
                if self.fallback_model:
                    command.extend(["--fallback-model", str(self.fallback_model)])
                if self.fallback_device:
                    command.extend(["--fallback-device", str(self.fallback_device)])
                if self.fallback_compute_type:
                    command.extend(["--fallback-compute-type", str(self.fallback_compute_type)])
            if self.language:
                command.extend(["--language", str(self.language)])

            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = self.log_path.open("ab")
            self._status_text = f"Listening warming up ({self.provider.replace('_', ' ')})..."
            self._server_process = subprocess.Popen(
                command,
                stdout=self._log_handle,
                stderr=self._log_handle,
            )

        deadline = time.time() + self.start_timeout
        while time.time() < deadline:
            if self._server_ready():
                self._ready = True
                self._startup_error = ""
                self._status_text = self.get_status_text()
                return
            if self._server_process and self._server_process.poll() is not None:
                self._ready = False
                self._startup_error = "server exited during startup"
                raise RuntimeError("STT server exited during startup.")
            time.sleep(1.0)

        self._ready = False
        self._startup_error = "startup timed out"
        raise RuntimeError("Timed out while waiting for the STT server to become ready.")

    def _server_ready(self) -> bool:
        try:
            response = requests.get(self.health_url, timeout=3)
            return response.status_code == 200
        except Exception:
            return False

    def __del__(self):
        with suppress(Exception):
            self.close()
