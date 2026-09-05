import { expect, test } from "@playwright/test";

const learnerPassword = process.env.ACADEMY_PASSWORD ?? "Learn-ModelN-2026";

test("learner can enter, explore a mission, and use the evidence atlas", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await page.getByLabel("Username").fill("kelvin");
  await page.getByLabel("Password").fill(learnerPassword);
  await page.getByRole("button", { name: "Start learning" }).click();

  await expect(page.getByRole("heading", { name: "Systems Adventure" })).toBeVisible();
  await expect(page.getByText("Seven worlds")).toBeVisible();
  await page.waitForTimeout(400);
  await page.screenshot({ path: "artifacts/dashboard-desktop.png", fullPage: true });

  await page.getByRole("button", { name: /Begin mission/ }).click();
  await page.getByRole("button", { name: /Why this matters/ }).click();
  await expect(page.getByRole("heading", { name: "Why this matters" })).toBeVisible();
  await page.getByRole("button", { name: /See the boundaries/ }).click();
  await expect(page.getByText(/Read the cited evidence/)).toBeVisible();
  await page.screenshot({ path: "artifacts/mission-explore.png", fullPage: true });

  await page.getByRole("button", { name: "Back to campaign" }).click();
  await page.getByRole("button", { name: "Evidence atlas" }).first().click();
  await page.getByRole("searchbox").fill("SAP_P4S_DIRECTSALES");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText(/FGI 205/).first()).toBeVisible();
});

test("theme selection persists across a signed-in reload", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");

  const loginTheme = page.getByRole("group", { name: "Color theme" });
  await expect(loginTheme).toBeVisible();
  await loginTheme.getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.getByLabel("Username").fill("kelvin");
  await page.getByLabel("Password").fill(learnerPassword);
  await page.getByRole("button", { name: "Start learning" }).click();
  await expect(page.getByRole("heading", { name: "Systems Adventure" })).toBeVisible();

  const academyTheme = page.getByRole("group", { name: "Color theme" }).filter({ visible: true });
  await expect(academyTheme).toBeVisible();
  await expect(academyTheme.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("heading", { name: "Systems Adventure" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Color theme" }).filter({ visible: true }).getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("group", { name: "Color theme" }).filter({ visible: true }).getByRole("button", { name: "Light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("campaign remains usable at a phone viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Username").fill("kelvin");
  await page.getByLabel("Password").fill(learnerPassword);
  await page.getByRole("button", { name: "Start learning" }).click();

  await expect(page.getByRole("heading", { name: "Systems Adventure" })).toBeVisible();
  await expect(page.getByLabel("Academy sections").last()).toBeVisible();
  await expect(page.getByRole("group", { name: "Color theme" }).filter({ visible: true })).toBeVisible();
  await page.screenshot({ path: "artifacts/dashboard-mobile.png", fullPage: true });
});
