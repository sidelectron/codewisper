# Devpost Submission Text — CodeWhisper (~400 words)

Copy the sections below into Devpost.

---

## Inspiration

The explosion of "vibe coding" has created a dangerous gap. Developers use AI tools like Cursor and Copilot to generate entire codebases in minutes but ship code they don't understand. Studies show AI-generated code has 1.7x more bugs and 2.74x more security vulnerabilities. When it breaks, developers can't debug it. We built CodeWhisper to close this understanding gap.

## What It Does

CodeWhisper is a real-time AI companion that watches your IDE screen and explains AI-generated code through voice. Share your screen, start coding with any AI tool, and CodeWhisper narrates what's happening — like a senior developer sitting next to you. It features three voice-switchable Flow Modes (Sportscaster, Catch-Up, Review), proactive Danger Zone security alerts, Adaptive Depth that adjusts to your skill level, IDE navigation that actively opens and reviews files, and comprehensive session summaries.

## How We Built It

CodeWhisper is built as a multi-agent system using Google's Agent Development Kit (ADK) with the Gemini Live API. Five specialized agents work together: a Root Orchestrator manages voice conversation and Flow Modes, a Code Review Agent explains code and tracks file relationships, a Security Agent scans for vulnerabilities, a Navigator Agent opens files and interacts with the IDE, and a Summary Agent generates session recaps. The backend uses FastAPI with ADK's Runner.run_live() for bidirectional audio and vision streaming. A universal code watcher (Python watchdog) sends actual file contents to the agents — not screenshot OCR — working with any editor. A cross-platform click agent (pyautogui) enables screen interaction. The frontend is React with Web Audio API for bidirectional voice. Deployed on Google Cloud Run.

## Challenges We Ran Into

Migrating from raw Gemini SDK to ADK's multi-agent framework mid-project. Coordinating five agents for smooth conversation flow without jarring transitions. Getting the code watcher's debouncing right — too fast floods Gemini, too slow misses rapid AI edits. Coordinate mapping between 768x768 screen frames and actual screen resolution for accurate clicking. Prompt engineering for proactive narration that talks enough to be useful without being annoying.

## What We Learned

ADK dramatically simplifies real-time agent development — tool execution, session management, and audio streaming that took weeks of manual code became declarative configuration. Multi-agent architecture forces cleaner separation of concerns. The universal code watcher approach (filesystem watching vs IDE extension) was simpler and more portable. System prompt engineering remains the highest-leverage activity.

## Built With

Google ADK, Gemini Live API, Python, FastAPI, React, Tailwind CSS, Vite, Web Audio API, watchdog, pyautogui, Docker, Google Cloud Run, Cloud Build
