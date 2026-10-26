import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://127.0.0.1:8000",
      "/predict": "http://127.0.0.1:8000",
      "/assessments": "http://127.0.0.1:8000",
      "/scenarios": "http://127.0.0.1:8000",
      "/explain": "http://127.0.0.1:8000",
      "/criteria": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "../backend/static",
    emptyOutDir: true,
  },
});
