import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
PY311_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
RUNNER_NAME = "run_local.bat"
BACKEND_API_VERSION = 5

if sys.version_info[:2] != (3, 11):
    message = (
        "This project now targets Python 3.11 for local TTS support.\n"
        f"Start it with `{RUNNER_NAME}` or run:\n"
        f"\"{PY311_EXE}\" app.py"
    )
    print(message)
    raise SystemExit(1)

from PySide6.QtWidgets import QApplication
from services.audio.protocols import STTProtocol, TTSProtocol
from services.backend.factory import create_backend_client
from services.backend.stt_client import BackendSTTProxy
from services.backend.tts_client import BackendTTSProxy
from llm.client_factory import create_llm_client
from services.audio.stt_factory import create_stt_service
from services.audio.factory import create_tts_service
from services.config_paths import resolve_config_paths
from services.persona.normalize import normalize_persona
from ui.main_window import MainWindow


def load_config() -> dict[str, Any]:
    conf = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(conf, dict):
        raise RuntimeError(f"Expected a mapping in {CONFIG_PATH}")
    return resolve_config_paths(conf, PROJECT_ROOT)


def project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def configure_audio_output(conf: dict[str, Any]) -> None:
    output_device = conf.get("audio", {}).get("output_device")
    if output_device in (None, ""):
        return

    import sounddevice as sd

    input_device = sd.default.device[0]
    sd.default.device = (input_device, int(output_device))


def load_persona(conf: dict[str, Any]) -> dict[str, Any]:
    persona_path = project_path(conf["paths"]["personality_path"])
    raw = json.loads(persona_path.read_text(encoding="utf-8"))
    return normalize_persona(raw)


def _backend_mode(conf: dict[str, Any]) -> str:
    backend_conf = conf.get("backend", {})
    return str(backend_conf.get("mode", "in_process")).strip().lower()


def _backend_base_url(conf: dict[str, Any]) -> str:
    backend_conf = conf.get("backend", {})
    return str(backend_conf.get("base_url", "http://127.0.0.1:8011")).rstrip("/")


def _backend_health_url(conf: dict[str, Any]) -> str:
    return _backend_base_url(conf) + "/health"


def _http_backend_status(conf: dict[str, Any]) -> tuple[bool, int]:
    try:
        with urlopen(_backend_health_url(conf), timeout=2.0) as response:
            if int(getattr(response, "status", 0)) != 200:
                return False, 0
            payload = json.loads(response.read().decode("utf-8"))
            version = int(payload.get("api_version", 1)) if isinstance(payload, dict) else 1
            return True, version
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False, 0


def _http_backend_is_ready(conf: dict[str, Any]) -> bool:
    ready, version = _http_backend_status(conf)
    return ready and version >= BACKEND_API_VERSION


def _ensure_http_backend(conf: dict[str, Any]) -> subprocess.Popen[str] | None:
    if _backend_mode(conf) != "http":
        return None

    reachable, api_version = _http_backend_status(conf)
    if reachable and api_version >= BACKEND_API_VERSION:
        return None
    if reachable:
        raise RuntimeError(
            "An older Nellie backend is already running. "
            "Close Nellie completely and start it again so the backend can be updated."
        )

    backend_conf = conf.get("backend", {})
    if not bool(backend_conf.get("autostart", False)):
        raise RuntimeError(
            "Backend mode is 'http' but Nellie's backend is not reachable. "
            "Enable backend.autostart or start tools/local_nellie_backend_server.py first."
        )

    launch = str(backend_conf.get("launch", "")).strip()
    if not launch:
        raise RuntimeError(
            "Backend mode is 'http' but backend.launch is empty. "
            "Set backend.launch to a command that starts the local backend server."
        )

    workdir = project_path(str(backend_conf.get("workdir", "."))).resolve()
    creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    process = subprocess.Popen(
        launch,
        cwd=str(workdir),
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        creationflags=creation_flags,
    )

    deadline = time.time() + float(backend_conf.get("startup_wait_sec", 18))
    while time.time() < deadline:
        if _http_backend_is_ready(conf):
            return process
        if process.poll() is not None:
            raise RuntimeError(
                f"Nellie backend exited before becoming ready. Exit code: {process.returncode}"
            )
        time.sleep(0.4)

    raise RuntimeError(
        "Timed out waiting for Nellie's local backend server to answer /health."
    )


def build_services(conf: dict[str, Any], backend: Any | None = None) -> tuple[Any | None, STTProtocol, TTSProtocol]:
    ollama = None if _backend_mode(conf) == "http" else create_llm_client(conf)
    if _backend_mode(conf) == "http" and backend is not None:
        stt = BackendSTTProxy(backend, language=str(conf.get("stt", {}).get("language", "en")))
        tts = BackendTTSProxy(backend)
    else:
        stt = create_stt_service(conf)
        tts = create_tts_service(conf)
    return ollama, stt, tts


def main() -> None:
    conf = load_config()
    configure_audio_output(conf)
    persona = load_persona(conf)
    app = QApplication(sys.argv)
    backend_process = _ensure_http_backend(conf)
    bootstrap_backend = create_backend_client(conf, None, None, None)
    ollama, stt, tts = build_services(conf, backend=bootstrap_backend)
    memory = None

    if _backend_mode(conf) != "http":
        memory_path = project_path(conf["paths"]["db_path"])  # lazy import to avoid sqlite on import
        memory_path.parent.mkdir(parents=True, exist_ok=True)

        from services.memory.sqlite_store import MemoryStore

        memory = MemoryStore(memory_path)
        backend = create_backend_client(conf, ollama, memory, stt, tts)
    else:
        backend = bootstrap_backend
    win = MainWindow(conf=conf, persona=persona, ollama=ollama, stt=stt, tts=tts, memory=memory, backend=backend)
    win.backend_process = backend_process

    if backend_process is not None:
        def _shutdown_backend() -> None:
            if backend_process.poll() is not None:
                return
            try:
                backend_process.terminate()
                backend_process.wait(timeout=4)
            except Exception:
                try:
                    backend_process.kill()
                except Exception:
                    pass

        app.aboutToQuit.connect(_shutdown_backend)

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
