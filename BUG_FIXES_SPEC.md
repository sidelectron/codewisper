# Bug Fixes: Language, Echo, Danger Zone, Questions, Summary

> **These are all critical bugs that must be fixed before the demo video and submission.**

---

## Bug 1: Starts Speaking in Hindi

**Problem:** Gemini auto-detects user's system language or mic input language and starts speaking Hindi (or other non-English language).

**Fix 1 — System prompt (prompts.py, ROOT_INSTRUCTION):**

Add this as the VERY FIRST line of ROOT_INSTRUCTION, before everything else:

"LANGUAGE: You MUST speak in English at all times. All your spoken responses must be in English. If the user speaks in another language, respond in English first, then ask: 'Would you like me to switch to [detected language]?' Only switch if they confirm."

Better approach — make it configurable. Add a language parameter that gets injected into the prompt at session start. But for the hackathon, hardcoding English-first with the ability to switch is fine.

**Fix 2 — RunConfig (main.py, _build_run_config):**

Check if the ADK RunConfig or Gemini LiveConnectConfig supports a language or locale setting. If so, set it to "en-US". Check the ADK docs for speech_config options.

**Fix 3 — Session opening prompt:**

In the ROOT_INSTRUCTION session opening section, change the greeting to explicitly be in English:

"When the session starts, greet the user in English: 'Hey! I can see your screen...'"

---

## Bug 2: Two Voices Overlapping (Echo/Feedback Loop)

**Problem:** Gemini's voice plays through speakers → mic picks it up → sends back to Gemini → Gemini hears its own voice and responds to it → overlapping audio, two voices talking.

**This is the most critical bug. It makes the product unusable.**

**Fix 1 — Frontend: Mute mic while Gemini is speaking (useSession.js):**

When audio chunks arrive from Gemini (type "audio"), the frontend should temporarily suppress sending mic audio to the backend. Not by stopping the mic, but by not sending chunks while Gemini audio is actively playing.

Add a flag: `geminiSpeakingRef`. Set it to true when audio chunks arrive. Set it to false when playback stops (after a gap of ~500ms with no new audio chunks).

In the onAudioChunk callback, check this flag:
```javascript
onAudioChunk: (chunk) => {
  if (isConnectedRef.current && sessionStateRef.current === 'active' && !geminiSpeakingRef.current) {
    sendMessage({ type: 'audio', data: chunk });
  }
}
```

This is NOT the same as disabling interruption. The user can still speak — they just need to speak loud enough / clearly enough that it doesn't sound like echo. When the user speaks, Gemini's VAD will detect it and interrupt. But ambient echo of Gemini's own voice won't be forwarded.

**Problem with Fix 1:** This completely disables the mic during Gemini speech, which means the user can't interrupt. Interruption is a key feature.

**Better Fix 2 — Use AudioWorklet to cancel echo:**

Replace ScriptProcessorNode with an AudioWorklet that does basic echo detection. If the audio coming from the mic closely matches what was just played through the speakers (energy-level comparison), suppress it.

This is complex. Skip for hackathon.

**Best Fix 3 (pragmatic for hackathon) — Tell users to use headphones + add prompt guard:**

In the UI, add a prominent message: "🎧 Use headphones for the best experience. Speaker audio may cause echo."

In the system prompt, add: "IMPORTANT: You may sometimes hear your own voice echoed back through the user's microphone. This is audio feedback, not the user speaking. Ignore any audio that sounds like a repetition of what you just said. Only respond to clearly new speech from the user that is different from your recent output."

AND use Fix 1 (suppress mic during playback) but with a shorter window — only suppress for the first 200ms after each audio chunk starts playing, then allow the mic through. This filters the loudest echo burst while still allowing the user to interrupt with clear speech.

**Recommended approach: Fix 1 (suppress mic during active playback) + Fix 3 (headphones notice + prompt guard).** This is the most reliable combination for the hackathon.

**Implementation of Fix 1 in useSession.js:**

Add a ref to track when Gemini is speaking:
```javascript
const geminiSpeakingRef = useRef(false);
const speakingTimeoutRef = useRef(null);
```

When audio arrives from the backend:
```javascript
} else if (type === 'audio' && message.data) {
  geminiSpeakingRef.current = true;
  // Reset the timeout every time new audio arrives
  if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
  speakingTimeoutRef.current = setTimeout(() => {
    geminiSpeakingRef.current = false;
  }, 800); // 800ms after last audio chunk = Gemini stopped speaking
  
  playChunk(message.data);
}
```

In the onAudioChunk callback:
```javascript
onAudioChunk: (chunk) => {
  if (isConnectedRef.current && sessionStateRef.current === 'active' && !geminiSpeakingRef.current) {
    sendMessage({ type: 'audio', data: chunk });
  }
}
```

This means: while Gemini is speaking (audio chunks arriving), mic data is not sent. 800ms after the last audio chunk, mic data resumes. The user can interrupt by waiting for a brief pause and speaking, OR by speaking loudly (though this won't work with the suppression active).

**Trade-off:** User cannot interrupt mid-sentence. They have to wait for Gemini to pause. This is acceptable for the hackathon demo — it's better than the echo loop.

If you want interruption to work, use a softer version: instead of completely suppressing, reduce the volume threshold. Only send mic audio if the mic level is above a certain threshold (indicating the user is actively speaking, not ambient echo). This requires measuring audio energy in the ScriptProcessorNode:

```javascript
processor.onaudioprocess = (e) => {
  const input = e.inputBuffer.getChannelData(0);
  
  // Calculate RMS energy
  let sum = 0;
  for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
  const rms = Math.sqrt(sum / input.length);
  
  // Only send if energy is above threshold (user is speaking, not echo)
  const THRESHOLD = 0.02; // Tune this value
  if (rms < THRESHOLD && geminiSpeakingRef.current) return; // Suppress low-level echo
  
  const int16 = float32ToInt16(input);
  const base64 = arrayBufferToBase64(int16.buffer);
  if (onAudioChunkRef.current) onAudioChunkRef.current(base64);
};
```

This is the smartest approach: during Gemini playback, only forward mic audio that's LOUD (user deliberately speaking), not quiet ambient echo. The user can interrupt by speaking at normal volume.

---

## Bug 3: Not Detecting Hardcoded Values (Danger Zone)

**Problem:** CodeWhisper doesn't flag hardcoded API keys, secrets, or passwords visible in the code.

**Root causes:**
1. Screen frames at 768x768 JPEG are too compressed to read small text like API keys
2. The root agent isn't proactively scanning for security issues — it's waiting to "notice" them
3. Agent delegation to security_scanner may not be happening

**Fix 1 — Make root agent directly scan for security (prompts.py, ROOT_INSTRUCTION):**

Don't rely on delegation to the security_scanner for basic detection. Add to ROOT_INSTRUCTION:

"DANGER ZONE — ALWAYS ACTIVE: You must continuously scan ALL code visible on screen and ALL code received from the file watcher for security issues. When you see ANY of these, IMMEDIATELY say 'Heads up —' followed by the specific issue:
- Strings that look like API keys (long alphanumeric strings, especially after 'key=', 'token=', 'secret=', 'password=', 'api_key=')
- Hardcoded passwords or credentials
- SQL queries with string concatenation
- eval() or innerHTML with dynamic content
- Missing error handling on fetch/axios/database calls
- CORS set to allow all origins

Do NOT wait to delegate to another agent. Flag it YOURSELF, immediately, in ANY Flow Mode."

**Fix 2 — If code watcher is connected, security scanning is much better:**

The actual file text from the code watcher is character-perfect. The security agent can read exact variable names, key values, etc. Make sure the code watcher is running during testing.

Add to SECURITY_INSTRUCTION:

"When you receive file contents from the code watcher, scan the FULL text for security issues. Look for patterns like: API_KEY = 'sk-...', password = '...', token = '...', any string assigned to a variable named key/secret/token/password/credential that contains a literal value."

**Fix 3 — Test with obvious examples:**

When testing, make sure the hardcoded key is OBVIOUS. Put this in a visible file:
```javascript
const API_KEY = "sk-1234567890abcdef1234567890abcdef";
const DB_PASSWORD = "admin123";
```

If CodeWhisper still doesn't flag it with the code watcher running and these blatant examples, the issue is in the agent delegation or the prompts need to be even more explicit.

---

## Bug 4: Not Answering Questions

**Problem:** When user asks a question, CodeWhisper doesn't respond or responds with overlapping audio.

**This is likely caused by Bug 2 (echo loop).** When the user speaks, their voice gets mixed with Gemini's echo. Gemini can't distinguish the user's question from echo.

**Fix:** Fix Bug 2 first (mic suppression during playback). Then test questions again.

**Additional fix — Prompt (ROOT_INSTRUCTION):**

"When the user asks you a question (even if you are currently narrating), STOP your current narration immediately and answer their question directly. Questions take priority over narration. After answering, resume your previous behavior."

This is already in the prompt but make sure it's explicit and not buried. Move it to a prominent position.

---

## Bug 5: Not Giving Summary at End

**Problem:** When user clicks End Session, no summary is generated.

**Root cause in main.py:** When end_session is received:
1. It sets end_session_requested event
2. Sends a text message to Gemini: "The user has clicked End Session. Deliver the session summary now."
3. Waits 2 seconds
4. If no summary received, sends session_ended

**Issues:**
- 2 seconds is way too short for Gemini to generate a full spoken summary
- The output_transcription check may not be capturing the summary text correctly
- The summary agent may not be receiving the delegation

**Fix in main.py — increase timeout and improve detection:**

Change the end_session handler:

```python
elif action == "end_session":
    logger.info("Session end requested")
    if queue and session_started:
        end_session_requested.set()
        # Ask for summary
        content = types.Content(
            parts=[types.Part(text="The user is ending the session now. Please give a comprehensive spoken summary of this session covering: what was built, key concepts, any security issues flagged, things to review, and recommended next steps. Be specific about the code from this session.")]
        )
        queue.send_content(content)
        # Wait longer for summary — Gemini needs 15-30 seconds to generate a full summary
        await asyncio.sleep(20.0)
        if not summary_sent.is_set():
            # Try to capture whatever text we have
            await websocket.send_json({"type": "summary", "text": "Session summary is being spoken. Check audio output."})
            await websocket.send_json({"type": "status", "status": "session_ended"})
            queue.close()
    break
```

**Fix the summary text capture in _downstream_task:**

The current code checks `event.output_transcription` for the summary text. This may not be the right field. ADK events have different structures. Check what fields the events actually contain by adding debug logging:

```python
async for event in runner.run_live(...):
    logger.debug("Event: %s", event.model_dump_json(exclude_none=True)[:500])
    # ... rest of handler
```

Run a session, end it, check the logs. See what events come through when Gemini is generating the summary. The text may be in:
- event.content.parts[0].text (if Gemini sends text alongside audio)
- event.output_transcription (if ADK is transcribing the audio output)
- event.actions (if it's a tool call response)

Once you know the correct field, update the summary detection logic.

**Alternative approach — Request text summary separately:**

After the spoken summary, send another text prompt:
```python
content = types.Content(
    parts=[types.Part(text="Now provide that same summary as structured text with markdown sections: ## What Was Built, ## Key Concepts, ## Danger Zones, ## Things to Review, ## Next Steps")]
)
queue.send_content(content)
```

This explicitly asks for a TEXT response which is easier to capture than trying to transcribe audio.

But check if this works with AUDIO response modality. If RunConfig is set to response_modalities=["AUDIO"], Gemini may only generate audio, not text. You might need to temporarily switch modality or accept that the summary text comes from transcription.

**Simplest fix for hackathon:** Don't rely on automatic summary text capture. Let the spoken summary be the primary delivery. Show a message in the UI: "Summary spoken — listen for the recap" instead of trying to display text. The Download as Markdown feature can wait for post-hackathon.

OR: After the session ends, make a SEPARATE standard (non-live) Gemini API call with a prompt like "Summarize this coding session" and whatever context you have. This doesn't need the Live API and can return pure text.

---

## Priority Order

1. **Fix Bug 2 (echo)** — This is blocking everything. Without this, the demo is unusable.
2. **Fix Bug 1 (language)** — Quick prompt change, high impact.
3. **Fix Bug 5 (summary)** — Increase timeout, add logging to debug.
4. **Fix Bug 3 (Danger Zone)** — Prompt changes to make scanning more aggressive.
5. **Fix Bug 4 (questions)** — Likely resolves once Bug 2 is fixed.

---

## Cursor Prompt

```
Fix these 5 bugs in CodeWhisper:

1. LANGUAGE: Add "LANGUAGE: You MUST speak in English at all times unless the user explicitly asks to switch." as the VERY FIRST line of ROOT_INSTRUCTION in backend/codewhisper/prompts.py.

2. ECHO: In frontend/src/hooks/useSession.js, add mic suppression during Gemini playback. Track geminiSpeakingRef — set true when audio arrives, set false 800ms after last chunk. In onAudioChunk callback, don't send when geminiSpeakingRef is true. Also add energy-based gating: only send mic audio above RMS threshold 0.02 when Gemini is speaking.

3. DANGER ZONE: In ROOT_INSTRUCTION in prompts.py, add explicit always-active scanning: "You must continuously scan ALL code visible on screen for security issues. When you see API keys, hardcoded passwords, tokens, or secrets, IMMEDIATELY flag with 'Heads up —'. Do NOT delegate this — flag it yourself."

4. SUMMARY: In backend/main.py end_session handler, increase the wait from 2 seconds to 20 seconds. Make the summary request prompt more explicit. Add debug logging for all events during summary generation.

5. Add "🎧 Use headphones for best experience" text in SessionControls.jsx when session is active.

Do NOT change: agent definitions, tool functions, WebSocket protocol, frontend hooks structure.
```
