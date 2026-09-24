import { expect, test } from "@playwright/test";

// OPS-03 (analys_and_todo.md): основной сценарий — открыть риск-кейс, принять решение
// диспетчера «направить на проверку», убедиться, что появилась заявка на обслуживание.
// Данные — scripts/demo/seed_e2e_fixtures.py (риск-кейс на канале "E2E Насос A").
test("направить риск на проверку создаёт заявку", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("navigation").getByRole("link", { name: "Риски" })).toBeVisible();

  await page.getByRole("navigation").getByRole("link", { name: "Риски" }).click();
  await expect(page.getByText("E2E Насос A")).toBeVisible();
  await page.getByText("E2E Насос A").click();

  await expect(page.getByRole("heading", { name: /Риск-кейс #/ })).toBeVisible();
  await page.getByRole("button", { name: "Направить на проверку" }).click();
  await expect(page.getByText(/Решение сохранено: «Направить на проверку»/)).toBeVisible();
  await expect(
    page.getByText("По этому риску уже создана и ведётся заявка на обслуживание")
  ).toBeVisible();

  await page.getByRole("navigation").getByRole("link", { name: "Заявки" }).click();
  await expect(page.getByText("Диагностика и ТО насоса")).toBeVisible();
});
