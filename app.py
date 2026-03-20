# core
from groq import Groq

# other dauflt library imports
import asyncio
import io
import os
import re
import wave
from typing import Optional

# specfics 
import chainlit as cl
import edge_tts
from chainlit.input_widget import Switch
from langchain_groq import ChatGroq
from rawv.research import ResearchEngine
from rawv.research.models import ResearchMode


WHISPER_MODEL = os.getenv("RAWV_WHISPER_MODEL", "whisper-large-v3-turbo")
TTS_VOICE = os.getenv("RAWV_TTS_VOICE", "en-US-AriaNeural")
TTS_RATE = os.getenv("RAWV_TTS_RATE", "+5%")
GROQ_CHAT_MODEL = os.getenv("RAWV_CHAT_MODEL", "llama-3.1-8b-instant")


# sometimes mime types are missing or unreliable, so guess a filename extension
def _guess_audio_filename(mime_type: Optional[str]) -> str:
    if not mime_type:
        return "audio.wav"
    mime = mime_type.lower()
    if "webm" in mime:
        return "audio.webm"
    if "ogg" in mime:
        return "audio.ogg"
    if "opus" in mime:
        return "audio.ogg"
    if "mpeg" in mime or "mp3" in mime:
        return "audio.mp3"
    if "wav" in mime:
        return "audio.wav"
    if "m4a" in mime:
        return "audio.m4a"
    if "mp4" in mime:
        return "audio.mp4"
    # Groq rejects unknown extensions, so always guess a supported one at all costs.
    return "audio.wav"


def _sniff_container_extension(audio_bytes: bytes) -> Optional[str]:
    # Minimal magic-byte sniffing to choose an extension Groq accepts.
    if audio_bytes.startswith(b"RIFF") and audio_bytes[8:12] == b"WAVE":
        return "wav"
    if audio_bytes.startswith(b"OggS"):
        return "ogg"
    if audio_bytes.startswith(b"ID3"):
        return "mp3"
    if audio_bytes[:4] == b"fLaC":
        return "flac"
    if len(audio_bytes) >= 12 and audio_bytes[4:8] == b"ftyp":
        # mp4 container (m4a is also mp4 container but different branding)
        return "mp4"
    if audio_bytes[:4] == b"\x1A\x45\xDF\xA3":
        return "webm"
    return None


def _wrap_raw_pcm_as_wav(
    audio_bytes: bytes, *, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2
) -> bytes:
    # If the browser sends raw PCM frames, Groq needs a WAV container.
    # Ensure frames align.
    frame_size = channels * sample_width
    if frame_size > 0 and len(audio_bytes) % frame_size != 0:
        audio_bytes = audio_bytes[: len(audio_bytes) - (len(audio_bytes) % frame_size)]

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_bytes)
    return buf.getvalue()


# Because Chainlit is unrelaible about mime types.
def _normalize_audio_for_groq(audio_bytes: bytes, mime_type: Optional[str]) -> tuple[str, bytes, str]:
    # Chainlit can provide raw PCM frames (e.g. mime_type == "pcm16").
    # Groq requires an actual media container, so wrap raw PCM as WAV.
    if mime_type and "pcm" in mime_type.lower():
        sample_rate = int(os.getenv("RAWV_AUDIO_SAMPLE_RATE", "24000"))
        wav_bytes = _wrap_raw_pcm_as_wav(audio_bytes, sample_rate=sample_rate)
        return "audio.wav", wav_bytes, "wav"

    # Prefer sniffing the bytes over relying on mime_type.
    # Sniffing - examining.
    sniffed = _sniff_container_extension(audio_bytes)
    if sniffed in {"wav", "mp3", "mp4", "m4a", "ogg", "opus", "webm", "flac"}:
        ext = "ogg" if sniffed == "opus" else sniffed
        return f"audio.{ext}", audio_bytes, ext

    # If mime type hints at a known container, use it.
    guessed_name = _guess_audio_filename(mime_type)
    guessed_ext = guessed_name.rsplit(".", 1)[-1].lower()
    if guessed_ext in {"wav", "mp3", "mp4", "m4a", "ogg", "webm", "flac"}:
        return guessed_name, audio_bytes, guessed_ext

    # Last resort: treat as raw PCM and wrap into WAV.
    sample_rate = int(os.getenv("RAWV_AUDIO_SAMPLE_RATE", "24000"))
    wav_bytes = _wrap_raw_pcm_as_wav(audio_bytes, sample_rate=sample_rate)
    return "audio.wav", wav_bytes, "wav"


def transcribe_bytes(audio_bytes: bytes, mime_type: Optional[str] = None) -> tuple[str, str]:
    api_key = os.getenv("GROQ_API_KEY")
    client = Groq(api_key=api_key)

    filename, normalized_bytes, ext = _normalize_audio_for_groq(audio_bytes, mime_type)
    transcription = client.audio.transcriptions.create(
        file=(filename, normalized_bytes),
        model=WHISPER_MODEL,
        response_format="text",
    )
    transcript_text = str(transcription)
    debug = (
        f"file={filename} ext={ext} in_bytes={len(audio_bytes)} out_bytes={len(normalized_bytes)} "
        f"mime_type={(mime_type or '(unknown)')}"
    )
    return transcript_text, debug


async def synthesize_mp3_bytes(text: str) -> bytes:
    communicate = edge_tts.Communicate(text=text, voice=TTS_VOICE, rate=TTS_RATE)
    audio = bytearray()
    async for chunk in communicate.stream():
        data = chunk.get("data")
        if chunk.get("type") == "audio" and isinstance(data, (bytes, bytearray)):
            audio.extend(data)
    return bytes(audio)


def _parse_mode_and_query(text: str) -> tuple[ResearchMode, str]:
    lowered = text.strip().lower()
    if lowered.startswith("quick research on "):
        return "quick", text[len("quick research on ") :].strip()
    if lowered.startswith("deep research on "):
        return "deep", text[len("deep research on ") :].strip()
    if lowered.startswith("normal research on "):
        return "normal", text[len("normal research on ") :].strip()
    default_mode = os.getenv("RAWV_RESEARCH_DEFAULT_MODE", "normal").strip().lower()
    if default_mode == "quick":
        return "quick", text
    if default_mode == "deep":
        return "deep", text
    if default_mode == "normal":
        return "normal", text
    return "normal", text


def _render_sources(sources) -> str:
    if not sources:
        return "Sources: none (fallback response)"
    lines = ["Sources:"]
    for i, source in enumerate(sources, start=1):
        lines.append(f"[{i}] {source.title} - {source.url}")
    return "\n".join(lines)


def _is_smalltalk(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    smalltalk_patterns = [
        r"^hi$",
        r"^hello$",
        r"^hey$",
        r"^yo$",
        r"^sup$",
        r"^how are you( doing)?\??$",
        r"^what'?s up\??$",
        r"^good (morning|afternoon|evening)$",
        r"^thanks!?$",
        r"^thank you!?$",
    ]
    return any(re.match(pattern, normalized) for pattern in smalltalk_patterns)


def _needs_research(text: str, force_research: bool) -> bool:
    if not text.strip():
        return False

    lower = text.lower().strip()
    explicit_research_request = (
        lower.startswith("quick research on ")
        or lower.startswith("normal research on ")
        or lower.startswith("deep research on ")
        or "research" in lower
        or "look up" in lower
        or "find sources" in lower
    )
    if explicit_research_request:
        return True

    if _is_smalltalk(text):
        return False

    research_signal_words = [
        "latest",
        "today",
        "news",
        "trend",
        "compare",
        "analysis",
        "cite",
        "evidence",
        "source",
        "what is",
        "who is",
        "when did",
        "why does",
        "how to",
    ]
    has_research_signal = any(word in lower for word in research_signal_words)
    looks_like_question = "?" in lower or len(lower.split()) >= 8

    if force_research and not _is_smalltalk(text):
        return True

    return has_research_signal and looks_like_question


def _build_voice_reply(answer: str) -> str:
    clean = " ".join(answer.split())
    if len(clean) <= 280:
        return clean
    return clean[:277] + "..."


async def _run_chat_reply(chat_model: ChatGroq, user_text: str) -> str:
    def _invoke() -> str:
        system = (
            "You are RAWV, a friendly voice-first assistant. "
            "For casual chat, keep it brief and natural (1-2 sentences)."
        )
        response = chat_model.invoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ]
        )
        content = response.content
        if isinstance(content, str):
            return content.strip()
        return str(content).strip()

    return await asyncio.to_thread(_invoke)


async def _respond_with_voice(engine: ResearchEngine, chat_model: ChatGroq, user_text: str) -> None:
    mode, query = _parse_mode_and_query(user_text)
    if not query:
        await cl.Message(content="Please ask a question after the mode command.").send()
        return

    force_research = bool(cl.user_session.get("force_research"))
    use_research = _needs_research(query, force_research)

    if not use_research:
        reply = await _run_chat_reply(chat_model, query)
        await cl.Message(content=reply).send()
        try:
            audio_bytes = await synthesize_mp3_bytes(_build_voice_reply(reply))
            await cl.Message(
                content="",
                elements=[
                    cl.Audio(
                        content=audio_bytes,
                        name="reply.mp3",
                        display="inline",
                        auto_play=True,
                    )
                ],
            ).send()
        except Exception as e:
            await cl.Message(content=f"(TTS skipped) {e}").send()
        return

    result = await asyncio.to_thread(engine.run, query, mode)

    for step in result.steps:
        with cl.Step(type="tool", name=step.name) as ui_step:
            ui_step.output = step.output

    final_text = f"{result.answer}\n\n{_render_sources(result.sources)}"
    msg = cl.Message(content=final_text)
    await msg.send()

    try:
        audio_bytes = await synthesize_mp3_bytes(result.spoken_summary)
        await cl.Message(
            content="",
            elements=[
                cl.Audio(
                    content=audio_bytes,
                    name="reply.mp3",
                    display="inline",
                    auto_play=True,
                )
            ],
        ).send()
    except Exception as e:
        await cl.Message(content=f"(TTS skipped) {e}").send()


async def _ensure_settings_ui() -> None:
    if bool(cl.user_session.get("settings_initialized")):
        return

    force_research = bool(cl.user_session.get("force_research"))
    await cl.ChatSettings(
        [
            Switch(
                id="force_research",
                label="RESEARCH MODE (FORCE ON)",
                initial=force_research,
                description="When ON, RAWV researches most non-smalltalk queries.",
            )
        ]
    ).send()
    cl.user_session.set("settings_initialized", True)


@cl.set_starters
async def set_starters(_current_user, _language):
    return [
        cl.Starter(
            label="Start Chat",
            message="start",
            icon="/public/rawv-avatar-favicon.png",
        ),
        cl.Starter(
            label="Enable Research Mode",
            message="research on",
            icon="/public/rawv-avatar-favicon.png",
        ),
        cl.Starter(
            label="Disable Research Mode",
            message="research off",
            icon="/public/rawv-avatar-favicon.png",
        ),
        cl.Starter(
            label="Quick Research Example",
            message="quick research on latest AI browser automation trends",
            icon="/public/rawv-avatar-favicon.png",
        ),
    ]


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("audio_buffer", bytearray())
    cl.user_session.set("audio_mime_type", None)
    cl.user_session.set("voice_task", None)
    cl.user_session.set("research_engine", ResearchEngine())
    cl.user_session.set("chat_model", ChatGroq(model=GROQ_CHAT_MODEL, temperature=0.3))
    cl.user_session.set("force_research", False)
    cl.user_session.set("settings_initialized", False)


@cl.on_settings_update
async def on_settings_update(settings):
    enabled = bool(settings.get("force_research", False))
    cl.user_session.set("force_research", enabled)
    status = "ON" if enabled else "OFF"
    await cl.Message(content=f"Research mode is now {status}.").send()


@cl.action_callback("research_on")
async def on_research_on(_action: cl.Action):
    cl.user_session.set("force_research", True)
    await cl.Message(content="Research mode is now ON.").send()


@cl.action_callback("research_off")
async def on_research_off(_action: cl.Action):
    cl.user_session.set("force_research", False)
    await cl.Message(content="Research mode is now OFF.").send()


@cl.on_message
async def on_message(message: cl.Message):
    engine = cl.user_session.get("research_engine")
    if engine is None:
        engine = ResearchEngine()
        cl.user_session.set("research_engine", engine)
    chat_model = cl.user_session.get("chat_model")
    if chat_model is None:
        chat_model = ChatGroq(model=GROQ_CHAT_MODEL, temperature=0.3)
        cl.user_session.set("chat_model", chat_model)

    message_text = message.content.strip()
    if message_text.lower() in {"start", "/start"}:
        await _ensure_settings_ui()
        await cl.Message(
            content=(
                "RAWV is ready. Ask anything, or say 'quick research on ...' for sourced web research. "
                "You can toggle research mode in settings anytime."
            )
        ).send()
        return

    if message_text.lower() in {"/research on", "research on"}:
        cl.user_session.set("force_research", True)
        await _ensure_settings_ui()
        await cl.Message(content="Research mode is now ON.").send()
        return
    if message_text.lower() in {"/research off", "research off"}:
        cl.user_session.set("force_research", False)
        await _ensure_settings_ui()
        await cl.Message(content="Research mode is now OFF.").send()
        return

    await _ensure_settings_ui()
    await _respond_with_voice(engine, chat_model, message.content)


# Lots of audio helpers because chainlit and groq audios are not directly compatible.
@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    audio_buffer = cl.user_session.get("audio_buffer")
    if audio_buffer is None:
        audio_buffer = bytearray()
        cl.user_session.set("audio_buffer", audio_buffer)

    audio_bytes = getattr(chunk, "data", None)
    if audio_bytes:
        audio_buffer.extend(audio_bytes)

    # Set mime type once (avoid per-chunk session writes which can slow recording UX).
    if cl.user_session.get("audio_mime_type") is None:
        mime_type = getattr(chunk, "mime_type", None) or getattr(chunk, "mimeType", None)
        cl.user_session.set("audio_mime_type", mime_type)


@cl.on_audio_start
async def on_audio_start():
    # Chainlit expects this hook to exist when audio is enabled.
    # Returning True allows the client to start streaming audio.
    audio_buffer = cl.user_session.get("audio_buffer")
    if audio_buffer is None:
        cl.user_session.set("audio_buffer", bytearray())
    else:
        audio_buffer.clear()

    cl.user_session.set("audio_mime_type", None)

    previous_task = cl.user_session.get("voice_task")
    if previous_task is not None and hasattr(previous_task, "cancel") and not previous_task.done():
        previous_task.cancel()

    return True


@cl.on_audio_end
async def on_audio_end():
    audio_buffer = cl.user_session.get("audio_buffer")
    if not audio_buffer:
        await cl.Message(content="No audio received.").send()
        return

    mime_type = cl.user_session.get("audio_mime_type")
    audio_bytes = bytes(audio_buffer)
    audio_buffer.clear()

    # Important UX detail: keep this hook fast so the UI can stop recording immediately.
    # Do the heavy work (STT + LLM + TTS) in a background task.
    previous_task = cl.user_session.get("voice_task")
    if previous_task is not None and hasattr(previous_task, "cancel") and not previous_task.done():
        previous_task.cancel()

    async def _process() -> None:
        engine = cl.user_session.get("research_engine")
        if engine is None:
            engine = ResearchEngine()
            cl.user_session.set("research_engine", engine)
        chat_model = cl.user_session.get("chat_model")
        if chat_model is None:
            chat_model = ChatGroq(model=GROQ_CHAT_MODEL, temperature=0.3)
            cl.user_session.set("chat_model", chat_model)

        with cl.Step(type="tool", name="🎙️ Transcribing") as step:
            try:
                transcript, debug = transcribe_bytes(audio_bytes, mime_type=mime_type)
                step.output = transcript
            except Exception as e:
                mt = mime_type or "(unknown)"
                step.output = (
                    f"Transcription failed: {e}\n"
                    f"mime_type={mt} bytes={len(audio_bytes)}"
                )
                await cl.Message(content=step.output).send()
                return

        # Emit debug info as a small tool step output (helps diagnose browser formats).
        with cl.Step(type="tool", name="🧾 Audio debug") as step:
            step.output = debug

        await _respond_with_voice(engine, chat_model, transcript)

    task = asyncio.create_task(_process())
    cl.user_session.set("voice_task", task)
