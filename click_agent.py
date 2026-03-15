#!/usr/bin/env python3
"""
CodeWhisper Click Agent — connects to backend via WebSocket.
Receives click/scroll/hotkey/type commands; executes via pyautogui.
Works with local backend OR Cloud Run.
"""

import argparse
import asyncio
import json
import logging
import sys
import time

import pyautogui
import websockets

# Failsafe: move mouse to corner to stop. Keep enabled.
pyautogui.FAILSAFE = True

# Rate limit: max 2 actions per second
MIN_INTERVAL = 0.5  # seconds between requests
_last_action_time: float = 0.0

DEFAULT_WS_URL = "ws://localhost:8000/ws/click-agent"


def _platform() -> str:
    p = sys.platform
    if p == "win32":
        return "windows"
    if p == "darwin":
        return "darwin"
    return "linux"


def _rate_limit() -> None:
    global _last_action_time
    now = time.monotonic()
    elapsed = now - _last_action_time
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_action_time = time.monotonic()


def _map_hotkey_keys(keys: list[str]) -> list[str]:
    """On macOS, map 'ctrl' to 'command' for IDE shortcuts."""
    if _platform() != "darwin":
        return keys
    return ["command" if k.lower() == "ctrl" else k for k in keys]


def log_ts(msg: str) -> None:
    """Log message with [HH:MM:SS] prefix."""
    t = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{t}] {msg}", flush=True)


def _normalize_ws_url(url: str, path: str) -> str:
    """Convert https:// to wss://, http:// to ws://, and ensure path is appended."""
    u = url.strip().rstrip("/")
    if u.startswith("https://"):
        base = "wss://" + u[8:]
    elif u.startswith("http://"):
        base = "ws://" + u[7:]
    else:
        base = u
    path = path if path.startswith("/") else "/" + path
    return base.rstrip("/") + path if not base.endswith(path) else base


async def handle_command(action: str, params: dict) -> dict:
    """Execute a command and return the result dict."""
    _rate_limit()

    if action == "health":
        return {"status": "ok", "platform": _platform()}

    if action == "click":
        x, y = params["x"], params["y"]
        pyautogui.click(x, y)
        logging.info("CLICK at (%s, %s)", x, y)
        return {"status": "clicked", "x": x, "y": y}

    if action == "double_click":
        x, y = params["x"], params["y"]
        pyautogui.doubleClick(x, y)
        logging.info("DOUBLE_CLICK at (%s, %s)", x, y)
        return {"status": "double_clicked", "x": x, "y": y}

    if action == "scroll":
        x, y, clicks = params["x"], params["y"], params["clicks"]
        pyautogui.moveTo(x, y)
        pyautogui.scroll(clicks)
        logging.info("SCROLL at (%s, %s) by %s", x, y, clicks)
        return {"status": "scrolled", "clicks": clicks}

    if action == "hotkey":
        keys = _map_hotkey_keys(params["keys"])
        pyautogui.hotkey(*keys)
        logging.info("HOTKEY %s", "+".join(keys))
        return {"status": "pressed", "keys": params["keys"]}

    if action == "type_text":
        text = params["text"]
        try:
            pyautogui.typewrite(text, interval=0.02)
        except Exception:
            pyautogui.write(text)
        logging.info("TYPED %s", repr(text[:50] + ("..." if len(text) > 50 else "")))
        return {"status": "typed", "text": text}

    return {"status": "error", "message": f"Unknown action: {action}"}


async def run_click_agent(backend_url: str) -> None:
    """Connect to backend WebSocket and process commands."""
    while True:
        try:
            async with websockets.connect(
                backend_url, ping_interval=20, ping_timeout=10
            ) as ws:
                log_ts(f"CONNECTED to backend at {backend_url}")

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    if msg.get("type") != "command":
                        continue

                    request_id = msg.get("requestId")
                    action = msg.get("action", "")
                    params = msg.get("params") or {}

                    try:
                        result = await handle_command(action, params)
                    except Exception as e:
                        result = {"status": "error", "message": str(e)}
                        logging.error("Command %s failed: %s", action, e)

                    response = {"requestId": request_id, **result}
                    await ws.send(json.dumps(response))

        except (OSError, websockets.InvalidStatusCode, websockets.ConnectionClosed) as e:
            log_ts(f"Backend not available ({e}), retrying in 5s...")
        except Exception as e:
            log_ts(f"Error: {e}. Retrying in 5s...")

        await asyncio.sleep(5)


def _print_banner(backend_url: str) -> None:
    """Print startup banner showing backend URL and safety info."""
    plat = _platform()
    plat_label = {"windows": "Windows", "darwin": "macOS", "linux": "Linux"}.get(
        plat, plat
    )
    # Truncate long URLs for display (34-char width to match banner)
    url_display = backend_url[:31] + "..." if len(backend_url) > 34 else backend_url
    print(
        f"""
+==========================================+
|  CodeWhisper Click Agent                 |
|  Running on: {plat_label:<26} |
|  Backend:  {url_display:<34} |
|                                          |
|  SAFETY: Move mouse to any screen        |
|  corner to emergency stop.               |
|  Press Ctrl+C to quit.                   |
+==========================================+
"""
    )
    if plat == "windows":
        print("Click Agent running on Windows. No additional setup needed.")
    elif plat == "darwin":
        print(
            "Click Agent running on macOS. Grant Accessibility permissions: "
            "System Preferences → Privacy & Security → Accessibility → enable Terminal/Python."
        )
    else:
        print(
            "Click Agent running on Linux (X11). Install xdotool: sudo apt install xdotool"
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="CodeWhisper Click Agent")
    parser.add_argument(
        "--backend-url",
        default=None,
        help=f"WebSocket URL for the backend (default: {DEFAULT_WS_URL})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for local backend (builds ws://localhost:PORT/ws/click-agent)",
    )
    args = parser.parse_args()

    if args.backend_url:
        backend_url = _normalize_ws_url(args.backend_url, "/ws/click-agent")
    elif args.port:
        backend_url = f"ws://localhost:{args.port}/ws/click-agent"
    else:
        backend_url = DEFAULT_WS_URL

    _print_banner(backend_url)

    try:
        asyncio.run(run_click_agent(backend_url))
    except KeyboardInterrupt:
        log_ts("Quit.")


if __name__ == "__main__":
    main()
