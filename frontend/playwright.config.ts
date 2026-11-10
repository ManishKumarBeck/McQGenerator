import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

// End-to-end tests run the real backend with a fake AI generator (no OpenAI calls)
// and the Vite dev server proxying /api to it.
const python = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const apiPort = 8001;
const webPort = 5174;
const db = path.join(os.tmpdir(), "mcqgen-e2e.db");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 900 } }, testIgnore: /mobile\.spec/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /mobile\.spec/ },
  ],
  webServer: [
    {
      command: `${python} -m tests.e2e_server --port ${apiPort} --db "${db}" --fresh`,
      cwd: path.resolve(import.meta.dirname, "../backend"),
      url: `http://127.0.0.1:${apiPort}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
    },
    {
      // Bind explicitly to IPv4: "localhost" resolves to ::1 first on GitHub's Ubuntu runners,
      // which made Vite listen on IPv6 only while Playwright waited on 127.0.0.1.
      command: `npx vite --host 127.0.0.1 --port ${webPort} --strictPort`,
      url: `http://127.0.0.1:${webPort}`,
      env: { VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}` },
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
    },
  ],
});
