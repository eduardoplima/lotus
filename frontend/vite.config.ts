import { defineConfig } from "vite";

// The dev server proxies /api to the localhost-bound FastAPI backend, so the
// browser only ever talks to localhost and the API needs no open CORS (§12).
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
