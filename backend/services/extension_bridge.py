"""Singleton WebSocket bridge to the VS Code extension. Tools call this for file/editor commands."""

import asyncio
import logging
import uuid
from typing import Any

from google.genai import types

logger = logging.getLogger(__name__)

EXTENSION_TOOL_NAMES = [
    "get_file_contents",
    "list_project_files",
    "open_file",
    "get_git_diff",
]


class ExtensionBridge:
    """Manages the extension WebSocket connection. Singleton instance."""

    def __init__(self) -> None:
        self._websocket: Any = None
        self._pending: dict[str, asyncio.Future[str]] = {}
        self._session_queue: Any = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """True if extension WebSocket is connected."""
        return self._websocket is not None

    def set_connection(self, websocket: Any) -> None:
        """Store the extension WebSocket when it connects."""
        self._websocket = websocket
        logger.info("Extension bridge: connection set")

    def clear_connection(self) -> None:
        """Clear the reference when extension disconnects."""
        self._websocket = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("Extension disconnected"))
        self._pending.clear()
        self._session_queue = None
        logger.info("Extension bridge: connection cleared")

    def register_session_queue(self, queue: Any) -> None:
        """Register the active LiveRequestQueue for injecting file updates (optional)."""
        self._session_queue = queue

    def unregister_session_queue(self) -> None:
        """Unregister when session ends."""
        self._session_queue = None

    async def send_command(self, type: str, params: dict[str, Any]) -> str:
        """Send a command to the extension and await the response. Timeout 5s."""
        if self._websocket is None:
            return "Extension not connected. Cannot access files directly."
        request_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._pending[request_id] = fut
        try:
            await self._websocket.send_json({
                "type": "command",
                "requestId": request_id,
                "command": type,
                "params": params,
            })
            return await asyncio.wait_for(fut, timeout=5.0)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            return "Extension command timed out."
        except Exception as e:
            self._pending.pop(request_id, None)
            logger.warning("Extension send_command failed: %s", e)
            return f"Extension error: {e}"
        finally:
            self._pending.pop(request_id, None)

    def handle_message(self, message: dict[str, Any]) -> None:
        """Process incoming message from extension. Resolve pending Future or inject file context."""
        request_id = message.get("requestId")
        if request_id and request_id in self._pending:
            fut = self._pending[request_id]
            if not fut.done():
                data = message.get("data") or message.get("result") or message.get("text") or message.get("content", "")
                if isinstance(data, dict):
                    data = data.get("content", data.get("text", str(data)))
                fut.set_result(str(data) if data is not None else "")
            return
        # File change event: inject into session if queue registered
        if self._session_queue and message.get("type") in ("file_changed", "file_created"):
            path = message.get("path", "")
            content = message.get("content", "")
            if content:
                try:
                    truncated = content[:8000]
                    suffix = f"\n... (truncated, {len(content)} chars total)" if len(content) > 8000 else ""
                    event = "Created" if message["type"] == "file_created" else "Changed"
                    text = f"[Code Watcher — File {event}: {path}]\n```\n{truncated}{suffix}\n```"
                    ctx = types.Content(parts=[types.Part(text=text)])
                    self._session_queue.send_content(ctx)
                    logger.info("Injected file update: %s (%d chars)", path, len(content))
                except Exception as e:
                    logger.warning("Failed to inject file update: %s", e)

    def get_available_tools(self) -> list[str]:
        """Return list of tool names the extension supports when connected."""
        if not self.is_connected:
            return []
        return list(EXTENSION_TOOL_NAMES)


extension_bridge = ExtensionBridge()
