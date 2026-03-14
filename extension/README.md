# CodeWhisper

Connects your IDE to the CodeWhisper backend for real-time code understanding. Zero UI — runs in the background and shows connection status in the status bar.

## Install

1. Build: `cd extension && npm install && npx tsc && npx vsce package`
2. Install the `.vsix`: `code --install-extension codewhisper-0.1.0.vsix` (or `cursor --install-extension codewhisper-0.1.0.vsix`)

## Requirements

- CodeWhisper backend running at `ws://localhost:8000/ws/extension`
- Open a workspace folder; the extension connects on startup and retries every 5s if the backend is unavailable.
