/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 0.0.0.0 so the port is reachable when the dev server runs in a
    // container. Harmless when it runs natively.
    host: true,
    // Bind-mounted source on macOS and Windows does not deliver inotify
    // events, so file changes are missed and hot reload silently stops
    // working. Polling costs a little CPU and is opt-in through the
    // environment, which docker-compose.dev.yml sets.
    watch:
      process.env.CHOKIDAR_USEPOLLING === 'true'
        ? { usePolling: true, interval: 300 }
        : undefined,
    proxy: {
      // The same contract as production: the browser calls /api on its own
      // origin and something in front forwards it to the backend. In
      // production that is nginx; here it is this proxy. Keeping both means
      // VITE_API_BASE_URL stays empty everywhere and no code branches on
      // which environment it is in.
      //
      // DEV_API_PROXY_TARGET is read by Node at config time and is NOT a
      // VITE_ variable, so it is never compiled into the browser bundle.
      // Default is the host; the dev container overrides it to backend:8000.
      '/api': {
        target: process.env.DEV_API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    coverage: {
      reporter: ['text', 'html'],
    },
  },
});
