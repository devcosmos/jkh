import { expect, test } from "@playwright/test";

test("вход администратора показывает основной интерфейс", async ({ page }) => {
  await page.goto("/");
  // Форма логина предзаполнена демо-доступом (LoginPage.tsx) — просто отправляем.
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("navigation").getByRole("link", { name: "Риски" })).toBeVisible();
});

test("неверный пароль показывает ошибку, не пускает внутрь", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Пароль").fill("совсем-не-тот-пароль");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByText("Неверный логин или пароль")).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("link", { name: "Риски" })).not.toBeVisible();
});
