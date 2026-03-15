import { useState, useEffect, useCallback } from 'react';

const HEALTH_POLL_INTERVAL_MS = 10000;

/**
 * Poll /health for extension_connected and click_agent_available.
 * Derives wsBaseUrl from window.location for copy-paste commands.
 * @param {boolean} enabled - When true, poll every 10s. When false, stop polling.
 * @returns {{ extensionConnected: boolean, clickAgentAvailable: boolean, wsBaseUrl: string }}
 */
export function useHealth(enabled) {
  const [extensionConnected, setExtensionConnected] = useState(false);
  const [clickAgentAvailable, setClickAgentAvailable] = useState(false);
  const [wsBaseUrl, setWsBaseUrl] = useState('');

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/health');
      if (!res.ok) return;
      const data = await res.json();
      setExtensionConnected(Boolean(data.extension_connected));
      setClickAgentAvailable(Boolean(data.click_agent_available));
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      setWsBaseUrl(`${protocol}//${host}`);
    } catch {
      setWsBaseUrl('ws://localhost:8000');
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    fetchHealth();
    const id = setInterval(fetchHealth, HEALTH_POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [enabled, fetchHealth]);

  return { extensionConnected, clickAgentAvailable, wsBaseUrl };
}
