# CodeWhisper — Complete Gap Analysis & Fix Spec

> **15 gaps found in the codebase. Prioritized for March 16 deadline.**
> Hand this entire document to Cursor. Gaps 1–8 are MUST FIX. Gaps 9–15 are nice-to-have.

---

## TIER 1: MUST FIX (Demo won't work without these)

### Gap 1: File changes from code watcher never reach Gemini (DEAD CODE)

**File:** `backend/services/extension_bridge.py` ~line 90

**Problem:** When the code watcher sends `file_changed` or `file_created` events, the handler does literally `pass`. The file content is received by the backend but never forwarded to Gemini. This means even when the code watcher IS connected, Gemini never sees file contents proactively — it can only see them if an agent explicitly calls `get_file_contents`.

**Current code:**
```python
if self._session_queue and message.get("type") in ("file_changed", "file_created"):
    try:
        pass  # <--- NOOP
    except Exception as e:
        logger.warning("Failed to inject file update: %s", e)
```

**Fix:** Replace the `pass` with actual injection:
```python
if self._session_queue and message.get("type") in ("file_changed", "file_created"):
    path = message.get("path", "")
    content = message.get("content", "")
    if content:
        try:
            from google.genai import types
            # Truncate large files to avoid flooding context
            truncated = content[:8000]
            suffix = f"\n... (truncated, {len(content)} chars total)" if len(content) > 8000 else ""
            text = f"[Code Watcher — File {'Created' if message['type'] == 'file_created' else 'Changed'}: {path}]\n```\n{truncated}{suffix}\n```"
            ctx = types.Content(parts=[types.Part(text=text)])
            self._session_queue.send_content(ctx)
            logger.info("Injected file update: %s (%d chars)", path, len(content))
        except Exception as e:
            logger.warning("Failed to inject file update: %s", e)
```

---

### Gap 2: Session queue never registered with extension_bridge

**File:** `backend/main.py`, in the `start_session` handler

**Problem:** After creating `queue = LiveRequestQueue()`, nobody calls `extension_bridge.register_session_queue(queue)`. So `self._session_queue` is always `None` in extension_bridge, and Gap 1's fix would still not work.

**Fix:** In main.py, after `queue = LiveRequestQueue()` and `session_started = True`, add:
```python
extension_bridge.register_session_queue(queue)
```

And in the `finally` block at the end of `websocket_session`, add:
```python
extension_bridge.unregister_session_queue()
```

---

### Gap 3: Root agent has no file tools — hallucinates file contents

**File:** `backend/codewhisper/agent.py`

**Problem:** Root agent only has `get_session_info`. When user asks "what files are in the project?" or "what's in config.py?", root can't check — it guesses from blurry screenshots. This causes hallucination (mentioning files that don't exist).

**Current:**
```python
root_agent = LlmAgent(
    ...
    tools=[tools_module.get_session_info],
)
```

**Fix:**
```python
root_agent = LlmAgent(
    ...
    tools=[tools_module.get_session_info, tools_module.get_file_contents, tools_module.list_project_files],
)
```

---

### Gap 4: Navigator can't read files — only opens them

**File:** `backend/codewhisper/agent.py`

**Problem:** Navigator has `open_file` but not `get_file_contents`. When it opens a file, it can't verify the content or read it for the user.

**Current:**
```python
navigator = LlmAgent(
    tools=[tools_module.open_file, tools_module.click_screen, tools_module.scroll_screen, tools_module.press_keys, tools_module.type_text],
)
```

**Fix:** Add `get_file_contents`:
```python
navigator = LlmAgent(
    tools=[tools_module.open_file, tools_module.get_file_contents, tools_module.click_screen, tools_module.scroll_screen, tools_module.press_keys, tools_module.type_text],
)
```

---

### Gap 5: SECTION_8 IDE navigation prompt is dead code

**File:** `backend/prompts/system_prompt.py` vs `backend/codewhisper/prompts.py`

**Problem:** The detailed IDE navigation behavior (Section 8 — "work in parallel with Cursor", file-by-file workflow, coordinate guidance) exists in `system_prompt.py` as `SECTION_8_IDE_NAVIGATION`. But `agent.py` imports from `codewhisper/prompts.py`, not `prompts/system_prompt.py`. Section 8 is never used. The navigator agent has tools but the root agent doesn't know HOW to use navigation effectively.

**Fix:** Append a condensed version of the navigation behavior to ROOT_INSTRUCTION in `backend/codewhisper/prompts.py`. Add before the closing `"""`:

```python
# Add to end of ROOT_INSTRUCTION in prompts.py:

**IDE Navigation:** You have sub-agents that can open and read files. When the user asks about a specific file, or when you see Cursor editing files:
1. Use get_file_contents(path) to read the file and understand it.
2. Delegate to navigator to open_file(path) so the user can see it in their IDE.
3. Then explain what the file does.

When Cursor finishes editing one file and moves to the next, open the completed file and explain it. Work one file behind Cursor — reviewing as it codes.

Track imports and relationships across files. Build a progressive mental model of the project. After reading several files, explain the overall architecture.

If you don't know whether a file exists, use list_project_files() first. Do NOT guess filenames from screenshots — verify with the tool.
"""
```

---

### Gap 6: Mode switch buttons are cosmetic — don't notify Gemini

**File:** `backend/main.py`, in the `switch_mode` handler

**Problem:** When user clicks a mode button in the Control Panel, the backend sends `{"type": "mode", "mode": "catchup"}` back to the frontend UI, but never tells Gemini. So the UI shows "Catch-Up" but Gemini is still in Sportscaster mode narrating. Voice switching works (Gemini hears it), but button switching is broken.

**Current:**
```python
elif action == "switch_mode":
    mode = message.get("mode")
    if mode and mode in ("sportscaster", "catchup", "review"):
        await websocket.send_json({"type": "mode", "mode": mode})
```

**Fix:**
```python
elif action == "switch_mode":
    mode = message.get("mode")
    if mode and mode in ("sportscaster", "catchup", "review"):
        await websocket.send_json({"type": "mode", "mode": mode})
        # Tell Gemini about the mode switch
        if queue and session_started:
            mode_names = {"sportscaster": "Sportscaster", "catchup": "Catch-Up", "review": "Review"}
            content = types.Content(
                parts=[types.Part(text=f"The user just switched to {mode_names.get(mode, mode)} mode via the UI button. Adjust your behavior accordingly.")]
            )
            queue.send_content(content)
```

---

### Gap 7: Navigator prompt prioritizes clicking over open_file

**File:** `backend/codewhisper/prompts.py`, NAVIGATOR_INSTRUCTION

**Problem:** The current prompt says "Primary method: Use open_file(path) tool (VS Code extension) when available. Fallback method: Use click_screen(x, y)". But then the detailed guidance focuses heavily on clicking filenames in Cursor's panel. When the click agent isn't connected (Cloud Run), the navigator keeps trying to click and failing, then tells the user to open files manually.

**Fix:** Rewrite NAVIGATOR_INSTRUCTION to be clearer:

```python
NAVIGATOR_INSTRUCTION = """Your role is to navigate the IDE — open files, read code, and interact with UI elements.

**ALWAYS try open_file(path) FIRST.** This uses the code watcher and is 100% reliable when connected. If it returns "Extension not connected", fall back to click_screen or tell the user.

**ALWAYS try get_file_contents(path) to READ files.** This gives you the actual text. Do NOT guess file contents from screenshots.

**Before opening or reading a file, use list_project_files() if you're unsure the file exists.** Never guess filenames — verify first.

**click_screen is a LAST RESORT** for UI elements the code watcher cannot control — like Cursor's accept/reject buttons, visual elements, or when open_file is unavailable.

When Cursor finishes editing a file and moves to the next:
1. Call get_file_contents(path) on the completed file to read it.
2. Call open_file(path) to show it in the IDE.
3. Explain what the file does while Cursor works on the next one.

For click_screen: Coordinates are in 768x768 frame space. Aim for center of target. If a click misses, try open_file as fallback.

Narrate navigation: "Let me open auth.js — Cursor just finished editing it."

Do NOT navigate while Cursor is actively editing a file. Wait until it moves on.
Do NOT click randomly or navigate without purpose."""
```

---

### Gap 8: Bug fixes (Echo, Language, Summary, Danger Zone)

Already specced in BUG_FIXES_SPEC.md. These are confirmed present in the code:

1. **Echo** — `useSession.js` already has geminiSpeakingRef + RMS gating. `useAudioInput.js` already has RMS_THRESHOLD = 0.02. These fixes ARE in the code. ✅ ALREADY FIXED.

2. **Language** — ROOT_INSTRUCTION already starts with `**LANGUAGE:** You MUST speak in English`. ✅ ALREADY FIXED.

3. **Summary timeout** — main.py already has `await asyncio.sleep(20.0)`. ✅ ALREADY FIXED.

4. **Danger Zone** — ROOT_INSTRUCTION already has the DANGER ZONE section with aggressive scanning. ✅ ALREADY FIXED.

5. **Headphones notice** — SessionControls.jsx already shows "Use headphones for the best experience." ✅ ALREADY FIXED.

**All 5 bug fixes are already in the code.** The remaining issues are the architectural gaps (1–7 above) and the nice-to-haves below.

---

## TIER 2: SHOULD FIX (Improves demo quality)

### Gap 9: Pulse score inflated — counts every mic audio chunk as a "question"

**File:** `frontend/src/hooks/useSession.js`

**Problem:** In the `onAudioChunk` callback, `pulseQuestionsRef.current += 1` runs for EVERY mic buffer that passes the RMS gate. A 1-second question generates ~4 audio chunks, each incrementing the counter. This inflates Understanding score to 100% almost immediately.

**Fix:** Remove the pulseQuestionsRef increment from onAudioChunk. Only increment on meaningful events:
```javascript
onAudioChunk: (chunk) => {
  if (isConnectedRef.current && sessionStateRef.current === 'active' && !geminiSpeakingRef.current) {
    // Don't increment pulseQuestionsRef here — it fires too often
    sendMessage({ type: 'audio', data: chunk });
  }
},
```

Instead, increment pulseQuestionsRef once when Gemini starts responding (which implies user asked something), for example when `gemini_listening` status arrives after audio was playing.

---

### Gap 10: get_session_info returns static placeholder text

**File:** `backend/codewhisper/tools.py`

**Problem:** `get_session_info()` always returns the same string. The root agent might call it expecting real data.

**Fix:** Low priority. For hackathon, just make it slightly more useful:
```python
async def get_session_info() -> str:
    ext_status = "connected" if extension_bridge.is_connected else "not connected"
    click_status = "connected" if _click_client and await _click_client.check_available() else "not connected"
    return f"Session active. Code watcher: {ext_status}. Click agent: {click_status}. Flow Modes: Sportscaster (default), Catch-Up (say 'go quiet'), Review (say 'just watch'). Say 'wrap up' for session summary."
```

---

### Gap 11: Pydantic warning on response_modalities

**File:** `backend/main.py`, `_build_run_config()`

**Problem:** `response_modalities=["AUDIO"]` passes a string instead of an enum, causing a Pydantic serializer warning in logs.

**Fix:** Try using the enum if available:
```python
try:
    from google.genai.types import Modality
    modalities = [Modality.AUDIO]
except (ImportError, AttributeError):
    modalities = ["AUDIO"]

return RunConfig(
    streaming_mode=StreamingMode.BIDI,
    response_modalities=modalities,
    ...
)
```

If the enum doesn't exist in this version of google-genai, the string fallback is fine — it works, just logs a warning.

---

## TIER 3: NICE TO HAVE (Skip if behind schedule)

### Gap 12: Architecture diagram missing

**File:** `docs/architecture.svg` — referenced in README.md but doesn't exist.

**Impact:** 30% of judging is Demo & Presentation. Architecture diagram is called out as a requirement.

**Fix:** Create a simple SVG or PNG. Can be done in Excalidraw or even as an ASCII art diagram. Show: Browser ↔ WebSocket ↔ FastAPI/ADK ↔ Gemini Live API, with code watcher and click agent as side connections.

---

### Gap 13: .cursorrules file needs renaming

**Problem:** Repo has `cursorrules (1).md` but Cursor reads `.cursorrules` from root.

**Fix:** `cp "cursorrules (1).md" .cursorrules`

---

### Gap 14: Gemini 1011 timeout on static screens

**Problem:** Keepalive sends frames every 5s but Gemini Live API may require audio activity. Static screens with no talking can cause 1011 disconnect.

**Fix:** Send a silent audio chunk every 10s alongside the frame keepalive:
```python
# In the keepalive effect or a backend-side periodic task
import base64
SILENT_PCM = base64.b64encode(b'\x00' * 3200).decode()  # 100ms of silence at 16kHz
```

For hackathon demo, just keep talking. Low priority.

---

### Gap 15: Two prompt files causing confusion

**Problem:** `backend/prompts/system_prompt.py` (Phase 5, unused) and `backend/codewhisper/prompts.py` (ADK, active) both exist. SECTION_8 is in the wrong file.

**Fix:** After copying relevant SECTION_8 content into prompts.py (Gap 5), delete or clearly mark `backend/prompts/system_prompt.py` as deprecated:
```python
"""DEPRECATED — This file is from Phase 5 (pre-ADK). Active prompts are in backend/codewhisper/prompts.py."""
```

---

## Cursor Prompt (Copy-paste this)

```
Read COMPLETE_GAP_ANALYSIS.md. Fix Gaps 1-7 in order:

1. EXTENSION BRIDGE FILE INJECTION: In backend/services/extension_bridge.py, replace the `pass` in the file_changed/file_created handler with actual code that injects file content into the session queue as a types.Content text message. Truncate files over 8000 chars.

2. REGISTER SESSION QUEUE: In backend/main.py, after `queue = LiveRequestQueue()`, call `extension_bridge.register_session_queue(queue)`. In the finally block, call `extension_bridge.unregister_session_queue()`.

3. ROOT AGENT TOOLS: In backend/codewhisper/agent.py, add get_file_contents and list_project_files to root_agent's tools list.

4. NAVIGATOR TOOLS: In backend/codewhisper/agent.py, add get_file_contents to navigator's tools list.

5. NAVIGATION PROMPT: In backend/codewhisper/prompts.py, add IDE navigation guidance to ROOT_INSTRUCTION — tell it to use get_file_contents and list_project_files before guessing, and to delegate to navigator for open_file. Also rewrite NAVIGATOR_INSTRUCTION to prioritize open_file and get_file_contents over click_screen.

6. MODE SWITCH TO GEMINI: In backend/main.py switch_mode handler, after echoing the mode back to frontend, also send a types.Content text message to Gemini via queue.send_content telling it the user switched modes.

7. PULSE FIX: In frontend/src/hooks/useSession.js, remove the pulseQuestionsRef increment from the onAudioChunk callback.

Do NOT change: WebSocket protocol, frontend component structure, Dockerfile, cloudbuild.yaml, code_watcher.py, click_agent.py.
```

---

## Quick Reference: What's Already Fixed vs What's Still Broken

| Item | Status |
|------|--------|
| Echo suppression (geminiSpeakingRef + RMS) | ✅ Already in code |
| English language prompt | ✅ Already in code |
| Summary 20s timeout | ✅ Already in code |
| Danger Zone aggressive scanning prompt | ✅ Already in code |
| Headphones notice in UI | ✅ Already in code |
| Click agent WebSocket redesign | ✅ Already in code |
| Click agent bridge | ✅ Already in code |
| Code watcher WebSocket | ✅ Already in code |
| File injection from code watcher → Gemini | ❌ Gap 1 — NOOP pass |
| Session queue registration | ❌ Gap 2 — never registered |
| Root agent file tools | ❌ Gap 3 — no file access |
| Navigator read tools | ❌ Gap 4 — can't read files |
| IDE navigation prompt | ❌ Gap 5 — dead code |
| Button mode switch to Gemini | ❌ Gap 6 — cosmetic only |
| Navigator prompt priority | ❌ Gap 7 — clicks before open_file |
| Pulse score inflation | ❌ Gap 9 — counts every mic chunk |
| Architecture diagram | ❌ Gap 12 — doesn't exist |
