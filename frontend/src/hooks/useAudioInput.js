import { useState, useRef, useCallback } from 'react';
import { float32ToInt16, arrayBufferToBase64 } from '../utils/audioUtils';

const SAMPLE_RATE = 16000;
const BUFFER_SIZE = 4096;
const INPUT_CHANNELS = 1;
const OUTPUT_CHANNELS = 1;

const RMS_THRESHOLD = 0.02;

/**
 * Manages microphone capture and PCM audio streaming (16kHz mono, base64).
 * @param {Object} options
 * @param {function(string): void} [options.onAudioChunk] - Called with base64 PCM chunk for each buffer.
 * @param {React.RefObject<boolean>} [options.geminiSpeakingRef] - When true, only forward mic audio above RMS threshold (echo suppression).
 * @returns {{ isRecording: boolean, startRecording: function, stopRecording: function, error: string|null }}
 */
export function useAudioInput(options = {}) {
  const { onAudioChunk, geminiSpeakingRef } = options;
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);

  const streamRef = useRef(null);
  const contextRef = useRef(null);
  const processorRef = useRef(null);
  const onAudioChunkRef = useRef(onAudioChunk);
  onAudioChunkRef.current = onAudioChunk;
  const geminiSpeakingRefRef = useRef(geminiSpeakingRef);
  geminiSpeakingRefRef.current = geminiSpeakingRef;

  const stopRecording = useCallback(() => {
    if (processorRef.current && contextRef.current) {
      try {
        processorRef.current.disconnect();
      } catch (_) {}
      processorRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (contextRef.current) {
      contextRef.current.close();
      contextRef.current = null;
    }
    setIsRecording(false);
    setError(null);
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: INPUT_CHANNELS,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      const context = new AudioContext({ sampleRate: SAMPLE_RATE });
      contextRef.current = context;

      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(BUFFER_SIZE, INPUT_CHANNELS, OUTPUT_CHANNELS);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        const ref = geminiSpeakingRefRef.current;
        if (ref?.current) {
          let sum = 0;
          for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
          const rms = Math.sqrt(sum / input.length);
          if (rms < RMS_THRESHOLD) return;
        }
        const int16 = float32ToInt16(input);
        const base64 = arrayBufferToBase64(int16.buffer);
        if (onAudioChunkRef.current) {
          onAudioChunkRef.current(base64);
        }
      };

      source.connect(processor);
      processor.connect(context.destination);

      setIsRecording(true);
    } catch (err) {
      setError(err.message || 'Microphone access failed');
      stopRecording();
    }
  }, [stopRecording]);

  return { isRecording, startRecording, stopRecording, error };
}
