import { expect, test } from "@playwright/test";

// OPS-03 (analys_and_todo.md): диспетчер с доступом только к объекту A не должен видеть
// риск-кейс объекта B ни в списке, ни получить его напрямую по ID (403). Данные —
// scripts/demo/seed_e2e_fixtures.py (dispatcher-a привязан только к object_a).
test("диспетчер объекта A не видит риск-кейс объекта B в списке", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Логин").fill("dispatcher-a");
  await page.getByLabel("Пароль").fill("dispatcher-a-pass");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("navigation").getByRole("link", { name: "Риски" })).toBeVisible();

  await page.getByRole("navigation").getByRole("link", { name: "Риски" }).click();
  await expect(page.getByText("E2E Насос A")).toBeVisible();
  await expect(page.getByText("E2E Насос B")).not.toBeVisible();
});

test("диспетчер объекта A получает 403 при прямом запросе риска объекта B", async ({ page, request }) => {
  await page.goto("/");
  await page.getByLabel("Логин").fill("dispatcher-a");
  await page.getByLabel("Пароль").fill("dispatcher-a-pass");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("navigation").getByRole("link", { name: "Риски" })).toBeVisible();

  const token = await page.evaluate(() => localStorage.getItem("jkh_token"));
  expect(token).toBeTruthy();

  // Риск-кейс объекта B создаётся вторым в seed_e2e_fixtures.py (risk_b) — id найден по
  // фильтру канала, не захардкожен, т.к. может отличаться при повторных прогонах фикстур
  // на разных БД.
  const asAdmin = await request.post("/api/auth/login", {
    form: { username: "admin", password: "demo-local-2026" },
  });
  const adminToken = (await asAdmin.json()).access_token as string;
  const riskList = await request.get("/api/risk-cases?limit=500", {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
  const risks = (await riskList.json()) as { id: number; channel_label: string | null }[];
  const riskB = risks.find((r) => r.channel_label === "E2E Насос B");
  expect(riskB).toBeTruthy();

  const denied = await request.post(`/api/risk-cases/${riskB!.id}/decisions`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { action: "observe" },
  });
  expect(denied.status()).toBe(403);
});
