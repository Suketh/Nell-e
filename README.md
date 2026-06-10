# Nellie

Nellie is a local AI companion project with multiple clients on top of the same backend:

- desktop app in PySide6
- mobile app in Expo/React Native
- web client for admin and overview
- conversation server
- STT server for speech-to-text
- XTTS server for voice synthesis

## Modernized Desktop

The actively updated desktop application now lives in `desktop/`. It combines the
responsive PySide6 interface with:

- Chatterbox-Turbo as the primary expressive TTS engine
- XTTS as an automatic fallback
- local Ollama model switching
- persistent conversation and preference memory
- weather, web, Wikipedia, YouTube, and Spotify actions
- safe arithmetic, local date/time, webpage reading, PDF extraction, and vision
- contextual follow-up handling for people, albums, songs, and searches

Start this version from the repository root:

```powershell
.\Start Nellie Desktop.bat
```

The start file delegates to `desktop/run_local.bat`, which is the canonical
desktop launcher. The existing mobile, web, and server stack remains available
for continued development.

The project is built for local Windows use and uses Ollama for the language model, but the end product targets to become a mobile app.

## Project Structure

- `desktop/app.py` starts the modernized desktop app
- `app.py` remains the original full-stack desktop client
- `config.yaml` contains runtime configuration
- `server/` contains the HTTP servers for conversation, STT, and XTTS
- `services/` contains dialogue logic, tools, memory, and audio adapters
- `ui/` contains the desktop interface
- `mobile/` contains the Expo mobile app
- `web/` contains the web client
- `scripts/` contains PowerShell scripts for start, stop, and status
- `data/` contains local data, logs, and user memory

## Requirements

- Windows
- Python 3.11 or 3.12
- Node.js and npm
- Ollama installed locally
- A GPU is recommended for XTTS and faster STT, but not required for all functionality

## Python and Node Setup

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Install mobile app dependencies:

```powershell
cd mobile
npm install
```

## Ollama

Nellie uses Ollama according to `config.yaml`.

Current defaults in this project:

- text model: `hermes3:8b`
- vision model: `llava:7b`

Example:

```powershell
ollama pull hermes3:8b
ollama pull llava:7b
```

## Quick Start

### Desktop

Simplest option:

```powershell
.\Start Nellie Desktop.bat
```

Or directly:

```powershell
python app.py
```

### Web + Desktop

```powershell
.\Start Nellie All.bat
```

This starts:

- the web client
- the conversation server
- the desktop app

### Mobile

For mobile testing through Expo Go:

```powershell
.\Start Nellie Mobile HTTPS.bat
```

This starts the mobile stack through `scripts/start_nellie_stack.ps1 -MobileExpo` and should give you an Expo address like:

```text
exp://192.168.x.x:8081
```

Stop everything with:

```powershell
.\Stop Nellie Stack.bat
```

Check status with:

```powershell
.\Nellie Status.bat
```

## Manual Start Commands

### Conversation Server

```powershell
python server/conversation_server.py --host 127.0.0.1 --port 8877
```

### STT Server

```powershell
python server/stt_server.py --host 127.0.0.1 --port 8765
```

### XTTS Server

```powershell
python server/xtts_tts_server.py --host 127.0.0.1 --port 8891 --language en
```

### Expo Mobile

```powershell
cd mobile
npx expo start --lan --port 8081
```

### Web

```powershell
cd web
npm install
npm run dev
```

## Important Ports

- `8877` conversation backend
- `8765` STT backend
- `8891` XTTS backend
- `8081` Expo Metro
- `5173` web client

## Configuration

All main configuration lives in `config.yaml`.

Key sections:

- `ollama`
- `stt`
- `tts`
- `paths`

Examples of what is controlled there:

- which text model is used
- which TTS engine is used
- which voice profiles exist
- STT provider and fallback
- local paths for data and gallery

## Voices

Voice profiles are defined in `config.yaml` under `tts.voice_profiles`.

Examples:

- `nellie1`
- `nellie2`
- `nellie3`

Voice samples are stored in:

- `assets/voices/Nellie1.wav`
- `assets/voices/Nellie2.wav`
- `assets/voices/Nellie3.wav`

## Mobile Environment Variables

The mobile app can read:

- `EXPO_PUBLIC_NELLIE_API_BASE`
- `EXPO_PUBLIC_NELLIE_STT_BASE`
- `EXPO_PUBLIC_NELLIE_ADMIN_WEB_URL`

The mobile start script normally sets these for you.

## Troubleshooting

### Expo Cannot Find the App

If Expo Go says the packager is not running:

- make sure `Start Nellie Mobile HTTPS.bat` is actually running
- make sure the phone is on the same network as the computer
- use the current `exp://...` address from the latest Expo session

### `STT failed`

Check:

- that the STT server is running on `8765`
- that `config.yaml` points to the correct STT provider
- that `data/run/stt.log` and `data/run/stt.err.log` do not show errors

### Slow Voice Response

Check these first:

- `data/diagnostics/admin-mobile.jsonl`
- `server_chat_timing`
- `server_tts_timing`
- `tts_fetch_ms`
- `audio_load_ms`

### Wrong IP During Mobile Testing

If the computer has multiple network adapters, Expo or the backend may choose the wrong IP. The start script tries to prefer LAN addresses, but you should still verify that the phone is using the same network as the computer.

## Data and Logs

This project creates local files that normally should not be pushed:

- `data/run/`
- `data/diagnostics/`
- `data/users/`
- local SQLite databases
- `.venv/`
- `.voxtral-venv/`
- `.xtts-venv/`
- `models/`
- large cache or model files under `external/`

## Recommended `.gitignore`

When you publish this project to GitHub, you should at least ignore:

```gitignore
.venv/
.voxtral-venv/
.xtts-venv/
__pycache__/
data/run/
data/diagnostics/
data/users/
data/*.db
data/*.sqlite
models/
mobile/node_modules/
web/node_modules/
```

## Current State

The codebase has been actively cleaned up and split into more navigable parts, but it is still a practical development project rather than a fully packaged product. This README is therefore written to help you start, debug, and extend the project quickly.
