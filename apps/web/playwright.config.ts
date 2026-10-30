import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure",
    // Pre-installed browser in the cloud sandbox; unset elsewhere so Playwright uses its own download.
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH, args: ["--no-sandbox"] } : {},
  },
  webServer: [
    {
      command: "../../.venv/bin/python -m uvicorn app.main:app --port 8000 --app-dir ../api",
      cwd: ".", url: "http://127.0.0.1:8000/api/v1/health", reuseExistingServer: true, timeout: 60_000,
      env: { REDEEM_DATABASE_URL: "sqlite:////tmp/redeem-e2e.db", REDEEM_REGISTER_RATE_LIMIT: "1000" },
    },
    { command: "npx next start -p 3000", cwd: ".", url: "http://127.0.0.1:3000", reuseExistingServer: true, timeout: 60_000 },
  ],
});
