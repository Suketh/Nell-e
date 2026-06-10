from pathlib import Path
from typing import Any


def resolve_config_paths(conf: dict[str, Any], project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    conf["_project_root"] = str(root)

    paths = conf.get("paths", {})
    if isinstance(paths, dict):
        for key, value in paths.items():
            if isinstance(value, str) and value.strip():
                paths[key] = str(_resolve(value, root))

    _resolve_field(conf.get("tts"), "voice_sample", root)
    _resolve_field(conf.get("tts"), "chatterbox_python", root)
    _resolve_field(conf.get("tts"), "chatterbox_worker", root)
    _resolve_field(conf.get("backend"), "workdir", root)
    _resolve_field(conf.get("stt"), "voxtral_self_hosted_workdir", root)
    return conf


def _resolve_field(section: Any, key: str, root: Path) -> None:
    if not isinstance(section, dict):
        return
    value = section.get(key)
    if isinstance(value, str) and value.strip():
        section[key] = str(_resolve(value, root))


def _resolve(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path
