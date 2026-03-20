# RAWV Hosting Plan (Docker + Hugging Face Spaces)

This runbook is the full plan to host RAWV on Hugging Face Spaces so your laptop does not need to stay on.

## 1. Goal and Current Fit

You already have the key pieces needed for hosted deployment:
- Chainlit app entrypoint in [app.py](app.py)
- Custom Chainlit config in [.chainlit/config.toml](.chainlit/config.toml)
- Custom UI assets in [public/stylesheet.css](public/stylesheet.css) and [public/rawv-avatar-favicon.png](public/rawv-avatar-favicon.png)
- Python dependency list in [requirements.txt](requirements.txt)

What is still needed:
- Add Docker packaging files
- Add Hugging Face Space metadata
- Configure HF secrets/variables
- Remove or disable any host-local browser assumptions in production
- Validate voice input/output in a hosted browser context

---

## 2. Big Constraint to Decide First

RAWV currently has an optional browser evidence path that tries to use local Chrome tooling:
- [rawv/research/browser_adapter.py](rawv/research/browser_adapter.py)

On Hugging Face Spaces this is usually not available as-is because:
- No direct access to your local Chrome instance
- Different sandbox/runtime constraints
- MCP/local desktop coupling is not guaranteed

Recommendation for first hosted release:
- Keep `RAWV_BROWSER_EVIDENCE=false`
- Use search + HTML extraction + synthesis as the default transparent research path

If later you want full browser control in cloud, move to server-side Playwright flow (separate phase).

---

## 3. Required Repository Changes

## 3.1 Add a Dockerfile

Create a root [Dockerfile](Dockerfile):

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Basic OS packages useful for HTTPS, certs, and audio tooling compatibility.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# HF Spaces provides PORT env var for Docker apps.
ENV CHAINLIT_HOST=0.0.0.0
ENV CHAINLIT_PORT=7860

EXPOSE 7860

CMD ["sh", "-c", "chainlit run app.py --host 0.0.0.0 --port ${PORT:-7860}"]
```

Notes:
- Keep `PORT` fallback to 7860 for local Docker runs.
- `ffmpeg` is included as a safety dependency for audio handling edge cases.

## 3.2 Add .dockerignore

Create [.dockerignore](.dockerignore):

```dockerignore
.venv
__pycache__
*.pyc
.git
.gitignore
*.log
*.tmp
*.ipynb
```

This keeps image builds smaller and faster.

## 3.3 Add HF Space README frontmatter

Update [README.md](README.md) with YAML frontmatter at top (required by Hugging Face Spaces):

```yaml
---
title: RAWV
emoji: "🔬"
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---
```

Then keep your normal README content below it.

## 3.4 Keep Chainlit config production-safe

In [.chainlit/config.toml](.chainlit/config.toml), current settings are mostly fine.
Production recommendations:
- Keep `default_theme = "light"`
- Keep `custom_css`, `logo_file_url`, and `default_avatar_file_url`
- Keep audio enabled
- Optionally tighten `allow_origins` later if needed

---

## 4. Environment Variables and Secrets on Hugging Face

Set these in Space Settings:

## 4.1 Secrets (sensitive)
- `GROQ_API_KEY` (required)

## 4.2 Variables (non-sensitive)
- `RAWV_CHAT_MODEL` (example: `llama-3.1-8b-instant`)
- `RAWV_WHISPER_MODEL` (example: `whisper-large-v3-turbo`)
- `RAWV_TTS_VOICE` (example: `en-US-AriaNeural`)
- `RAWV_TTS_RATE` (example: `+5%`)
- `RAWV_RESEARCH_DEFAULT_MODE` (`normal` recommended)
- `RAWV_BROWSER_EVIDENCE` (`false` for hosted v1)
- `RAWV_AUDIO_SAMPLE_RATE` (`24000`)

Good default hosted profile:
- Faster + lower cost model first
- Browser evidence off
- Normal research mode default

---

## 5. Hugging Face Spaces Setup Steps

1. Create new Space in HF UI.
2. Choose:
   - SDK: Docker
   - Visibility: private or public based on your launch plan
   - Hardware: start with CPU Basic, then scale up if needed
3. Connect GitHub repo or push directly to Space git remote.
4. Ensure [Dockerfile](Dockerfile) exists at repo root.
5. Add Space Secrets and Variables from Section 4.
6. Deploy and watch build logs.
7. Open app URL and run smoke tests (Section 8).

---

## 6. Operational Notes for "Laptop-Off" Hosting

What you gain:
- Always-on web app independent of your local machine
- Public URL for demos/users

What you still need to manage:
- API key health and quotas (Groq limits)
- Space runtime restarts/build failures
- Versioned updates via git push

Cost/runtime expectations:
- CPU Basic can handle light usage
- Audio + research + synthesis under concurrency can require better hardware

---

## 7. Production Hardening Checklist

## 7.1 App behavior
- Keep non-research chat path for greetings/smalltalk
- Keep research only when needed or forced by toggle
- Ensure all exceptions show user-friendly messages

## 7.2 Security
- Never hardcode `GROQ_API_KEY`
- Keep secrets only in HF Secret settings
- Avoid enabling unsafe HTML rendering unless required

## 7.3 Rate limits and resilience
- Add retry/backoff around external calls
- Add graceful fallback when search/source extraction fails
- Optionally add in-memory short TTL cache for repeated questions

## 7.4 Observability
- Use clear step logs in Chainlit steps
- Add concise error reporting to UI
- Consider writing structured logs for source failures

---

## 8. Smoke Test Plan After Deployment

Run these tests in hosted Space:

1. UI/Branding
- RAWV icon appears in header/avatar
- Silver/baby-blue palette applies
- Buttons are high contrast and readable

2. Text chat no-research path
- Input: "hello"
- Expected: quick conversational response, no research steps

3. Research path
- Input: "deep research on latest multimodal model benchmarks"
- Expected: transparent steps + sources + spoken summary

4. Toggle path
- Turn "RESEARCH MODE (FORCE ON)" on
- Ask a non-trivial question
- Expected: research path is used even without explicit "research" phrase

5. Audio path
- Record short microphone input
- Expected: transcript step appears, answer + TTS audio returned

6. Fallback behavior
- Ask a difficult/obscure question
- Expected: no crash; graceful fallback text

---

## 9. Known Hosted Risks and Mitigations

1. Search/source fetch intermittency
- Mitigation: retries + fallback answer

2. Groq throttling
- Mitigation: concise outputs, request pacing, optional queue logic for scale

3. Audio browser differences
- Mitigation: test with Chrome first, then Edge/Safari; keep clear user messaging

4. Browser evidence mode in cloud
- Mitigation: keep disabled unless replaced with server-compatible browser automation stack

---

## 10. Suggested Next Commits (in order)

1. Add [Dockerfile](Dockerfile)
2. Add [.dockerignore](.dockerignore)
3. Add HF frontmatter in [README.md](README.md)
4. Push to main and deploy Space
5. Configure HF secrets/variables
6. Run smoke tests from Section 8

---

## 11. Optional Phase 2 Improvements

- Add Playwright-based server browser module for cloud-safe browser evidence
- Add short-term conversation memory store
- Add source quality scoring before synthesis
- Add basic analytics on research-toggle usage and failure rates
- Add endpoint health check and startup self-test message

---

## 12. Quick Reference

Minimum to go live:
- Dockerfile
- HF README frontmatter
- GROQ_API_KEY secret
- `RAWV_BROWSER_EVIDENCE=false`
- Deploy as Docker Space

That is enough to run RAWV hosted without your laptop being on.
