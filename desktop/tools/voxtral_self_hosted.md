# Voxtral Self-Hosted for Nellie

This document describes the recommended future architecture for `XTTS + self-hosted Voxtral`.

## Goal

- Keep `XTTS v2` as Nellie's voice output.
- Run `Voxtral Mini Transcribe` as a separate self-hosted speech-to-text service.
- Let Nellie call that service over:

```text
http://127.0.0.1:8000/v1/audio/transcriptions
```

## Recommended target

Use a small Voxtral transcription model first:

- `voxtral-mini-latest`
- or a dedicated `Voxtral Mini Transcribe` variant if your serving stack exposes it

The point is to start with transcription only, not full audio chat.

## Recommended deployment shape

For this project, the most realistic upgrade path is:

1. `XTTS v2` stays local inside the desktop app.
2. `Voxtral` runs as a separate local self-hosted transcription service.
3. Nellie connects to it over an OpenAI-compatible transcription endpoint.

The recommended hosting direction is:

- `WSL2` on Windows
- `vLLM` or another OpenAI-compatible serving layer
- local endpoint on `127.0.0.1:8000`

Why this shape:

- It keeps Nellie itself simple.
- It avoids pushing more model-serving complexity into the desktop process.
- It keeps the upgrade path clean: `Whisper now`, `Voxtral later`.

## Expected serving shape

Nellie currently expects an OpenAI-compatible transcription endpoint:

```text
POST /v1/audio/transcriptions
```

with a multipart file upload containing a WAV file.

That means your self-hosted server should accept:

- `file`
- `model`
- optional `language`

and return a JSON body containing one of:

- `text`
- `transcript`

## Nellie config

In `config.yaml`:

```yaml
stt:
  engine: faster_whisper
  prefer_voxtral_when_configured: true
  voxtral_mode: self_hosted
  voxtral_self_hosted_url: http://127.0.0.1:8000
  voxtral_self_hosted_enabled: false
  voxtral_self_hosted_autostart: true
  voxtral_self_hosted_launch: ""
  voxtral_self_hosted_workdir: ""
  voxtral_model: voxtral-mini-latest
```

Keep:

```yaml
tts:
  engine: xtts_tts
```

When the local runtime is really in place:

- set `voxtral_self_hosted_launch` to the actual command that starts your local server
- optionally set `voxtral_self_hosted_workdir`
- then switch `voxtral_self_hosted_enabled: true`

## Practical rollout

1. Keep `Local Whisper` as the stable default.
2. Build or install a local self-hosted Voxtral runtime separately.
3. Expose it at `http://127.0.0.1:8000/v1/audio/transcriptions`.
4. Put the real launch command into Nellie's config.
5. Let Nellie autostart or connect to it.
6. Use `Refresh Speech Runtime` and `Test Speech Input` before relying on it in conversation.

## Notes

- The app side is prepared for `self_hosted` mode.
- The desktop app now has the beginning of a managed runtime path:
  - status in UI
  - refresh button
  - start button
  - autostart hook
- This project still does not include the actual Voxtral server runtime itself.
- If you self-host on Windows and hit serving issues, `WSL2` or Linux is the recommended path.
- The exact launch command depends on the runtime stack you choose for serving Voxtral.
