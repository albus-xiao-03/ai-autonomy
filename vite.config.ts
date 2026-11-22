import { fileURLToPath } from 'node:url';
import { defineConfig, type ProxyOptions } from 'vite';

// The browser only talks to the engine through /api (REST) and /ws (WebSocket); the dev
// and preview servers proxy both to the engine on loopback (plans/R1.md §6).
// REQ: ARCH-01
const engineTarget = `http://127.0.0.1:${process.env.AIA_ENGINE_PORT ?? '8787'}`;

function engineProxy(): Record<string, ProxyOptions> {
  return {
    '/api': { target: engineTarget },
    '/ws': { target: engineTarget, ws: true },
  };
}

export default defineConfig({
  root: fileURLToPath(new URL('./aiautonomy/interfaces', import.meta.url)),
  publicDir: false,
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: engineProxy() },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy: engineProxy() },
  oxc: { jsx: { runtime: 'automatic', importSource: 'preact' } },
  build: {
    // The engine serves this directory at `/`.
    outDir: fileURLToPath(new URL('./dist', import.meta.url)),
    emptyOutDir: true,
    sourcemap: true,
    chunkSizeWarningLimit: 1024,
  },
});
