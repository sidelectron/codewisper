# CodeWhisper

**Vibe code without losing the mental model.**

CodeWhisper is a real-time AI coding companion that watches your IDE screen and explains AI-generated code through voice. Built with Google's Agent Development Kit (ADK) and the Gemini Live API as a multi-agent system with specialized agents for code review, security scanning, IDE navigation, and session summarization.

![Architecture](docs/architecture.svg)

---

## The Problem

Vibe coding has exploded. Developers accept AI-generated code without understanding it. 45% say debugging AI code takes longer than expected. AI-generated code has 1.7x more bugs and 2.74x more security vulnerabilities. Real startups have shut down because founders couldn't debug their vibe-coded apps.

---

## The Solution

CodeWhisper watches your screen and explains code through real-time voice conversation. Built as a multi-agent system:

- **Voice conversation with interruption** — talk naturally, ask questions anytime
- **Three Flow Modes** — Sportscaster (continuous narration), Catch-Up (on-demand summary), Review (full debrief)
- **Danger Zone Alerts** — proactive security scanning, flags hardcoded keys and injection risks
- **IDE Navigation** — opens and reads files as your AI tool edits them
- **Adaptive Depth** — "explain like I'm new to React"
- **Session Summary** — spoken and text recap with everything covered
- **Works with any editor** — VS Code, Cursor, Windsurf, Vim, anything

---

## Agent Architecture

The system uses 5 ADK agents:

| Agent | Role |
|-------|------|
| **Root Agent (Orchestrator)** | Manages voice conversation, Flow Modes, delegates to specialists |
| **Code Review Agent** | Explains code, tracks file relationships, adapts explanation depth |
| **Security Agent** | Scans for vulnerabilities, fires Danger Zone alerts |
| **Navigator Agent** | Opens files, scrolls through code, interacts with IDE |
| **Summary Agent** | Generates end-of-session recaps |

![Architecture](docs/architecture.svg)

---

## Live Demo

**Try it live:** [https://codewhisper-xxxxx-uc.a.run.app](https://codewhisper-xxxxx-uc.a.run.app) *(replace with your Cloud Run URL after deploy)*

The live version uses voice + screen share. For the full experience with direct code access and IDE navigation, run locally with the code watcher and click agent.

---

## Demo Video

*Add your YouTube demo video link here after recording (under 4 minutes, PUBLIC).*

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Agent Framework | Google ADK (Agent Development Kit) |
| AI Model | Gemini Live API (bidirectional audio + vision) |
| Backend | Python, FastAPI, WebSocket |
| Frontend | React, Tailwind CSS, Vite, Web Audio API |
| Code Access | Python watchdog (universal file watcher) |
| Screen Interaction | pyautogui (cross-platform click agent) |
| Deployment | Google Cloud Run, Docker, Cloud Build |
| Infrastructure | Docker Compose (local), Artifact Registry (production) |

---

## Deploy to Cloud Run

**One-off deploy (from your machine):**

```bash
gcloud builds submit --config cloudbuild.yaml
```

**Deploy on every push to `main`:**  
- **GitHub Actions** (recommended): Add secrets `GCP_PROJECT_ID` and `GCP_SA_KEY`; each push runs [.github/workflows/deploy-cloudrun.yml](.github/workflows/deploy-cloudrun.yml). See [docs/github-actions-deploy.md](docs/github-actions-deploy.md).  
- **Cloud Build trigger:** Alternatively connect the repo in GCP and create a trigger — [docs/cloud-build-trigger-setup.md](docs/cloud-build-trigger-setup.md).

---

## Quick Start

### Try it online (full features with local helpers)

For file access and navigation with the hosted app, run the code watcher and click agent pointing at your Cloud Run URL. **The app shows connection status when the session is active** — if tools are not connected, copy-paste the commands shown.

```bash
# 1. Open the app in your browser
# Visit: https://codewhisper-xxxxx.run.app (replace with your Cloud Run URL)

# 2. Connect your project files (new terminal)
pip install watchdog websockets
python code_watcher.py /path/to/your/project --backend-url https://codewhisper-xxxxx.run.app

# 3. Enable IDE navigation (new terminal, optional)
pip install pyautogui websockets
python click_agent.py --backend-url https://codewhisper-xxxxx.run.app

# 4. Click Start Session in the browser, share your full screen, allow mic
```

*You can pass `https://` or `wss://` for `--backend-url`; both work.*

### Try it online (no setup)

Visit the Cloud Run URL. Click **Start Session**, share your screen, allow mic. Works for voice + screen share without local helpers.

### Run fully local

**Prerequisites:** Docker, Python 3.9+, a [Gemini API key](https://aistudio.google.com/apikey) (free).

```bash
# 1. Clone and configure
git clone https://github.com/weeklyweights-a11y/CodeWhisper.git
cd CodeWhisper
cp .env.example .env
# Add your GOOGLE_API_KEY to .env

# 2. Start backend + frontend
docker compose up

# 3. Start code watcher (in a new terminal)
pip install watchdog websockets
python code_watcher.py /path/to/your/project

# 4. (Optional) Start click agent for IDE navigation
pip install pyautogui websockets
python click_agent.py

# 5. Open http://localhost:3000
# Click Start Session, share your full screen, allow mic
```

---

## Three Tiers of Operation

1. **Cloud (hosted):** Voice + screen share. All prompt-driven features. No direct code access.
2. **Local + Code Watcher:** Adds direct file reading. Code Review Agent gets actual file text. Any editor.
3. **Local + Code Watcher + Click Agent:** Adds UI interaction. Navigator Agent clicks and scrolls.

---

## Project Structure

```
CodeWhisper/
├── README.md
├── Dockerfile                 # Production multi-stage build
├── docker-compose.yml         # Local dev (backend + frontend)
├── cloudbuild.yaml            # GCP build + deploy
├── .dockerignore
├── backend/
│   ├── main.py                # FastAPI + WebSocket + ADK
│   ├── config.py
│   ├── codewhisper/           # ADK agents, tools, prompts
│   ├── services/              # extension_bridge, click_client
│   ├── utils/                 # coordinates
│   └── static/                # React build (production)
├── frontend/                  # React, Vite, Tailwind
├── extension/                 # VS Code extension (optional)
├── docs/
│   └── architecture.svg       # Architecture diagram
├── code_watcher.py            # Universal file watcher (local)
├── click_agent.py             # Screen interaction (local)
└── watcher_requirements.txt
```

---

## Hackathon Compliance

| Requirement | Status |
|-------------|--------|
| Category: Live Agent | ✅ |
| Gemini Live API (bidirectional audio + vision) | ✅ |
| Google ADK (multi-agent, tool calling, Runner.run_live()) | ✅ |
| Google Cloud service (Cloud Run) | ✅ |
| Hosted on Google Cloud | ✅ |
| Multimodal (audio, vision, tools) | ✅ |
| Real-time interaction (streaming, VAD interruption) | ✅ |
| New project (built during contest) | ✅ |

---

## Built With

Built for the **Gemini Live Agent Challenge**. #GeminiLiveAgentChallenge
