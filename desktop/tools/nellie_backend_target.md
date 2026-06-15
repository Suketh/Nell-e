# Nellie Backend Target

## Goal

Move as much of Nellie's backend as possible off the desktop UI process and into a local backend service, so the frontend app can become lighter and easier to reuse later in a mobile-style client.

This should support two modes:

1. `desktop_local`
- current-style desktop app
- can still run everything locally in one machine

2. `thin_client`
- UI app becomes mainly:
  - chat surface
  - avatar/mood rendering
  - mic input
  - audio playback
  - settings
- most backend logic runs in a local or LAN backend server


## Target Split

### Frontend Client

Keep in the frontend:
- Qt UI
- avatar/mood visuals
- recorder widget and push-to-talk UX
- text input
- audio playback output
- local settings view
- minimal session status display

The frontend should ideally call backend APIs for:
- conversation replies
- memory reads/writes
- speech-to-text
- tool actions
- optional text-to-speech generation


### Backend Service

Move into backend service:
- LLM orchestration
- memory store access
- emotion state logic
- web/tool actions
- Spotify / YouTube / Wikipedia helpers
- STT runtime control
- optional TTS generation
- response shaping and continuity logic


## Best Migration Order

### Phase 1

Externalize first:
- LLM
- memory
- tool actions

Reason:
- these are already logically service-like
- they do not need direct Qt access
- they carry most of Nellie's "brain"


### Phase 2

Externalize next:
- STT

Reason:
- STT is already partly separable
- Voxtral already points in this direction
- this reduces local frontend weight further


### Phase 3

Decide later:
- keep TTS local in client
- or move TTS generation to backend and stream/play audio in client

My current recommendation:
- keep playback in client
- decide later whether XTTS synthesis itself should stay local or move server-side


## Suggested Backend API Shape

### `POST /v1/chat/respond`

Input:
- user text
- source (`text` or `speech`)
- language
- current conversation flags

Output:
- reply text
- mood
- expression
- optional tool action


### `GET /v1/memory/user`

Returns saved user facts and notes.


### `POST /v1/memory/remember`

Stores explicit memory notes.


### `POST /v1/memory/forget`

Deletes matching memory notes.


### `POST /v1/tools/action`

For:
- spotify
- youtube
- wikipedia
- web search


### `POST /v1/audio/transcriptions`

STT endpoint.


### Optional `POST /v1/audio/speak`

Only if TTS later moves into backend.


## Recommended Long-Term Topology

### Near-Term

- frontend desktop app on Windows
- local backend service on same machine
- client talks to:
  - `http://127.0.0.1:8001` for brain/tools/memory
  - `http://127.0.0.1:8080` for STT if desired


### Later Mobile-Friendly Direction

- thin frontend client
- shared Nellie backend on:
  - same laptop
  - home mini PC
  - local network box

This would make it easier to build:
- lighter desktop client
- tablet-like client
- mobile companion UI


## Concrete Next Refactor

Create one backend-facing service boundary for:
- `chat`
- `memory`
- `tools`

That means the frontend should eventually stop calling these modules directly:
- `llm/*`
- `services/memory/sqlite_store.py`
- `services/tools/*`

Instead, frontend should call a client such as:
- `services/backend/client.py`


## First Practical Implementation Step

Introduce a backend client layer that the UI talks to, even if it still points to local in-process implementations at first.

Suggested target:
- add `services/backend/client.py`
- add `services/backend/local_adapter.py`
- route `MainWindow` through that boundary

This gives a clean migration path from:
- in-process desktop app

to:
- local backend server

without rewriting the UI again later.
