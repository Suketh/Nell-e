import contextlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any


class Worker:
    def __init__(self) -> None:
        self.model: Any | None = None
        self.device = ""

    def load(self, device: str) -> None:
        resolved_device = str(device or "cuda")
        if self.model is not None and self.device == resolved_device:
            return
        with contextlib.redirect_stdout(sys.stderr):
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            self.model = ChatterboxTurboTTS.from_pretrained(device=resolved_device)
        self.device = resolved_device

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = str(request.get("id", ""))
        action = str(request.get("action", ""))
        try:
            self.load(str(request.get("device", "cuda")))
            if action == "preload":
                return {"id": request_id, "ok": True}
            if action != "generate":
                raise ValueError(f"Unsupported action: {action}")
            model = self.model
            if model is None:
                raise RuntimeError("Chatterbox model is not loaded.")
            output_path = Path(str(request["output_path"]))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with contextlib.redirect_stdout(sys.stderr):
                import torchaudio

                wav = model.generate(
                    str(request.get("text", "")),
                    audio_prompt_path=str(request.get("audio_prompt_path", "")),
                )
                torchaudio.save(str(output_path), wav.detach().cpu(), model.sr)
            return {"id": request_id, "ok": True, "sample_rate": int(model.sr)}
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            return {"id": request_id, "ok": False, "error": str(exc)}


def main() -> None:
    worker = Worker()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("Expected a JSON object.")
            response = worker.handle(request)
        except Exception as exc:
            response = {"id": "", "ok": False, "error": str(exc)}
        print(json.dumps(response, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
