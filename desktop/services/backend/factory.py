from typing import Any

from services.backend.client import BackendClient
from services.backend.http_client import HttpBackendClient
from services.backend.local_adapter import LocalBackendAdapter


def create_backend_client(conf: dict[str, Any], llm: Any, memory: Any, stt: Any | None = None, tts: Any | None = None) -> Any:
    backend_conf = conf.get("backend", {})
    mode = str(backend_conf.get("mode", "in_process")).strip().lower()

    if mode == "http":
        return HttpBackendClient(
            base_url=str(backend_conf.get("base_url", "http://127.0.0.1:8011")),
            timeout=float(backend_conf.get("timeout_sec", 120)),
        )

    return BackendClient(LocalBackendAdapter(llm=llm, memory=memory, stt=stt, tts=tts))
