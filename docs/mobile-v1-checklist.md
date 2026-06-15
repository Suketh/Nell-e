# Nellie Mobile V1 Checklist

## Goal
- Mobile app handles chat and voice reliably.
- Admin, rollout, and operational controls stay in the desktop web client.

## Must Pass
- Expo app opens on the phone from LAN without manual debugging.
- Chat text send/receive works against the same backend as desktop/web.
- `Voice shell` completes the full loop:
  - record
  - transcribe
  - reply
  - play
- Mood portrait updates from Nellie's reply mood.
- `Gallery` loads without list/render warnings.
- `Bond` shows live progression data for the active profile.

## Backend
- Conversation server listens on LAN, not only `127.0.0.1`.
- STT server listens on LAN, not only `127.0.0.1`.
- `/v1/chat/reply` returns stable payloads.
- `/v1/profile-summary` returns stage/xp/level.
- `/v1/gallery/catalog` and `/v1/gallery/unlocked` return items for the active user.
- `/v1/tts` returns playable audio.
- `/v1/assets/moods/<mood>.png` returns the expected portrait.

## Mobile UX
- `Chat` is the default tab.
- Voice states are obvious:
  - ready
  - listening
  - transcribing
  - replying
  - playing
- Errors surface as clear human messages, not raw transport failures.
- Active mood image is visible and not tiny.
- Buttons do not allow duplicate taps during busy phases.

## Before Wider Rollout
- Replace LAN IP defaults with configurable environment values per deployment.
- Decide whether Expo Go is enough for testing or if EAS/dev builds are needed.
- Add one restart path for:
  - backend
  - STT
  - Expo
- Run one end-to-end test on:
  - desktop app
  - desktop web
  - mobile Expo app

## Not In V1
- Mobile admin mode
- Mobile rollout controls
- Advanced profile management on phone
- Production auth
- Push notifications
