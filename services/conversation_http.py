import json
import os
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from uuid import uuid4
from pathlib import Path

from services.conversation_service import ConversationResult


class HttpConversationClient:
    def __init__(self, conf: dict, persona_path: str | Path, config_path: str | Path = "config.yaml"):
        backend_conf = ((conf or {}).get("backend", {}) or {}).get("conversation", {}) or {}
        self.url = str(backend_conf.get("url", "http://127.0.0.1:8877")).rstrip("/")
        parsed = urllib.parse.urlparse(self.url)
        self.host = backend_conf.get("host", parsed.hostname or "127.0.0.1")
        self.port = int(backend_conf.get("port", parsed.port or 8877))
        self.autostart = bool(backend_conf.get("autostart", True))
        self.start_timeout = float(backend_conf.get("start_timeout", 120))
        self.python_executable = str(backend_conf.get("python_executable", sys.executable))
        self.script_path = Path(backend_conf.get("script_path", "server/conversation_server.py"))
        self.project_root = Path.cwd().resolve()
        self.persona_path = Path(persona_path).resolve()
        self.config_path = Path(config_path).resolve()
        self.user_id = self._resolve_user_id(conf, backend_conf)
        self.session_id = self._resolve_session_id(backend_conf)
        self._server_process = None

    def reply(self, user_text: str, stream_callback=None) -> ConversationResult:
        payload = self._post_json(
            "/v1/chat/reply",
            {"user_id": self.user_id, "session_id": self.session_id, "user_text": user_text, "text": user_text},
        )
        reply_text = str(payload.get("reply", "") or "")
        if stream_callback and reply_text:
            stream_callback(reply_text)
        return ConversationResult(
            reply=reply_text,
            mood=str(payload.get("mood", "thoughtful") or "thoughtful"),
            context=str(payload.get("context", "") or ""),
            mode=str(payload.get("mode", "direct_reply") or "direct_reply"),
            tool_events=list(payload.get("tool_events", []) or []),
            agent_trace=list(payload.get("agent_trace", []) or []),
            gallery_image_path=str(payload.get("gallery_image_path", "") or "") or None,
            gallery_image_caption=str(payload.get("gallery_image_caption", "") or "") or None,
            new_unlock=payload.get("new_unlock") or None,
        )

    def get_affection_state(self) -> dict:
        return self.get_progress_state()

    def get_progress_state(self) -> dict:
        return self._get_json(self._with_user("/v1/progress"))

    def get_unlocked_gallery(self) -> list[dict]:
        payload = self._get_json(self._with_user("/v1/gallery/unlocked"))
        return list(payload.get("items", []) or [])

    def get_gallery_catalog(self) -> list[dict]:
        payload = self._get_json(self._with_user("/v1/gallery/catalog"))
        return list(payload.get("items", []) or [])

    def get_turn_log(self, limit: int = 250) -> str:
        query = urllib.parse.urlencode({"limit": max(1, int(limit)), "user_id": self.user_id})
        payload = self._get_json(f"/v1/log?{query}")
        return str(payload.get("log", "") or "")

    def clear_all(self):
        self._post_json("/v1/memory/clear", {"user_id": self.user_id, "session_id": self.session_id})

    def close(self):
        if self._server_process and self._server_process.poll() is None:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
        self._server_process = None

    def _get_json(self, path: str) -> dict:
        self._ensure_server()
        with urllib.request.urlopen(f"{self.url}{path}", timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict) -> dict:
        self._ensure_server()
        request = urllib.request.Request(
            f"{self.url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))

    def _ensure_server(self):
        if self._server_ready():
            return
        if not self.autostart:
            raise RuntimeError(f"Conversation backend is not reachable at {self.url}")
        if self._server_process and self._server_process.poll() is not None:
            self._server_process = None
        if self._server_process is None:
            command = [
                self.python_executable,
                str(self.script_path),
                "--config",
                str(self.config_path),
                "--persona",
                str(self.persona_path),
                "--host",
                str(self.host),
                "--port",
                str(self.port),
            ]
            self._server_process = subprocess.Popen(
                command,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        deadline = time.time() + self.start_timeout
        while time.time() < deadline:
            if self._server_ready():
                return
            if self._server_process and self._server_process.poll() is not None:
                stdout, stderr = self._server_process.communicate(timeout=1)
                detail = (stderr or stdout or "").strip()
                if detail:
                    raise RuntimeError(f"Conversation backend exited during startup: {detail}")
                raise RuntimeError("Conversation backend exited during startup.")
            time.sleep(1.0)
        raise RuntimeError("Timed out while waiting for the conversation backend to become ready.")

    def _server_ready(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/health?user_id={urllib.parse.quote(self.user_id)}", timeout=3) as response:
                return response.status == 200
        except Exception:
            return False

    def _with_user(self, path: str) -> str:
        separator = "&" if "?" in path else "?"
        return f"{path}{separator}user_id={urllib.parse.quote(self.user_id)}"

    def _resolve_user_id(self, conf: dict, backend_conf: dict) -> str:
        explicit = str(backend_conf.get("user_id", "") or "").strip()
        if explicit:
            return explicit
        profile = str(((conf or {}).get("profile", {}) or {}).get("user_id", "") or "").strip()
        if profile:
            return profile
        username = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
        host = socket.gethostname() or "device"
        return f"{username.lower()}@{host.lower()}"

    def _resolve_session_id(self, backend_conf: dict) -> str:
        explicit = str(backend_conf.get("session_id", "") or "").strip()
        if explicit:
            return explicit
        host = socket.gethostname() or "device"
        return f"desktop-{host.lower()}-{uuid4().hex[:8]}"
