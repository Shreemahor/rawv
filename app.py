# core
from groq import Groq
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq

# other dauflt library imports
import asyncio
import io
import os
import wave
from typing import Optional, cast

# specfics 
import chainlit as cl
import edge_tts


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
    debug = (
        f"file={filename} ext={ext} in_bytes={len(audio_bytes)} out_bytes={len(normalized_bytes)} "
        f"mime_type={(mime_type or '(unknown)')}"
    )
    return transcription, debug


async def synthesize_mp3_bytes(text: str) -> bytes:
    communicate = edge_tts.Communicate(text=text, voice=TTS_VOICE, rate=TTS_RATE)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)


async def _respond_with_voice(runnable: Runnable, user_text: str) -> None:
    msg = cl.Message(content="")
    async for chunk in runnable.astream(
        {"question": user_text},
        config=RunnableConfig(callbacks=[cl.LangchainCallbackHandler()]),
    ):
        await msg.stream_token(chunk)

    await msg.send()

    try:
        audio_bytes = await synthesize_mp3_bytes(msg.content)
        msg.elements = [
            cl.Audio(
                content=audio_bytes,
                name="reply.mp3",
                display="inline",
                auto_play=True,
            )
        ]
        if hasattr(msg, "update"):
            await msg.update()
        else:
            await cl.Message(content="", elements=msg.elements).send()
    except Exception as e:
        await cl.Message(content=f"(TTS skipped) {e}").send()


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("audio_buffer", bytearray())
    cl.user_session.set("audio_mime_type", None)
    cl.user_session.set("voice_task", None)

    model = ChatGroq(model=GROQ_CHAT_MODEL, streaming=True)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are RAWV, a helpful voice-first assistant. Reply like a real person in a conversational tone. Keep responses short (1-2 sentences by default) and easy to speak aloud. Ask one clarifying question if needed. Avoid long lists unless the user explicitly asks for them.",
            ),
            ("human", "{question}"),
        ]
    )
    runnable = prompt | model | StrOutputParser()
    cl.user_session.set("runnable", runnable)


@cl.on_message
async def on_message(message: cl.Message):
    runnable = cast(Runnable, cl.user_session.get("runnable"))  # type: Runnable
    await _respond_with_voice(runnable, message.content)


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
        runnable = cast(Runnable, cl.user_session.get("runnable"))  # type: Runnable

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

        await _respond_with_voice(runnable, transcript)

    task = asyncio.create_task(_process())
    cl.user_session.set("voice_task", task)
