import { defineConfig, devices } from "@playwright/test";

// OPS-03 (analys_and_todo.md): backend/frontend должны быть уже подняты отдельно (см.
// e2e/README.md) — данные (scripts/demo/seed_e2e_fixtures.py) требуют конкретной БД,
// поднимать весь стек внутри одной команды playwright test не стал: тот же паттерн
// "поднять сервер сам" уже давал хрупкие тесты в других проектах при параллельном запуске.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:58030",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
