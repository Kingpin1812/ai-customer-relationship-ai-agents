import { expect, type Page, test } from "@playwright/test";

const REQUEST =
  "Prepare an invoice for Acme Ltd for 10 hours of approved consulting at ₹2,500 per hour, update the CRM note, generate this month's sales summary, and prepare an email.";

async function signIn(page: Page, name: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

async function submit(page: Page, request = REQUEST, simulate?: string) {
  await page.goto("/workflows/new");
  await page.getByLabel("Request", { exact: true }).fill(request);
  if (simulate) await page.getByLabel("Simulate a failure").selectOption(simulate);
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page).toHaveURL(/\/workflows\/[0-9a-f-]{36}$/);
  return page.url();
}

async function sentCount(page: Page) {
  await page.goto("/outbox");
  const text = await page.getByText(/has received \d+ message/).textContent();
  return Number(/received (\d+)/.exec(text ?? "")?.[1]);
}

test("reject sends nothing, then approve sends exactly one email", async ({ page }) => {
  await signIn(page, "Maya Manager");
  const before = await sentCount(page);

  // First run: rejected.
  const rejected = await submit(page);
  await page.getByRole("link", { name: "Review and decide" }).click();
  await expect(page.getByRole("definition").getByText("billing@acme-ltd.example")).toBeVisible();
  await expect(page.getByText("₹29,500.00")).toBeVisible();
  await expect(page.getByRole("button", { name: "Reject" })).toBeDisabled();
  await page.getByLabel(/Reason/).fill("Wrong month");
  await page.getByRole("button", { name: "Reject" }).click();
  await expect(page).toHaveURL(rejected);
  await expect(page.getByText("Rejected: Wrong month")).toBeVisible();
  expect(await sentCount(page)).toBe(before);

  // Second run: approved.
  const approved = await submit(page);
  await page.getByRole("link", { name: "Review and decide" }).click();
  await page.getByRole("button", { name: "Approve and run" }).click();
  await expect(page).toHaveURL(approved);
  await expect(page.getByTestId("timeline").getByText("Complete")).toBeVisible();
  await expect(page.getByText("Provider message ID")).toBeVisible();
  expect(await sentCount(page)).toBe(before + 1);

  // Every step and decision is on the audit page.
  await page.goto(`/audit?workflow_id=${approved.split("/").pop()}`);
  for (const action of ["workflow.created", "approval.approved", "integration.send_email", "workflow.succeeded"]) {
    await expect(page.getByRole("cell", { name: action, exact: true }).first()).toBeVisible();
  }
});

test("an operator submits work but gets no approval controls", async ({ page }) => {
  await signIn(page, "Omar Operator");
  await submit(page);
  await page.getByRole("link", { name: "View request" }).click();
  await expect(page.getByTestId("no-approve-permission")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve and run" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Settings" })).toHaveCount(0);
});

test("a viewer cannot start work", async ({ page }) => {
  await signIn(page, "Vik Viewer");
  await expect(page.getByRole("link", { name: "New workflow" })).toHaveCount(0);
  await page.goto("/workflows/new");
  await expect(page.getByText("Your role can view workflows but not submit them.")).toBeVisible();
});

test("a CRM timeout is retried and recovers, and the attempts are visible", async ({ page }) => {
  await signIn(page, "Maya Manager");
  await submit(page, REQUEST, "crm_timeout");
  await expect(page.getByRole("link", { name: "Review and decide" })).toBeVisible();
  const row = page.getByRole("row", { name: /Search customer/ });
  await expect(row).toContainText("Succeeded");
  await expect(row.getByRole("cell", { name: "3", exact: true })).toBeVisible();
});

test("an ambiguous customer stops and asks", async ({ page }) => {
  await signIn(page, "Maya Manager");
  await submit(page, "Prepare an invoice for Acme for 1 hour of consulting at ₹100 per hour");
  await expect(page.getByText("More information needed")).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "More information needed" })).toContainText("Acme Logistics");
});

test("the 3D view draws a real scene and sits above the readable timeline", async ({ page }) => {
  await signIn(page, "Maya Manager");
  await expect(page.locator("[data-testid=scene-3d] canvas")).toBeVisible();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "test-results/overview.png", fullPage: true });

  await submit(page);
  await expect(page.getByRole("link", { name: "Review and decide" })).toBeVisible();
  await expect(page.locator("[data-testid=scene-3d] canvas")).toBeVisible();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: "test-results/workflow-gate.png", fullPage: true });
  await expect(page.locator("[data-testid=scene-3d] .sr-only")).toContainText("Approval gate");
});

test("without WebGL the page still works and says so", async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: string, ...rest: unknown[]) {
      if (type.startsWith("webgl")) return null;
      return (original as (...args: unknown[]) => unknown).call(this, type, ...rest);
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
  await signIn(page, "Maya Manager");
  await expect(page.getByText("3D is not available on this device.")).toBeVisible();
  await submit(page);
  await expect(page.getByTestId("timeline")).toBeVisible();
  await expect(page.getByRole("link", { name: "Review and decide" })).toBeVisible();
});

test("reduced motion keeps everything usable", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await signIn(page, "Maya Manager");
  await submit(page);
  await expect(page.getByTestId("timeline")).toBeVisible();
  await expect(page.locator("[data-testid=scene-3d] canvas")).toBeVisible();
});

test("the 3D view can be turned off, and the choice is remembered", async ({ page }) => {
  await signIn(page, "Maya Manager");
  await page.getByRole("button", { name: "Hide 3D" }).click();
  await expect(page.locator("[data-testid=scene-3d] canvas")).toHaveCount(0);
  await expect(page.getByTestId("scene-3d")).toContainText("workflows in total");
  await page.reload();
  await expect(page.getByRole("button", { name: "Show 3D" })).toBeVisible();
  await page.getByRole("button", { name: "Show 3D" }).click();
});

test("no sideways scrolling at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "Maya Manager");
  await page.waitForTimeout(800);
  const overflow = () =>
    page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(await overflow()).toBeLessThanOrEqual(0);
  await page.screenshot({ path: "test-results/phone-overview.png" });
  await submit(page);
  await expect(page.getByTestId("timeline")).toBeVisible();
  await page.waitForTimeout(800);
  expect(await overflow()).toBeLessThanOrEqual(0);
  await page.screenshot({ path: "test-results/phone-workflow.png", fullPage: true });
  await page.getByRole("link", { name: "Review and decide" }).click();
  await expect(page.getByRole("button", { name: "Approve and run" })).toBeVisible();
  expect(await overflow()).toBeLessThanOrEqual(0);
  for (const path of ["/workflows", "/approvals", "/invoices", "/reports", "/integrations", "/audit", "/outbox"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForTimeout(400);
    expect(await overflow(), path).toBeLessThanOrEqual(0);
  }
});

test("a keyboard user can reach the main navigation", async ({ page }) => {
  await signIn(page, "Maya Manager");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Overview" })).toBeFocused();
});

async function expectReadableLabels(page: Page, expected: number) {
  const scene = page.getByTestId("scene-3d");
  await expect(scene.locator(".scene-label")).toHaveCount(expected);
  await page.waitForTimeout(1500);
  const result = await page.evaluate(() => {
    const frame = document.querySelector("[data-testid=scene-3d]")!.getBoundingClientRect();
    const boxes = [...document.querySelectorAll(".scene-label")].map((el) => ({
      text: el.textContent ?? "",
      box: el.getBoundingClientRect(),
    }));
    const outside = boxes
      .filter(({ box }) => box.left < frame.left || box.right > frame.right || box.top < frame.top || box.bottom > frame.bottom)
      .map((b) => b.text);
    const overlapping: string[] = [];
    boxes.forEach((a, i) =>
      boxes.slice(i + 1).forEach((b) => {
        if (a.box.left < b.box.right && b.box.left < a.box.right && a.box.top < b.box.bottom && b.box.top < a.box.bottom) {
          overlapping.push(`${a.text} / ${b.text}`);
        }
      }),
    );
    return { outside, overlapping };
  });
  expect(result).toEqual({ outside: [], overlapping: [] });
}

for (const [name, viewport] of [
  ["desktop", { width: 1280, height: 800 }],
  ["phone", { width: 390, height: 844 }],
] as const) {
  test(`3D labels are all in frame and never overlap on ${name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await signIn(page, "Maya Manager");
    await expectReadableLabels(page, 8);
    await page.screenshot({ path: `test-results/${name}-system.png` });
    await submit(page);
    await expect(page.getByRole("link", { name: "Review and decide" })).toBeVisible();
    await expectReadableLabels(page, 8);
    await page.getByTestId("scene-3d").screenshot({ path: `test-results/${name}-scene.png` });
  });
}

test.describe("west of UTC", () => {
  test.use({ timezoneId: "America/New_York" });

  test("the approval page shows the invoice's real due date", async ({ page }) => {
    const due = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
    const expected = due.toLocaleDateString("en-US", { dateStyle: "medium" });
    await signIn(page, "Maya Manager");
    await submit(page);
    await page.getByRole("link", { name: "Review and decide" }).click();
    await expect(page.getByRole("definition").getByText(expected, { exact: true })).toBeVisible();
  });
});
