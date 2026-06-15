from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.audio.stt_fw import FW_STT


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _parse_multipart(body: bytes, content_type: str) -> tuple[dict[str, str], tuple[str, bytes] | None]:
    boundary_match = None
    for part in content_type.split(";"):
        token = part.strip()
        if token.startswith("boundary="):
            boundary_match = token.split("=", 1)[1].strip().strip('"')
            break
    if not boundary_match:
        raise ValueError("missing multipart boundary")

    boundary = ("--" + boundary_match).encode("utf-8")
    fields: dict[str, str] = {}
    file_part: tuple[str, bytes] | None = None

    for raw_part in body.split(boundary):
        part = raw_part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].rstrip()
        header_blob, sep, content = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = header_blob.decode("utf-8", errors="replace").split("\r\n")
        disposition = next((line for line in headers if line.lower().startswith("content-disposition:")), "")
        if not disposition:
            continue
        name_match = None
        filename_match = None
        for token in disposition.split(";"):
            piece = token.strip()
            if piece.startswith("name="):
                name_match = piece.split("=", 1)[1].strip().strip('"')
            elif piece.startswith("filename="):
                filename_match = piece.split("=", 1)[1].strip().strip('"')
        if not name_match:
            continue
        payload = content.rstrip(b"\r\n")
        if filename_match:
            file_part = (filename_match or "upload.wav", payload)
        else:
            fields[name_match] = payload.decode("utf-8", errors="replace").strip()
    return fields, file_part


class VoxtralRuntimeServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_class: type[BaseHTTPRequestHandler], stt: FW_STT):
        super().__init__(server_address, handler_class)
        self.stt = stt
        self.workdir = str(Path.cwd())


class VoxtralHandler(BaseHTTPRequestHandler):
    server_version = "VoxtralLocal/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(
            f"{self.client_address[0]} - {self.command} {self.path} - "
            + (format % args),
            flush=True,
        )

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "voxtral-runtime-server",
                    "host": self.server.server_address[0],
                    "port": self.server.server_address[1],
                    "workdir": self.server.workdir,
                },
            )
            return
        if path == "/v1/models":
            self._send_json(
                HTTPStatus.OK,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "voxtral-mini-latest",
                            "object": "model",
                            "owned_by": "local",
                        }
                    ],
                },
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/v1/audio/transcriptions":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "multipart/form-data with file is required"},
            )
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else b""
        try:
            fields, file_field = _parse_multipart(body, content_type)
        except Exception as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid multipart payload: {exc}"})
            return

        if file_field is None:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "missing file"})
            return

        language = str(fields.get("language", "")).strip()
        if language:
            self.server.stt.language = language

        filename, file_bytes = file_field
        suffix = Path(filename or "upload.wav").suffix or ".wav"
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                temp_path = handle.name
                handle.write(file_bytes)

            text = self.server.stt.transcribe_bytes(temp_path)
            self._send_json(HTTPStatus.OK, {"text": text})
        except Exception as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--model-size", default="small.en")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    stt = FW_STT(model_size=args.model_size, device=args.device, language=args.language)
    server = VoxtralRuntimeServer((args.host, args.port), VoxtralHandler, stt)
    print(f"Voxtral runtime server listening on http://{args.host}:{args.port}", flush=True)
    print("Request logging is enabled", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
