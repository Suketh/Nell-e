# Fish Speech Server Plan

This is the intended production path for using Fish Speech as Nellie's primary voice engine without breaking the current app stack.

## Goal

Run Fish Speech as a separate TTS service and let Nellie's backend call it through the existing `/v1/tts` route.

Current behavior:
- Nellie backend prefers `fish_speech`
- falls back automatically to `vibevoice_realtime`
- mobile/web/desktop clients stay unchanged

That means the client contract is already stable. The missing part is the external Fish Speech server itself.

## Recommended deployment shape

Use:
- Linux server or WSL2
- dedicated GPU if possible
- separate process from Ollama and STT

Avoid:
- running Fish Speech directly inside the current Windows desktop backend process
- sharing a constrained 8 GB GPU with Ollama, STT, and Fish Speech at the same time

## Nellie-side contract

Nellie expects the Fish Speech service to expose:

### Health

`GET /health`

Expected:

```json
{
  "ok": true
}
```

Any `200` health response is enough for warmup.

### Synthesis

`GET /v1/tts?text=...&language=en`

Expected response:
- `200 OK`
- `Content-Type: audio/wav`
- body: valid WAV bytes

Optional later variant:
- `POST /v1/tts`
- JSON body with `text` and `language`

If the service later requires POST instead of GET, update:

```yaml
tts:
  fish_speech:
    use_post: true
```

## Current Nellie config

Already prepared in `config.yaml`:

```yaml
tts:
  engine: fish_speech
  fallback_engine: vibevoice_realtime
  fish_speech:
    base_url: http://127.0.0.1:8890
    health_url: http://127.0.0.1:8890/health
    synth_path: /v1/tts
    timeout: 90
    output_samplerate: 24000
    use_post: false
```

This means:
- if Fish Speech is up on port `8890`, Nellie will try it first
- if not, Nellie falls back to VibeVoice

## Suggested server wrapper

The cleanest path is a very small adapter service in front of Fish Speech.

Why:
- Nellie wants one simple WAV endpoint
- Fish Speech tooling may evolve
- the adapter isolates Nellie from upstream runtime changes

Suggested wrapper responsibilities:
- accept `text`
- call local Fish runtime
- return `audio/wav`
- expose `/health`
- optionally cache short repeated phrases

The first Nellie-side wrapper stub now exists at:

- [server/fish_tts_adapter.py](/c:/Users/D665/Desktop/PYTHONprogram/large/Nellie/nellie/server/fish_tts_adapter.py)

Example contract-only startup:

```powershell
python server\fish_tts_adapter.py --host 127.0.0.1 --port 8890 --mock
```

Example proxy startup once a real upstream Fish runtime exists:

```powershell
python server\fish_tts_adapter.py --host 127.0.0.1 --port 8890 --upstream-url http://127.0.0.1:9000/v1/tts --upstream-health-url http://127.0.0.1:9000/health
```

## Minimal runtime checklist

Before switching Nellie to Fish for real, confirm:

1. `GET /health` returns `200`
2. `GET /v1/tts?text=hello` returns valid WAV
3. first audio latency is acceptable
4. longer sentences do not clip at the end
5. repeated requests do not crash the service
6. GPU memory remains stable under repeated calls

## Validation from Nellie side

Once the Fish service is running, verify from the Nellie machine:

```powershell
python -c "import requests; print(requests.get('http://127.0.0.1:8890/health', timeout=10).status_code)"
```

Then:

```powershell
python -c "import requests; r=requests.get('http://127.0.0.1:8877/v1/tts', params={'text':'Hello from Nellie'}, timeout=120); print(r.status_code, r.headers.get('Content-Type'), len(r.content))"
```

If both work, Nellie is already routing through Fish Speech first.

## Rollout strategy

Recommended order:

1. bring up Fish Speech service separately
2. verify direct `/health` and `/v1/tts`
3. keep fallback enabled
4. test desktop
5. test mobile voice playback
6. only after stability: consider removing fallback

## What not to do yet

Do not remove `vibevoice_realtime` until:
- Fish Speech has been running stably for several sessions
- mobile playback sounds correct
- end-of-sentence clipping is not worse than current TTS
- latency is acceptable in real use

## Future nice-to-haves

Later, we can add:
- server-side voice style presets for Nellie
- shorter "spoken form" generation for mobile
- phrase cache on Fish side
- diagnostics that tag whether a reply used `fish_speech` or fallback
