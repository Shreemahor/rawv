# Rawv

Research AI With Voice

## Transparent research voice mode

- Default flow: transcribe -> search -> browse -> synthesize -> quality check -> speak.
- Text command: `quick research on <topic>`
- Text command: `normal research on <topic>`
- Text command: `deep research on <topic>`
- Every answer includes visible research steps and source links.

## Environment variables

- `GROQ_API_KEY` required for STT and synthesis model calls.
- `RAWV_WHISPER_MODEL` optional, default `whisper-large-v3-turbo`.
- `RAWV_CHAT_MODEL` optional, default `llama-3.1-8b-instant`.
- `RAWV_TTS_VOICE` optional, default `en-US-AriaNeural`.
- `RAWV_TTS_RATE` optional, default `+5%`.
- `RAWV_RESEARCH_DEFAULT_MODE` optional: `quick`, `normal`, or `deep`.
- `RAWV_BROWSER_EVIDENCE` optional: `true` to attempt UID capture from local browser tooling.
