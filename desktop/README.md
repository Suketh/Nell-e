# Nellie

Lightweight desktop chat app with:
- PySide6 UI
- Ollama for local LLM responses
- Faster-Whisper for speech-to-text
- Selectable text-to-speech
- Optional selectable speech-input backends

## Quickstart
1. Pull the Ollama models:
```bash
ollama pull llama3.2:3b
ollama pull llava:7b
```
2. Use the Python 3.11 local runtime for the app.
3. Run the app with:
```powershell
.\run_local.bat
```

`run_local.bat` is the canonical start file. It selects the project's Python 3.11
environment, applies local runtime paths, and starts `app.py`.

## Default behaviour
- `tts.engine: chatterbox_turbo` is the primary local TTS path.
- Chatterbox runs in `.venv_chatterbox` so its pinned ML dependencies do not conflict with XTTS.
- `stt.engine: faster_whisper` is the default local STT path.
- Python 3.11 is the supported runtime for this project.
- `stt.device: auto` tries CUDA first and otherwise falls back to CPU.
- `audio.input_device` is empty by default, so the system microphone is used.
- `ollama_runtime` is forwarded to Ollama chat options.
- `ollama_runtime.think: false` keeps reasoning models from spending the reply budget on hidden thinking.
- `quick_replies: false` lets the model handle greetings and check-ins instead of using canned responses.
- Conversation prompts encourage emotional continuity, varied cadence, specific opinions, and occasional initiative.
- Explicit likes, dislikes, favorites, habits, and upcoming plans are remembered automatically.
- Recent conversation is prioritized over static persona text so short reactions keep their intended context.
- The active Ollama language model can be changed in Settings under Conversation.

Configured language-model choices:
- `Gemma 3 Uncensored (4B)`
- `Gemma 4 (8B)` using the installed Ollama model `gemma4:latest`

## Config
The main settings live in `config.yaml`.

```yaml
ollama:
  host: http://localhost:11434
  text_model: llama3.2:3b
  vision_model: llava:7b

stt:
  engine: faster_whisper
  model_size: small.en
  device: auto

tts:
  engine: chatterbox_turbo

audio:
  input_device:
```

## TTS engines
- `chatterbox_turbo`: primary expressive English voice-cloning path
- `xtts_tts`: automatic fallback and selectable legacy path

## Speech input backends
- `faster_whisper`: current stable local default
- `voxtral_realtime`: future self-hosted upgrade path with two modes:
  - `api`
  - `self_hosted`

### Voxtral self-hosted target
If you want to keep speech input local-ish/self-hosted, Nellie is now prepared to call a Voxtral-compatible server at:

```text
http://127.0.0.1:8000/v1/audio/transcriptions
```

See:

- [tools/voxtral_self_hosted.md](tools/voxtral_self_hosted.md)
- [tools/voxtral_wsl_setup.md](tools/voxtral_wsl_setup.md)
- [tools/start_voxtral_self_hosted.bat](tools/start_voxtral_self_hosted.bat)
- [tools/start_voxtral_wsl_template.bat](tools/start_voxtral_wsl_template.bat)

Recommended direction:

- keep `faster_whisper` as the stable current default
- treat `Voxtral self-hosted` as the future upgrade path
- most realistic setup on this project is `WSL2 + vLLM + local OpenAI-compatible transcription endpoint`

### XTTS v2
XTTS v2 is the active local TTS path in the app.

Typical config:
```yaml
tts:
  engine: chatterbox_turbo
  voice_sample: assets/voices/Nellie.wav
  xtts_model: tts_models/multilingual/multi-dataset/xtts_v2
  xtts_language: en
```

## Gallery posts
Nellie can post images from `data/gallery`.

Add image files to that folder and describe them in `data/gallery/manifest.json`.

Example:
```json
[
  {
    "file": "cafe.jpg",
    "name": "cafe selfie",
    "moods": ["flirty", "happy"],
    "triggers": ["coffee", "date", "cute"],
    "caption": "I thought this one fit the mood."
  }
]
```

The app uses:
- current conversation mood
- trigger words in the conversation
- `gallery_habits` in `data/personality.json`

## Web search
Nellie can optionally use web search for current facts.

Turn on `Allow web search for current info` in Settings, then ask a current-info question or start a message with `/search `.

Example:
```text
/search latest news about OpenAI
```

## Language
Nellie can switch between English and Swedish in Settings.

The language setting affects:
- chat reply language
- speech-to-text language hint

Note: Swedish speech recognition works best with a multilingual Whisper model such as `small` rather than `small.en`.
