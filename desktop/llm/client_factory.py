from typing import Any

from llm.ollama_client import OllamaClient
from llm.openai_local_client import OpenAILocalClient


def create_llm_client(conf: dict[str, Any]) -> Any:
    llm_conf = conf.get("llm", {})
    backend = str(llm_conf.get("backend", "")).strip().lower()

    if backend == "local_openai":
        return OpenAILocalClient(
            base_url=str(llm_conf.get("base_url", "http://127.0.0.1:8001/v1")),
            text_model=str(llm_conf.get("model", "")),
            vision_model=str(llm_conf.get("vision_model", "") or llm_conf.get("model", "")),
            api_key=str(llm_conf.get("api_key", "local-token")),
            runtime=conf.get("llm_runtime", {}),
        )

    ollama_conf = conf.get("ollama", {})
    return OllamaClient(
        ollama_conf["host"],
        text_model=ollama_conf["text_model"],
        vision_model=ollama_conf["vision_model"],
        runtime=conf.get("ollama_runtime", {}),
    )
