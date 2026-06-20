import { defineConfig } from "@playwright/test";
import path from "node:path";

// Isolated ports so the e2e stack never collides with a local dev server.
const BACKEND_PORT = 8022;
const FRONTEND_PORT = 5180;
const PRACTICE_BANK = path.resolve("e2e/.artifacts/practice.json");

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    channel: "chrome",
    headless: true,
  },
  webServer: [
    {
      command: `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port ${BACKEND_PORT} --log-level warning`,
      cwd: "..",
      url: `http://127.0.0.1:${BACKEND_PORT}/health`,
      reuseExistingServer: false,
      env: { LLM_PROVIDER: "mock", PRACTICE_BANK_PATH: PRACTICE_BANK },
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      env: { VITE_API_TARGET: `http://127.0.0.1:${BACKEND_PORT}` },
    },
  ],
});
