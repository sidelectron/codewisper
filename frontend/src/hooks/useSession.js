import { useState, useRef, useCallback, useEffect } from 'react';
import { useWebSocket } from './useWebSocket';
import { useScreenCapture } from './useScreenCapture';
import { useAudioInput } from './useAudioInput';
import { useAudioOutput } from './useAudioOutput';

/**
 * High-level session orchestrator. Coordinates WebSocket, screen capture, audio input, and output.
 * Manages state machine: idle -> connecting -> active -> ending -> ended (or error).
 * @returns {{ sessionState: string, startSession: function, endSession: function, currentMode: string, error: string|null, summary: string|null, geminiStatus: string|null, isConnected: boolean }}
 */
export function useSession() {
  const [sessionState, setSessionState] = useState('idle');
  const [summary, setSummary] = useState(null);
  const [geminiStatus, setGeminiStatus] = useState(null);
  const [error, setError] = useState(null);
  const [currentMode, setCurrentMode] = useState('sportscaster');

  const sentStartRef = useRef(false);
  const sessionStateRef = useRef('idle');
  const isConnectedRef = useRef(false);
  const summaryTimeoutRef = useRef(null);
  const geminiSpeakingRef = useRef(false);
  const speakingTimeoutRef = useRef(null);
  const { playChunk, stop: stopAudio } = useAudioOutput();

  const audioChunksReceivedRef = useRef(0);
  const [pulseScore, setPulseScore] = useState(0);
  const pulseTotalRef = useRef(0);
  const pulseExplainedRef = useRef(0);
  const pulseQuestionsRef = useRef(0);

  const updatePulseScore = useCallback(() => {
    const total = pulseTotalRef.current;
    const explained = pulseExplainedRef.current;
    const questions = pulseQuestionsRef.current;
    const score =
      total > 0 ? Math.min(100, Math.round(((explained + questions) / total) * 100)) : 0;
    setPulseScore(score);
  }, []);

  const handleMessage = useCallback((message) => {
    const type = message?.type;
    if (type === 'status') {
      const status = message.status;
      if (status === 'gemini_connected') {
        console.log('[CodeWhisper] Gemini connected — session active');
      }
      setGeminiStatus(status);
      if (status === 'gemini_connected') {
        setSessionState('active');
        setError(null);
      } else if (status === 'session_ended') {
        if (summaryTimeoutRef.current) {
          clearTimeout(summaryTimeoutRef.current);
          summaryTimeoutRef.current = null;
        }
        setSummary((prev) => prev ?? 'Summary unavailable.');
        setSessionState('ended');
      } else if (status === 'gemini_listening') {
        // Turn complete; keep playing any queued audio (we don't stop on timer anymore).
      } else if (status === 'interrupted') {
        // User spoke while Gemini was talking (barge-in). Clear playback immediately.
        stopAudio();
      }
    } else if (type === 'summary') {
      if (summaryTimeoutRef.current) {
        clearTimeout(summaryTimeoutRef.current);
        summaryTimeoutRef.current = null;
      }
      const text = message.text ?? message.data ?? '';
      setSummary(text);
      setSessionState((s) => (s === 'ending' ? 'ended' : s));
    } else if (type === 'error') {
      setError(message.message || 'Something went wrong');
      setSessionState('error');
    } else if (type === 'mode') {
      const mode = message.mode ?? message.data;
      if (mode && ['sportscaster', 'catchup', 'review'].includes(mode)) {
        setCurrentMode(mode);
      }
    } else if (type === 'audio' && message.data) {
      geminiSpeakingRef.current = true;
      if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
      speakingTimeoutRef.current = setTimeout(() => {
        geminiSpeakingRef.current = false;
      }, 800);
      audioChunksReceivedRef.current += 1;
      pulseExplainedRef.current += 1;
      updatePulseScore();
      if (audioChunksReceivedRef.current <= 3) {
        console.log('[CodeWhisper] Received audio chunk #' + audioChunksReceivedRef.current + ', playing');
      }
      playChunk(message.data);
    } else if (type === 'pulse') {
      const score = message.score;
      if (typeof score === 'number') setPulseScore(Math.min(100, Math.max(0, Math.round(score))));
      if (typeof message.total === 'number') pulseTotalRef.current = message.total;
      if (typeof message.explained === 'number') pulseExplainedRef.current = message.explained;
      if (typeof message.questions === 'number') pulseQuestionsRef.current = message.questions;
    }
  }, [playChunk, stopAudio, updatePulseScore]);

  const {
    isConnected,
    connect,
    disconnect,
    sendMessage,
  } = useWebSocket({ onMessage: handleMessage });

  sessionStateRef.current = sessionState;
  isConnectedRef.current = isConnected;

  const { isCapturing, startCapture, stopCapture, latestFrame, captureWidth, captureHeight } = useScreenCapture();
  const { isRecording, startRecording, stopRecording } = useAudioInput({
    onAudioChunk: (chunk) => {
      if (isConnectedRef.current && sessionStateRef.current === 'active' && !geminiSpeakingRef.current) {
        sendMessage({ type: 'audio', data: chunk });
      }
    },
    geminiSpeakingRef,
  });

  // When in active, send latest frame when it changes
  const prevFrameRef = useRef(null);
  const latestFrameRef = useRef(null);
  latestFrameRef.current = latestFrame;
  useEffect(() => {
    if (sessionState !== 'active' || !isConnected || !latestFrame || latestFrame === prevFrameRef.current) return;
    prevFrameRef.current = latestFrame;
    pulseTotalRef.current += 1;
    updatePulseScore();
    sendMessage({ type: 'frame', data: latestFrame });
  }, [sessionState, isConnected, latestFrame, sendMessage, updatePulseScore]);

  // Keepalive: send frame every 5s to avoid Gemini 1011 timeout when screen is static
  useEffect(() => {
    if (sessionState !== 'active' || !isConnected) return;
    const id = setInterval(() => {
      const frame = latestFrameRef.current;
      if (frame) sendMessage({ type: 'frame', data: frame });
    }, 5000);
    return () => clearInterval(id);
  }, [sessionState, isConnected, sendMessage]);

  // Start screen share and mic as soon as user clicks Start (before Gemini connects)
  // So the picker appears first; by the time Gemini connects we have frame + audio ready
  useEffect(() => {
    if (sessionState !== 'connecting') return;
    startCapture();
    startRecording();
  }, [sessionState, startCapture, startRecording]);

  // Send start_session when WS connected (after user has had time to pick screen/grant mic)
  useEffect(() => {
    if (sessionState !== 'connecting' || !isConnected || sentStartRef.current) return;
    sentStartRef.current = true;
    const payload = { type: 'control', action: 'start_session' };
    if (captureWidth != null && captureHeight != null) {
      payload.screen_width = captureWidth;
      payload.screen_height = captureHeight;
    }
    sendMessage(payload);
  }, [sessionState, isConnected, sendMessage, captureWidth, captureHeight]);

  // If connection closes while ending, treat as ended
  useEffect(() => {
    if (sessionState === 'ending' && !isConnected) {
      setSessionState('ended');
    }
  }, [sessionState, isConnected]);

  const startSession = useCallback(() => {
    setError(null);
    setSummary(null);
    setGeminiStatus(null);
    setPulseScore(0);
    pulseTotalRef.current = 0;
    pulseExplainedRef.current = 0;
    pulseQuestionsRef.current = 0;
    sentStartRef.current = false;
    setSessionState('connecting');
    connect();
  }, [connect]);

  const endSession = useCallback(() => {
    setSessionState('ending');
    sendMessage({ type: 'control', action: 'end_session' });
    stopCapture();
    stopRecording();
    stopAudio();
    if (summaryTimeoutRef.current) clearTimeout(summaryTimeoutRef.current);
    summaryTimeoutRef.current = setTimeout(() => {
      setSessionState((s) => {
        if (s === 'ending') {
          setSummary('Summary unavailable.');
          return 'ended';
        }
        return s;
      });
      summaryTimeoutRef.current = null;
    }, 30000);
  }, [sendMessage, stopCapture, stopRecording, stopAudio]);

  const startNewSession = useCallback(() => {
    setSummary(null);
    setSessionState('idle');
    setError(null);
    setGeminiStatus(null);
    sentStartRef.current = false;
    disconnect();
  }, [disconnect]);

  const switchMode = useCallback(
    (mode) => {
      if (!['sportscaster', 'catchup', 'review'].includes(mode)) return;
      setCurrentMode(mode);
      sendMessage({ type: 'control', action: 'switch_mode', mode });
    },
    [sendMessage]
  );

  return {
    sessionState,
    startSession,
    endSession,
    startNewSession,
    currentMode,
    switchMode,
    error,
    summary,
    geminiStatus,
    isConnected,
    isRecording,
    isCapturing,
    pulseScore,
  };
}