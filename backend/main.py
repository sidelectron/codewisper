"""FastAPI application entry point for CodeWhisper backend (ADK-based)."""

import asyncio
import json
import logging
import os
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from codewhisper import root_agent
from codewhisper.tools import set_session_context
from services.extension_bridge import extension_bridge
from audio_handler import encode_audio_for_client, validate_audio_chunk
from frame_handler import validate_frame, resize_frame

# ADK imports
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

# Ensure ADK can see the API key (it reads GOOGLE_API_KEY; fallback from GEMINI_API_KEY or config)
if not os.environ.get("GOOGLE_API_KEY"):
    key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "gemini_api_key", "") or ""
    if key:
        os.environ["GOOGLE_API_KEY"] = key

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("codewhisper")

APP_NAME = "codewhisper"

# Phase 1: Application initialization (once at startup)
session_service = InMemorySessionService()
runner = Runner(
    app_name=APP_NAME,
    agent=root_agent,
    session_service=session_service,
)

logger.info(
    "CodeWhisper backend (ADK) starting: GOOGLE_API_KEY set=%s, model=%s",
    bool(os.environ.get("GOOGLE_API_KEY")),
    settings.agent_model,
)

app = FastAPI(
    title="CodeWhisper",
    description="Real-time AI coding companion",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint. Optionally include extension/click status."""
    from services.click_client import ClickClient
    click_available = False
    try:
        client = ClickClient()
        click_available = await client.check_available()
    except Exception:
        pass
    return {
        "status": "healthy",
        "service": "codewhisper-backend",
        "agent_model": settings.agent_model,
        "extension_connected": extension_bridge.is_connected,
        "click_agent_available": click_available,
    }


@app.websocket(settings.extension_ws_path)
async def websocket_extension(websocket: WebSocket) -> None:
    """WebSocket for VS Code extension. Register with extension_bridge on connect."""
    await websocket.accept()
    extension_bridge.set_connection(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            extension_bridge.handle_message(msg)
    except WebSocketDisconnect:
        pass
    finally:
        extension_bridge.clear_connection()


def _build_run_config() -> RunConfig:
    """Build RunConfig with AUDIO, transcription, BIDI as per plan."""
    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(),
    )


async def _downstream_task(
    websocket: WebSocket,
    user_id: str,
    session_id: str,
    queue: LiveRequestQueue,
    run_config: RunConfig,
    end_session_requested: asyncio.Event,
    summary_sent: asyncio.Event,
) -> None:
    """Consume run_live() events and send translated messages to the frontend."""
    try:
        async for event in runner.run_live(
            user_id=user_id,
            session_id=session_id,
            live_request_queue=queue,
            run_config=run_config,
        ):
            # Audio: encode and send { type: "audio", data }
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.inline_data and part.inline_data.data:
                        b64 = encode_audio_for_client(part.inline_data.data)
                        await websocket.send_json({"type": "audio", "data": b64})

            # Output transcription (model speech-to-text) — use for summary when end_session
            if event.output_transcription:
                raw = event.output_transcription
                text = raw if isinstance(raw, str) else getattr(raw, "text", None) or str(raw)
                if not text:
                    text = ""
                if end_session_requested.is_set() and not summary_sent.is_set():
                    await websocket.send_json({"type": "summary", "text": text})
                    summary_sent.set()
                    await websocket.send_json({"type": "status", "status": "session_ended"})
                    queue.close()
                    return
                await websocket.send_json({"type": "text", "text": text})

            # Turn complete -> gemini_listening (frontend contract)
            if getattr(event, "turn_complete", False):
                await websocket.send_json({"type": "status", "status": "gemini_listening"})

            # Interrupted
            if getattr(event, "interrupted", False):
                await websocket.send_json({"type": "status", "status": "interrupted"})

            # Error
            if getattr(event, "error_message", None):
                await websocket.send_json({"type": "error", "message": event.error_message})
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception("Downstream task error: %s", e)
        try:
            err_msg = str(e)
            if "1008" in err_msg or "not implemented" in err_msg.lower() or "not supported" in err_msg.lower():
                err_msg = "Session ended unexpectedly (known Gemini Live API issue with tool use). Please try again."
            await websocket.send_json({"type": "error", "message": err_msg})
        except Exception:
            pass


@app.websocket("/ws/session")
async def websocket_session(websocket: WebSocket) -> None:
    """Main WebSocket endpoint for CodeWhisper sessions. ADK lifecycle + translation layer."""
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    try:
        await websocket.send_json({"type": "status", "status": "connected"})
    except Exception:
        return

    user_id = "default"
    session_id = str(uuid.uuid4())
    queue: LiveRequestQueue | None = None
    run_config: RunConfig | None = None
    downstream_task: asyncio.Task | None = None
    end_session_requested = asyncio.Event()
    summary_sent = asyncio.Event()
    session_started = False

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type", "unknown")

            if msg_type == "control":
                action = message.get("action")
                if action == "start_session":
                    logger.info("Session start requested")
                    await websocket.send_json({"type": "status", "status": "session_starting"})

                    screen_width = message.get("screen_width")
                    screen_height = message.get("screen_height")
                    if screen_width is not None:
                        screen_width = int(screen_width)
                    if screen_height is not None:
                        screen_height = int(screen_height)
                    set_session_context(screen_width=screen_width, screen_height=screen_height)

                    # Get or create ADK session
                    session = await session_service.get_session(
                        app_name=APP_NAME,
                        user_id=user_id,
                        session_id=session_id,
                    )
                    if not session:
                        await session_service.create_session(
                            app_name=APP_NAME,
                            user_id=user_id,
                            session_id=session_id,
                        )

                    run_config = _build_run_config()
                    queue = LiveRequestQueue()
                    session_started = True

                    downstream_task = asyncio.create_task(
                        _downstream_task(
                            websocket,
                            user_id,
                            session_id,
                            queue,
                            run_config,
                            end_session_requested,
                            summary_sent,
                        )
                    )
                    await websocket.send_json({"type": "status", "status": "gemini_connected"})

                elif action == "end_session":
                    logger.info("Session end requested")
                    if queue and session_started:
                        end_session_requested.set()
                        # Trigger summarizer
                        content = types.Content(
                            parts=[types.Part(text="The user has clicked End Session. Deliver the session summary now.")]
                        )
                        queue.send_content(content)
                        # Wait briefly for summary to be sent, then close queue if no summary
                        await asyncio.sleep(2.0)
                        if not summary_sent.is_set():
                            await websocket.send_json({"type": "status", "status": "session_ended"})
                            queue.close()
                    break

                elif action == "switch_mode":
                    mode = message.get("mode")
                    if mode and mode in ("sportscaster", "catchup", "review"):
                        await websocket.send_json({"type": "mode", "mode": mode})

            elif msg_type == "audio" and queue and session_started:
                raw = message.get("data", "")
                try:
                    pcm = validate_audio_chunk(raw)
                    blob = types.Blob(mime_type="audio/pcm;rate=16000", data=pcm)
                    queue.send_realtime(blob)
                except ValueError as e:
                    logger.debug("Invalid audio chunk: %s", e)

            elif msg_type == "frame" and queue and session_started:
                raw = message.get("data", "")
                validated = validate_frame(raw)
                if validated:
                    resized = resize_frame(validated, target_size=settings.frame_size)
                    blob = types.Blob(mime_type="image/jpeg", data=resized)
                    queue.send_realtime(blob)

            elif msg_type == "text" and queue and session_started:
                text = message.get("text", "")
                if text:
                    content = types.Content(parts=[types.Part(text=text)])
                    queue.send_content(content)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected by client")
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON received: %s", e)
        try:
            await websocket.send_json({"type": "error", "message": "Invalid message format"})
        except Exception:
            pass
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if queue:
            try:
                queue.close()
            except Exception:
                pass
        if downstream_task and not downstream_task.done():
            downstream_task.cancel()
            try:
                await downstream_task
            except asyncio.CancelledError:
                pass
        logger.info("WebSocket connection closed")


# Serve React static files in production
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
