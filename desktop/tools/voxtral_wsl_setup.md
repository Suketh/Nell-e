# Voxtral via WSL2 for Nellie

This is the recommended path if you want `XTTS + self-hosted Voxtral` with the least friction on Windows.

## Current state

- Nellie already supports:
  - `XTTS v2` for voice output
  - `Local Whisper` as the stable speech-input default
  - `Voxtral Realtime` as a future self-hosted speech-input upgrade
- Your app is already prepared to talk to a local transcription endpoint at:

```text
http://127.0.0.1:8000/v1/audio/transcriptions
```

## Why WSL2

For this project, `WSL2` is the safest future path because:

- Linux model-serving stacks tend to be better supported than native Windows for this class of workload
- it keeps Voxtral separate from the desktop app
- Nellie can stay simple and just call a local HTTP endpoint

## Goal architecture

```text
Windows app (Nellie)
  -> XTTS runs inside the app
  -> speech input defaults to Whisper
  -> future upgrade: POST audio to http://127.0.0.1:8000/v1/audio/transcriptions

WSL2 runtime
  -> runs Voxtral-compatible transcription server
  -> exposes OpenAI-compatible audio transcription endpoint
```

## Step plan

1. Install `WSL2`
2. Install an Ubuntu distro
3. Inside WSL, set up the serving runtime for Voxtral
4. Expose it on `127.0.0.1:8000`
5. Put the real launch command into Nellie's `config.yaml`
6. Let Nellie autostart or connect to it

## Nellie config target

When your runtime exists, the target config shape is:

```yaml
stt:
  engine: faster_whisper
  prefer_voxtral_when_configured: true
  voxtral_mode: self_hosted
  voxtral_self_hosted_url: http://127.0.0.1:8000
  voxtral_self_hosted_enabled: true
  voxtral_self_hosted_autostart: true
  voxtral_self_hosted_launch: ""
  voxtral_self_hosted_workdir: ""
  voxtral_model: voxtral-mini-latest
```

## Launch-command idea

Once WSL is installed and your Voxtral server is actually runnable there, Nellie can use a Windows-side command in this shape:

```powershell
wsl -d Ubuntu -- bash -lc "<your actual voxtral server command here>"
```

That full command is what should go into:

- `stt.voxtral_self_hosted_launch`

And if needed:

- `stt.voxtral_self_hosted_workdir`

## Notes

- Do not switch Nellie fully to Voxtral until the WSL runtime actually answers on `127.0.0.1:8000`
- Keep `Local Whisper` as the safe operational default until then
- XTTS stays unchanged in the app
