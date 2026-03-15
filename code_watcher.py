#!/usr/bin/env python3
"""
Universal Code Watcher for CodeWhisper.
Monitors a project directory with watchdog, connects to the backend WebSocket,
sends file changes and responds to open_file, get_file, list_files, get_git_diff.
Works with any editor (cursor, code, windsurf, vim, etc.).
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import websockets
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent, FileMovedEvent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_WS_URL = "ws://localhost:8000/ws/extension"
RETRY_SEC = 5
DEBOUNCE_SEC = 0.5
MAX_FILE_BYTES = 100 * 1024

EXCLUDED_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".next",
    ".venv", "venv", "env", ".cache", "coverage", ".nyc_output", ".idea", ".vscode",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pyc", ".pyo", ".class", ".o", ".so", ".dll", ".exe",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".sqlite", ".db",
}

EDITOR_AUTODETECT_ORDER = ["cursor", "code", "windsurf", "subl"]


def log_ts(msg: str) -> None:
    """Log message with [HH:MM:SS] prefix."""
    t = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{t}] {msg}", flush=True)


def normalize_ws_url(url: str, path: str) -> str:
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


# ---------------------------------------------------------------------------
# Helpers: path and exclusions
# ---------------------------------------------------------------------------
def get_relative_path(root: str, path: str) -> str:
    root = os.path.normpath(root)
    path = os.path.normpath(path)
    if path == root:
        return ""
    if path.startswith(root + os.sep):
        return path[len(root) + 1 :].replace(os.sep, "/")
    return path.replace(os.sep, "/")


def is_excluded_path(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    for part in parts:
        if part in EXCLUDED_DIRS:
            return True
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in BINARY_EXTENSIONS:
        return True
    return False


def is_excluded_by_size(content: bytes) -> bool:
    return len(content) > MAX_FILE_BYTES


def build_file_list(project_root: str) -> list[str]:
    """Walk project dir and return relative file paths (excluding dirs and binary)."""
    out = []
    for dirpath, _dirnames, filenames in os.walk(project_root, topdown=True):
        rel_dir = get_relative_path(project_root, dirpath)
        if rel_dir:
            parts = rel_dir.replace("\\", "/").split("/")
            if any(p in EXCLUDED_DIRS for p in parts):
                continue
        for name in filenames:
            rel = os.path.join(rel_dir, name).replace("\\", "/") if rel_dir else name
            if is_excluded_path(rel):
                continue
            out.append(rel)
    return out


def detect_editor() -> str | None:
    for cmd in EDITOR_AUTODETECT_ORDER:
        if shutil.which(cmd):
            return cmd
    return None


# ---------------------------------------------------------------------------
# Watchdog handler: enqueue file events (debounce on_modified)
# ---------------------------------------------------------------------------
class ChangeHandler(FileSystemEventHandler):
    def __init__(self, project_root: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, debounce: dict):
        self.project_root = project_root
        self.queue = queue
        self.loop = loop
        self.debounce = debounce  # path -> threading.Timer

    def _put(self, msg: dict) -> None:
        self.loop.call_soon_threadsafe(self.queue.put_nowait, msg)

    def _rel(self, path: str) -> str:
        return get_relative_path(self.project_root, path)

    def _read_and_send_change(self, path: str) -> None:
        rel = self._rel(path)
        if is_excluded_path(rel):
            log_ts(f"SKIPPED: {rel} (excluded directory or binary)")
            return
        try:
            with open(path, "rb") as f:
                content = f.read()
        except OSError:
            return
        if is_excluded_by_size(content):
            log_ts(f"SKIPPED: {rel} ({len(content) // 1024}KB, exceeds 100KB limit)")
            return
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            return
        size_kb = len(content) / 1024
        log_ts(f"FILE_CHANGED: {rel} ({size_kb:.1f}KB)")
        self._put({"type": "file_changed", "path": rel, "content": text})

    def on_modified(self, event: FileModifiedEvent) -> None:
        if event.is_directory:
            return
        path = event.src_path
        rel = self._rel(path)
        if is_excluded_path(rel):
            return
        timer = self.debounce.get(rel)
        if timer:
            timer.cancel()
        t = threading.Timer(DEBOUNCE_SEC, self._read_and_send_change, args=(path,))
        t.daemon = True
        self.debounce[rel] = t
        t.start()

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        path = event.src_path
        rel = self._rel(path)
        if is_excluded_path(rel):
            return
        try:
            with open(path, "rb") as f:
                content = f.read()
        except OSError:
            self._put({"type": "file_created", "path": rel, "content": ""})
            return
        if is_excluded_by_size(content):
            log_ts(f"SKIPPED: {rel} ({len(content) // 1024}KB, exceeds 100KB limit)")
            return
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        size_kb = len(content) / 1024
        log_ts(f"FILE_CREATED: {rel} ({size_kb:.1f}KB)")
        self._put({"type": "file_created", "path": rel, "content": text})

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if event.is_directory:
            return
        rel = self._rel(event.src_path)
        if is_excluded_path(rel):
            return
        self._put({"type": "file_deleted", "path": rel})

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        old_rel = self._rel(event.src_path)
        new_rel = self._rel(event.dest_path)
        if is_excluded_path(old_rel) and is_excluded_path(new_rel):
            return
        self._put({"type": "file_renamed", "oldPath": old_rel, "newPath": new_rel})


# ---------------------------------------------------------------------------
# Command handlers (run in async loop)
# ---------------------------------------------------------------------------
def cmd_open_file(project_root: str, editor: str | None, path: str) -> str:
    if not editor:
        return "No editor command available. Open the file manually."
    full = os.path.join(project_root, path)
    if not os.path.isfile(full):
        return f"File not found: {path}"
    try:
        subprocess.Popen([editor, full], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"File opened in {editor}"
    except Exception as e:
        return f"Error: {e}"


def cmd_get_file(project_root: str, path: str) -> str:
    full = os.path.join(project_root, path)
    if not os.path.isfile(full):
        return "File not found"
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"


def cmd_list_files(project_root: str) -> str:
    files = build_file_list(project_root)
    return json.dumps(files)


def cmd_get_git_diff(project_root: str) -> str:
    try:
        r = subprocess.run(
            ["git", "diff"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout or r.stderr or ""
    except Exception:
        return ""


def count_git_diff_files(diff_output: str) -> int:
    return diff_output.count("diff --git")


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
def _pad(s: str, w: int = 42) -> str:
    if len(s) > w:
        return s[: w - 3] + "..."
    return s + " " * (w - len(s))


def print_banner(project_root: str, editor: str | None, backend_url: str) -> None:
    editor_str = f"{editor} (auto-detected)" if editor else "none (open_file unavailable)"
    print("+==========================================+")
    print("|  CodeWhisper Code Watcher                |")
    print(f"|  Watching: {_pad(project_root)} |")
    print(f"|  Editor: {_pad(editor_str)} |")
    print(f"|  Backend: {_pad(backend_url)} |")
    print("|                                          |")
    print("|  Press Ctrl+C to quit.                   |")
    print("+==========================================+")


# ---------------------------------------------------------------------------
# Main async loop: connect, handshake, queue sender, command receiver
# ---------------------------------------------------------------------------
async def run_watcher(project_root: str, backend_url: str, editor: str | None) -> None:
    change_queue: asyncio.Queue = asyncio.Queue()
    debounce: dict = {}
    loop = asyncio.get_event_loop()
    handler = ChangeHandler(project_root, change_queue, loop, debounce)
    observer: Observer | None = None

    def start_observer() -> None:
        nonlocal observer
        if observer is not None:
            try:
                observer.stop()
                observer.join(timeout=2)
            except Exception:
                pass
        observer = Observer()
        observer.schedule(handler, project_root, recursive=True)
        observer.start()

    def stop_observer() -> None:
        nonlocal observer
        if observer is not None:
            try:
                observer.stop()
                observer.join(timeout=2)
            except Exception:
                pass
            observer = None

    while True:
        try:
            async with websockets.connect(backend_url, ping_interval=20, ping_timeout=10) as ws:
                log_ts("CONNECTED to backend")
                files = build_file_list(project_root)
                handshake = {"type": "handshake", "workspace": os.path.abspath(project_root), "files": files}
                await ws.send(json.dumps(handshake))
                log_ts(f"HANDSHAKE sent ({len(files)} files)")
                start_observer()

                async def send_from_queue() -> None:
                    while True:
                        msg = await change_queue.get()
                        await ws.send(json.dumps(msg))

                async def receive_commands() -> None:
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if data.get("type") != "command":
                            continue
                        req_id = data.get("requestId")
                        cmd = data.get("command", "")
                        params = data.get("params") or {}
                        path = params.get("path", "")

                        if cmd == "open_file":
                            result = cmd_open_file(project_root, editor, path)
                            log_ts(f"COMMAND: open_file {path} → opened in {editor}" if editor else f"COMMAND: open_file {path} → {result}")
                            await ws.send(json.dumps({"requestId": req_id, "data": result}))
                        elif cmd == "get_file":
                            result = cmd_get_file(project_root, path)
                            log_ts(f"COMMAND: get_file {path} → {'ok' if result != 'File not found' else 'not found'}")
                            await ws.send(json.dumps({"requestId": req_id, "data": result}))
                        elif cmd == "list_files":
                            result = cmd_list_files(project_root)
                            n = len(json.loads(result)) if result else 0
                            log_ts(f"COMMAND: list_files → {n} files")
                            await ws.send(json.dumps({"requestId": req_id, "data": result}))
                        elif cmd == "get_git_diff":
                            result = cmd_get_git_diff(project_root)
                            n = count_git_diff_files(result)
                            if n:
                                log_ts(f"COMMAND: get_git_diff → {n} files changed")
                            else:
                                log_ts("COMMAND: get_git_diff → no diff" if not result.strip() else "COMMAND: get_git_diff → (output)")
                            await ws.send(json.dumps({"requestId": req_id, "data": result}))
                        else:
                            await ws.send(json.dumps({"requestId": req_id, "data": f"Unknown command: {cmd}"}))

                send_task = asyncio.create_task(send_from_queue())
                recv_task = asyncio.create_task(receive_commands())
                try:
                    await asyncio.gather(send_task, recv_task)
                except (websockets.ConnectionClosed, asyncio.CancelledError):
                    pass
                finally:
                    send_task.cancel()
                    recv_task.cancel()
                    try:
                        await send_task
                    except asyncio.CancelledError:
                        pass
                    try:
                        await recv_task
                    except asyncio.CancelledError:
                        pass
        except (OSError, websockets.InvalidStatusCode, websockets.InvalidState) as e:
            log_ts(f"Backend not available ({e}), retrying in {RETRY_SEC}s...")
        except websockets.ConnectionClosed:
            log_ts("Backend disconnected. Retrying in 5s...")
        except Exception as e:
            log_ts(f"Error: {e}. Retrying in {RETRY_SEC}s...")
        stop_observer()
        await asyncio.sleep(RETRY_SEC)


def main() -> int:
    parser = argparse.ArgumentParser(description="CodeWhisper Code Watcher — monitor project and connect to backend.")
    parser.add_argument("project_path", help="Path to the project directory to watch")
    parser.add_argument("--backend-url", default=None, help=f"WebSocket URL (default: {DEFAULT_WS_URL})")
    parser.add_argument("--port", type=int, default=None, help="Port for backend (builds ws://localhost:PORT/ws/extension if --backend-url not set)")
    parser.add_argument("--editor", default=None, help="Editor command (cursor, code, windsurf, vim, emacs, subl, etc.). Default: auto-detect.")
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_path)
    if not os.path.isdir(project_root):
        print(f"Error: not a directory: {project_root}", file=sys.stderr)
        return 1

    if args.backend_url:
        backend_url = normalize_ws_url(args.backend_url, "/ws/extension")
    elif args.port is not None:
        backend_url = f"ws://localhost:{args.port}/ws/extension"
    else:
        backend_url = DEFAULT_WS_URL

    editor = args.editor if args.editor else detect_editor()
    if not editor and not args.editor:
        log_ts("Warning: no editor (cursor, code, windsurf, subl) found in PATH. open_file will be unavailable.")

    print_banner(project_root, editor, backend_url)

    try:
        asyncio.run(run_watcher(project_root, backend_url, editor))
    except KeyboardInterrupt:
        log_ts("Quit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
