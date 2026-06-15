# Nellie Project Structure Plan

## Goal
Split the project into three clear application boxes with shared domain logic:

1. `backend/server`
2. `frontend/desktop`
3. `frontend/web-mobile`

The shared logic should live outside those entrypoints so the UI layers stay thin.

## Current Reality

### Already close to backend
- `server/conversation_server.py`
- `server/stt_server.py`
- `services/conversation_service.py`
- `services/agent_service.py`
- `services/memory/sqlite_store.py`
- `services/tool_registry.py`
- `services/tools/*`
- `llm/ollama_client.py`
- `services/persona_profile.py`
- `services/conversation_http.py`
- `services/audio/stt_server_http.py`

### Desktop-specific
- `app.py`
- `ui/main_window.py`
- `ui/mood_avatar.py`
- `ui/chat_view.py`
- `ui/recorder_widget.py`
- local desktop TTS adapters in `services/audio/*` when they play sound on the machine directly

### Web/mobile-specific
- `web/src/*`
- `web/src/api/client.ts`
- `web/src/components/*`

## Main Architectural Problem
The project already has the right ingredients, but they are not grouped around ownership.

Right now:
- `services/` mixes true backend logic with client helpers
- `ui/main_window.py` owns too much orchestration
- audio paths are split between desktop-local behavior and server-friendly behavior
- `app.py` still wires several concerns at once

That makes future work slower:
- desktop changes are harder to isolate
- web/mobile voice mode is harder to add cleanly
- server deployment remains conceptually blurred with desktop runtime

## Target Structure

```text
nellie/
  app_desktop.py
  apps/
    backend/
      conversation_api.py
      stt_api.py
      runtime.py
    desktop/
      main_window.py
      controllers/
      widgets/
      state/
    web/
      client/   # current web/ source can conceptually map here
  domain/
    conversation/
    progression/
    gallery/
    persona/
    memory/
    tools/
  infra/
    llm/
    storage/
    audio/
  assets/
  data/
```

## Recommended Mapping

### 1. `domain/`
Pure app behavior. No PySide, no browser UI, no direct HTTP handler code.

Put here:
- progression rules
- gallery unlock logic
- relationship stage logic
- persona normalization rules
- memory extraction rules
- tool-planning behavior

Candidates from current tree:
- parts of `services/conversation_service.py`
- parts of `services/agent_service.py`
- parts of `services/persona_profile.py`
- parts of `services/memory/sqlite_store.py` that are about meaning, not SQLite plumbing

### 2. `infra/`
Adapters to the outside world.

Put here:
- Ollama adapter
- SQLite adapter
- TTS/STT adapters
- browser/web/wiki/pdf tool integrations

Candidates from current tree:
- `llm/ollama_client.py`
- `services/memory/sqlite_store.py` storage parts
- `services/audio/*`
- `services/tools/*`

### 3. `apps/backend/`
HTTP servers and server runtime composition.

Put here:
- conversation API entrypoint
- STT API entrypoint
- multi-user runtime assembly
- request/response DTO mapping

Candidates from current tree:
- `server/conversation_server.py`
- `server/stt_server.py`

### 4. `apps/desktop/`
PySide desktop app only.

Put here:
- main window
- widgets
- desktop-only controllers
- local profile UI
- startup/loading orchestration for desktop

Candidates from current tree:
- `ui/main_window.py`
- `ui/mood_avatar.py`
- `ui/chat_view.py`
- `ui/recorder_widget.py`

### 5. `apps/web/`
React web/mobile client only.

Put here:
- React components
- API client
- web-only state and layout

Candidates from current tree:
- current `web/`

## Concrete Split For `ui/main_window.py`

`ui/main_window.py` should be reduced into a shell plus controllers/widgets.

### Extract first
- `ui/controllers/profile_controller.py`
  - load/save/switch/create/rename/delete profiles
- `ui/controllers/startup_controller.py`
  - startup progress, warmup state, backend readiness
- `ui/controllers/chat_controller.py`
  - send reply, handle stream/update mood, turn log
- `ui/panels/progression_panel.py`
  - level/xp/stage rendering
- `ui/panels/gallery_panel.py`
  - unlocked gallery and gallery actions

### Leave in `MainWindow`
- top-level layout composition
- signal wiring between panels/controllers
- final ownership of shared widgets

## Concrete Split For Audio

Audio should be separated by execution model, not by random adapter name.

Recommended:

```text
infra/audio/
  stt/
    faster_whisper.py
    whispercpp.py
    http_client.py
  tts/
    pyttsx3.py
    coqui_xtts.py
    vibevoice_realtime.py
    null_tts.py
```

And then:
- desktop decides whether to play locally
- backend decides whether to synthesize/stream for clients

This is important for mobile voice mode.

## Concrete Split For Backend

Recommended:

```text
apps/backend/
  conversation_api.py
  stt_api.py
  runtime.py
  schemas.py
```

Where:
- `runtime.py` owns multi-user service creation
- `schemas.py` owns response/request shapes
- API files stay thin

## Concrete Split For Web/Mobile

Recommended:

```text
web/src/
  app/
    AppShell.tsx
    routes.ts
  features/
    chat/
    gallery/
    bond/
    profile/
  components/
    shared/
  api/
  types/
```

Current likely feature buckets:
- `chat`: `ChatPanel`, `Composer`, `MessageList`
- `gallery`: gallery room and item cards
- `bond`: bond view and mood presentation
- `profile`: profile switcher

## Migration Order

### Phase 1: Safe file organization without behavior change
- extract desktop profile logic from `ui/main_window.py`
- extract startup/loading logic
- extract gallery/progression UI panels
- keep imports stable

### Phase 2: Backend clarity
- move backend runtime assembly out of `server/conversation_server.py`
- create backend schemas module
- isolate HTTP layer from runtime logic

### Phase 3: Shared domain cleanup
- split progression/gallery/persona logic out of `services/conversation_service.py`
- keep service as orchestration only

### Phase 4: Web feature grouping
- move current `web/src/components/*` into feature folders
- make `App.tsx` thinner

## Immediate Low-Risk Next Step

If only one refactor starts now, it should be:

1. split `ui/main_window.py`
2. then split backend runtime from API handlers
3. then split web into feature folders

That order gives the best return with the least breakage risk.

## Bottom Line

The project should not be split into three isolated apps with duplicated logic.

It should be split into:
- shared domain and infrastructure
- three thin application shells:
  - backend
  - desktop
  - web/mobile

That is the structure most likely to let Nellie grow without the codebase turning brittle.
