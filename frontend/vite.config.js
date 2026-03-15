import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        'control-panel': resolve(__dirname, 'control-panel.html'),
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/ws': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
        ws: true,
        configure: (proxy) => {
          proxy.on('proxyReqWs', (_proxyReq, _req, socket) => {
            socket.setTimeout(0);
            socket.setKeepAlive(true);
          });
        },
      },
      '/health': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
      },
    },
  },
});
