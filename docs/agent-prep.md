# Agent Prep

## Current Shape
- `ui/main_window.py` owns presentation, input handling, and voice playback.
- `services/conversation_service.py` now owns the core conversation entry point.
- `services/agent_service.py` now owns the first orchestration layer:
  - decide direct reply vs tool-assisted reply
  - call model
  - persist memory
- `services/tool_registry.py` owns tool registration and lookup.
- `services/memory/sqlite_store.py` owns recall and memory extraction.
- `services/tools/*` are early local tool adapters.

## Why This Matters
This creates the first clean seam for future agent work:

`UI -> ConversationService -> AgentService -> model/memory/tools`

Later, the UI can call:
- a local conversation service
- a remote API with the same contract
- an agent runner behind the same service boundary

## Next Good Refactors
1. Split memory into two layers
   - chat history store
   - user profile / semantic memory store

2. Add richer response envelopes
   - `reply`
   - `mood`
   - `tool_events`
   - `agent_trace`
   - `tts_text`

3. Keep UI dumb
   - UI should render turns and statuses
   - orchestration should stay outside Qt widgets

4. Upgrade agent planning
   - richer tool selection
   - multi-step execution
   - error-aware fallbacks

## Minimal Target Architecture
- `ui/`
- `services/conversation_service.py`
- `services/agent_service.py`
- `services/tool_registry.py`
- `services/tools/*.py`
- `services/memory/*.py`

## First Agent Candidates
- web lookup
- PDF reading
- image description
- local task helpers

## Rule Of Thumb
Any logic that decides:
- what Nellie should do
- what tools to call
- what to remember
- what to say vs. what to speak

should move out of the UI layer.
