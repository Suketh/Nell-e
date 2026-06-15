import argparse
import io
import json
import os
import re
import tempfile
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests


class STTBackend:
    def transcribe(self, pcm_bytes: bytes, language: str | None = None) -> dict:
        raise NotImplementedError

    def transcribe_file(self, file_bytes: bytes, filename: str, _content_type: str | None = None, language: str | None = None) -> dict:
        raise NotImplementedError


class FasterWhisperBackend(STTBackend):
    def __init__(self, model: str = "medium", device: str = "cpu", compute_type: str | None = None):
        from faster_whisper import WhisperModel

        resolved_compute = compute_type or ("int8" if device == "cpu" else "float16")
        self.model = WhisperModel(model, device=device, compute_type=resolved_compute)

    def transcribe(self, pcm_bytes: bytes, language: str | None = None) -> dict:
        with tempfile.TemporaryDirectory() as temp_dir:
            wav_path = os.path.join(temp_dir, "input.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm_bytes)

            segments, _ = self.model.transcribe(
                wav_path,
                language=language,
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return {"text": text}

    def transcribe_file(self, file_bytes: bytes, filename: str, content_type: str | None = None, language: str | None = None) -> dict:
        suffix = os.path.splitext(filename or "")[1] or ".wav"
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = os.path.join(temp_dir, f"input{suffix}")
            with open(audio_path, "wb") as handle:
                handle.write(file_bytes)

            segments, _ = self.model.transcribe(
                audio_path,
                language=language,
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return {"text": text}


class MistralVoxtralBackend(STTBackend):
    def __init__(self, api_key: str, model: str = "voxtral-mini-latest", api_base: str = "https://api.mistral.ai"):
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY is required for the Mistral Voxtral backend.")
        self.api_key = api_key
        self.model = model
        self.url = api_base.rstrip("/") + "/v1/audio/transcriptions"

    def transcribe(self, pcm_bytes: bytes, language: str | None = None) -> dict:
        wav_bytes = self._pcm_to_wav_bytes(pcm_bytes)
        return self.transcribe_file(wav_bytes, "audio.wav", "audio/wav", language=language)

    def transcribe_file(self, file_bytes: bytes, filename: str, content_type: str | None = None, language: str | None = None) -> dict:
        files = {
            "file": (filename or "audio.wav", file_bytes, content_type or "application/octet-stream"),
        }
        data = {"model": self.model}
        if language:
            data["language"] = language

        response = requests.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            data=data,
            files=files,
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "text": str(payload.get("text", "") or "").strip(),
            "provider": "mistral_voxtral",
            "raw": payload,
        }

    @staticmethod
    def _pcm_to_wav_bytes(pcm_bytes: bytes) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_bytes)
        return buffer.getvalue()


class LocalVoxtralBackend(STTBackend):
    def __init__(self, model_path: str, device: str = "auto", dtype: str = "auto", fallback_backend: STTBackend | None = None):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        resolved_device = device
        if device == "auto":
            resolved_device = "cuda" if torch.cuda.is_available() else "cpu"

        if dtype == "auto":
            resolved_dtype = torch.bfloat16 if resolved_device == "cuda" else torch.float32
        else:
            resolved_dtype = getattr(torch, dtype)

        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_path,
            local_files_only=True,
            torch_dtype=resolved_dtype,
        )
        self.model.to(resolved_device)
        self.model.eval()
        self.device = resolved_device
        self.dtype = resolved_dtype
        self.fallback_backend = fallback_backend

    def transcribe(self, pcm_bytes: bytes, language: str | None = None) -> dict:
        import numpy as np

        try:
            audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            inputs = self.processor(audio, return_tensors="pt")
            prepared_inputs = {}
            for key, value in inputs.items():
                if hasattr(value, "to"):
                    tensor = value.to(self.model.device)
                    if getattr(tensor, "dtype", None) is not None and tensor.dtype.is_floating_point:
                        tensor = tensor.to(dtype=self.dtype)
                    prepared_inputs[key] = tensor
                else:
                    prepared_inputs[key] = value
            outputs = self.model.generate(**prepared_inputs)
            text = self.processor.batch_decode(outputs, skip_special_tokens=True)[0].strip()
            if text:
                return {
                    "text": text,
                    "provider": "local_voxtral",
                }
            if self.fallback_backend is not None:
                fallback_result = self.fallback_backend.transcribe(pcm_bytes, language=language)
                fallback_result["provider"] = f"{fallback_result.get('provider', 'faster_whisper')}_after_local_voxtral_empty"
                return fallback_result
            raise RuntimeError("Local Voxtral returned an empty transcript.")
        except Exception:
            if self.fallback_backend is not None:
                fallback_result = self.fallback_backend.transcribe(pcm_bytes, language=language)
                fallback_result["provider"] = f"{fallback_result.get('provider', 'faster_whisper')}_after_local_voxtral_error"
                return fallback_result
            raise

    def transcribe_file(self, file_bytes: bytes, filename: str, content_type: str | None = None, language: str | None = None) -> dict:
        if self.fallback_backend is not None and hasattr(self.fallback_backend, "transcribe_file"):
            fallback_result = self.fallback_backend.transcribe_file(file_bytes, filename, content_type=content_type, language=language)
            fallback_result["provider"] = f"{fallback_result.get('provider', 'faster_whisper')}_via_file_fallback"
            return fallback_result
        raise RuntimeError("Local Voxtral file transcription is not configured.")


class STTRequestHandler(BaseHTTPRequestHandler):
    backend: STTBackend = None
    default_language: str | None = None
    default_provider_name: str = "faster_whisper"
    cors_allow_origin = "*"

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        if self.path != "/transcribe":
            self._send_json(404, {"error": "not_found"})
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            self._send_json(400, {"error": "empty_audio"})
            return

        body = self.rfile.read(content_length)
        language = self._normalize_language(self.headers.get("X-STT-Language") or self.default_language)
        content_type = self.headers.get("Content-Type", "")

        try:
            if content_type.startswith("multipart/form-data"):
                file_bytes, filename, part_content_type = self._parse_multipart_file(body, content_type)
                result = self.backend.transcribe_file(file_bytes, filename, content_type=part_content_type, language=language)
            else:
                result = self.backend.transcribe(body, language=language)
        except Exception as exc:
            self._send_json(500, {"error": "transcription_failed", "detail": str(exc)})
            return

        payload = {
            "text": str(result.get("text", "") or "").strip(),
            "provider": str(result.get("provider", "") or self.default_provider_name),
        }
        if "raw" in result:
            payload["raw"] = result["raw"]
        self._send_json(200, payload)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "provider": self.default_provider_name})
            return
        self._send_json(404, {"error": "not_found"})

    def log_message(self, _format, *_args):
        return

    @staticmethod
    def _normalize_language(language: str | None) -> str | None:
        normalized = str(language or "").strip().lower()
        if normalized in {"", "auto", "detect", "unknown"}:
            return None
        return normalized

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", self.cors_allow_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-STT-Language, X-Audio-Format, X-Audio-Sample-Rate, X-Audio-Channels, X-STT-Provider, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")

    def _parse_multipart_file(self, body: bytes, content_type: str) -> tuple[bytes, str, str | None]:
        boundary_match = re.search(r'boundary="?([^";]+)"?', content_type or "", re.IGNORECASE)
        if not boundary_match:
            raise RuntimeError("multipart request is missing a boundary")
        boundary = boundary_match.group(1).encode("utf-8")
        delimiter = b"--" + boundary

        for chunk in body.split(delimiter):
            part = chunk.strip()
            if not part or part == b"--":
                continue
            if b"\r\n\r\n" not in part:
                continue
            raw_headers, raw_payload = part.split(b"\r\n\r\n", 1)
            payload = raw_payload.rstrip(b"\r\n-")
            header_lines = raw_headers.decode("utf-8", errors="ignore").split("\r\n")
            headers: dict[str, str] = {}
            for line in header_lines:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()

            disposition = headers.get("content-disposition", "")
            if "form-data" not in disposition or 'name="file"' not in disposition:
                continue

            filename_match = re.search(r'filename="([^"]*)"', disposition)
            filename = filename_match.group(1).strip() if filename_match else "audio.bin"
            part_content_type = headers.get("content-type")
            if not payload:
                raise RuntimeError("uploaded audio file is empty")
            return payload, filename or "audio.bin", part_content_type

        raise RuntimeError("multipart request is missing a 'file' field")


def parse_args():
    parser = argparse.ArgumentParser(description="Simple STT server for Nellie.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--provider", choices=["faster_whisper", "mistral_voxtral", "local_voxtral"], default="faster_whisper")
    parser.add_argument("--language", default=None)
    parser.add_argument("--model", default="medium")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default=None)
    parser.add_argument("--mistral-model", default="voxtral-mini-latest")
    parser.add_argument("--mistral-api-base", default="https://api.mistral.ai")
    parser.add_argument("--voxtral-model-path", default="models/Voxtral-Mini-4B-Realtime-2602")
    parser.add_argument("--voxtral-device", default="auto")
    parser.add_argument("--voxtral-dtype", default="auto")
    parser.add_argument("--fallback-provider", choices=["none", "faster_whisper"], default="faster_whisper")
    parser.add_argument("--fallback-model", default="small")
    parser.add_argument("--fallback-device", default="cpu")
    parser.add_argument("--fallback-compute-type", default=None)
    return parser.parse_args()


def build_backend(args):
    if args.provider == "mistral_voxtral":
        return MistralVoxtralBackend(
            api_key=os.environ.get("MISTRAL_API_KEY", ""),
            model=args.mistral_model,
            api_base=args.mistral_api_base,
        )
    if args.provider == "local_voxtral":
        fallback_backend = None
        if args.fallback_provider == "faster_whisper":
            fallback_backend = FasterWhisperBackend(
                model=args.fallback_model,
                device=args.fallback_device,
                compute_type=args.fallback_compute_type,
            )
        return LocalVoxtralBackend(
            model_path=args.voxtral_model_path,
            device=args.voxtral_device,
            dtype=args.voxtral_dtype,
            fallback_backend=fallback_backend,
        )
    return FasterWhisperBackend(
        model=args.model,
        device=args.device,
        compute_type=args.compute_type,
    )


def main():
    args = parse_args()
    backend = build_backend(args)
    STTRequestHandler.backend = backend
    STTRequestHandler.default_language = args.language
    STTRequestHandler.default_provider_name = args.provider
    server = ThreadingHTTPServer((args.host, args.port), STTRequestHandler)
    print(f"[stt-server] listening on http://{args.host}:{args.port}/transcribe using {args.provider}")
    server.serve_forever()


if __name__ == "__main__":
    main()
