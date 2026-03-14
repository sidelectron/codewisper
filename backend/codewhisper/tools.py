"""Tool functions for ADK agents. Session context (screen dimensions) is set by main.py."""

from __future__ import annotations

from typing import Any

from config import settings
from services.click_client import ClickClient
from services.extension_bridge import extension_bridge
from utils.coordinates import map_coordinates

# Session-scoped context set by main.py when session starts (screen_width, screen_height).
_session_context: dict[str, Any] = {"screen_width": 1920, "screen_height": 1080}

# Shared click client instance (uses settings.click_agent_url).
_click_client = ClickClient()


def set_session_context(screen_width: int | None = None, screen_height: int | None = None) -> None:
    """Set screen dimensions for click/scroll coordinate mapping. Called by main.py on start_session."""
    if screen_width is not None:
        _session_context["screen_width"] = screen_width
    if screen_height is not None:
        _session_context["screen_height"] = screen_height


# ---- Extension tools ----

async def get_file_contents(path: str) -> str:
    """Read the contents of a file in the project. Provide the file path relative to the project root."""
    return await extension_bridge.send_command("get_file", {"path": path})


async def list_project_files() -> str:
    """Get the project file tree showing all files and folders."""
    return await extension_bridge.send_command("list_files", {})


async def open_file(path: str) -> str:
    """Open a file in the user's IDE editor. More reliable than clicking — always prefer this for file navigation."""
    return await extension_bridge.send_command("open_file", {"path": path})


async def get_git_diff() -> str:
    """Get the current uncommitted git changes. Shows all modifications since the last commit."""
    return await extension_bridge.send_command("get_git_diff", {})


# ---- Click agent tools ----

async def click_screen(x: int, y: int, double: bool = False) -> str:
    """Click at a position on the user's screen. Coordinates are based on the screen image you see. Aim for the center of the target element."""
    if not await _click_client.check_available():
        return "Click agent not available. Cannot interact with the screen."
    w = _session_context.get("screen_width", 1920)
    h = _session_context.get("screen_height", 1080)
    rx, ry = map_coordinates(x, y, w, h)
    ok = await _click_client.click(rx, ry, double=double)
    return "Clicked successfully." if ok else "Click agent not available. Cannot interact with the screen."


async def scroll_screen(x: int, y: int, amount: int) -> str:
    """Scroll at a position on screen. Negative amount scrolls down, positive scrolls up. Each unit is roughly 3 lines."""
    if not await _click_client.check_available():
        return "Click agent not available. Cannot interact with the screen."
    w = _session_context.get("screen_width", 1920)
    h = _session_context.get("screen_height", 1080)
    rx, ry = map_coordinates(x, y, w, h)
    ok = await _click_client.scroll(rx, ry, amount)
    return "Scrolled." if ok else "Click agent not available. Cannot interact with the screen."


async def press_keys(keys: list[str]) -> str:
    """Press a keyboard shortcut. Use 'ctrl' for modifier — system auto-translates to Cmd on Mac. Example: ['ctrl', 'p'] opens file picker."""
    if not await _click_client.check_available():
        return "Click agent not available. Cannot interact with the screen."
    ok = await _click_client.hotkey(keys)
    return "Keys pressed." if ok else "Click agent not available. Cannot interact with the screen."


async def type_text(text: str) -> str:
    """Type text into the currently focused input. Use after opening file picker with press_keys."""
    if not await _click_client.check_available():
        return "Click agent not available. Cannot interact with the screen."
    ok = await _click_client.type_text(text)
    return "Typed." if ok else "Click agent not available. Cannot interact with the screen."


# ---- Session tool ----

async def get_session_info() -> str:
    """Return current session state: duration, files reviewed, mode, alerts count."""
    # Placeholder: ADK/session may expose this later. Return a minimal status.
    return "Session active. Use Flow Modes: Sportscaster (default), Catch-Up (say 'go quiet'), Review (say 'just watch'). Say 'wrap up' for session summary."
