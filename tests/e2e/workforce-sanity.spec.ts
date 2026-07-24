import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import {
  expect,
  type ElementHandle,
  type Locator,
  type Page,
  type Response,
  type TestInfo,
  test,
} from "@playwright/test";

/**
 * Run:
 *   E2E_BASE_URL=http://127.0.0.1:5173 npx playwright test tests/e2e/workforce-sanity.spec.ts
 *
 * Precondition:
 *   Vite frontend, FastAPI backend, and MongoDB are running. The AI alert flow
 *   upserts its own e2e_* Pending overload fixture before opening /alerts.
 */
const APP_BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const SCREENSHOT_DIR =
  process.env.E2E_SCREENSHOT_DIR ??
  path.join(process.cwd(), "test-results", "e2e-screenshots");

const MANAGER = { username: "manager_01", password: "password123" };
const STAFF = { username: "staff_a1", password: "password123" };
const AUTH_LOGIN_ENDPOINT = "/api/v1/auth/login";
const TASK_CONTROL_FIXTURE_CODE = "E2E-TASK";
const LOCAL_VENV_PYTHON = path.join(process.cwd(), "venv", "Scripts", "python.exe");
const E2E_FIXTURE_PYTHON =
  process.env.E2E_FIXTURE_PYTHON ??
  process.env.PYTHON ??
  (fs.existsSync(LOCAL_VENV_PYTHON) ? LOCAL_VENV_PYTHON : "python");

test.use({
  baseURL: APP_BASE_URL,
  storageState: { cookies: [], origins: [] },
  viewport: { width: 1440, height: 960 },
  trace: "retain-on-failure",
});

test.describe.configure({ mode: "serial" });
test.setTimeout(60_000);

function sanitizeSegment(value: string): string {
  const normalized = value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");

  return normalized.slice(0, 140) || "workforce_sanity";
}

function screenshotPath(testInfo: TestInfo, state: "PASSED" | "FAILED", step: string) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

  const testName = sanitizeSegment(testInfo.title);
  const stepName = sanitizeSegment(step);

  return path.join(SCREENSHOT_DIR, `${testName}_${state}_${stepName}.png`);
}

class ScreenshotRecorder {
  private stepNumber = 0;

  constructor(
    private readonly page: Page,
    private readonly testInfo: TestInfo,
  ) {}

  async passed(step: string, target?: Locator) {
    this.stepNumber += 1;
    const filePath = screenshotPath(
      this.testInfo,
      "PASSED",
      `${String(this.stepNumber).padStart(2, "0")}_${step}`,
    );

    const screenshotTarget = target ?? this.page.locator("body");
    await expect(screenshotTarget).toBeVisible({ timeout: 15_000 });
    await screenshotTarget.screenshot({ path: filePath });
    await this.testInfo.attach(path.basename(filePath), {
      path: filePath,
      contentType: "image/png",
    });
  }
}

test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status === testInfo.expectedStatus) {
    return;
  }

  const filePath = screenshotPath(testInfo, "FAILED", "after_each_full_page");
  try {
    if (page.isClosed()) {
      return;
    }

    await page.screenshot({ path: filePath, fullPage: true, timeout: 5_000 });
    await testInfo.attach(path.basename(filePath), {
      path: filePath,
      contentType: "image/png",
    });
  } catch (error) {
    await testInfo.attach("failed-screenshot-error.txt", {
      body: String(error),
      contentType: "text/plain",
    });
  }
});

async function clearClientAuth(page: Page) {
  await page.context().clearCookies();

  if (page.url() === "about:blank") {
    return;
  }

  try {
    if (new URL(page.url()).origin !== new URL(APP_BASE_URL).origin) {
      return;
    }

    await page.evaluate(() => {
      localStorage.removeItem("auth_token");
      localStorage.removeItem("auth_user");
      sessionStorage.clear();
    });
  } catch {
    // The next navigation starts from an empty storageState, so a best-effort
    // clear is enough when the current document is already gone.
  }
}

async function setReloadGuard(page: Page) {
  return page.evaluate(() => {
    const token = `reload-guard-${Date.now()}-${Math.random()}`;
    (window as Window & { __WORKFORCE_E2E_RELOAD_GUARD__?: string }).__WORKFORCE_E2E_RELOAD_GUARD__ =
      token;
    return token;
  });
}

async function expectNoFullPageReload(page: Page, guardToken: string) {
  const currentToken = await page.evaluate(
    () =>
      (window as Window & { __WORKFORCE_E2E_RELOAD_GUARD__?: string })
        .__WORKFORCE_E2E_RELOAD_GUARD__ ?? null,
  );
  expect(currentToken).toBe(guardToken);
}

function runPythonFixture(scriptName: string, failureMessage: string) {
  const fixtureScript = path.join(
    process.cwd(),
    "scripts",
    scriptName,
  );

  try {
    execFileSync(E2E_FIXTURE_PYTHON, [fixtureScript], {
      cwd: process.cwd(),
      env: process.env,
      stdio: "pipe",
    });
  } catch (error) {
    const execError = error as {
      message?: string;
      stdout?: Buffer;
      stderr?: Buffer;
    };

    throw new Error(
      [
        failureMessage,
        `Command: ${E2E_FIXTURE_PYTHON} ${fixtureScript}`,
        execError.message,
        execError.stdout?.toString(),
        execError.stderr?.toString(),
      ]
        .filter(Boolean)
        .join("\n"),
    );
  }
}

function ensureTaskControlFixture() {
  runPythonFixture(
    "ensure_e2e_task.py",
    "Không thể tạo fixture hồ sơ Đang xử lý cho Task Control Center E2E test.",
  );
}

function ensureAIOverloadFixture() {
  runPythonFixture(
    "ensure_e2e_overload.py",
    "Không thể tạo fixture Pending overload cho AI E2E test.",
  );
}

async function waitForLoginResponseAfter(
  page: Page,
  action: () => Promise<unknown>,
): Promise<Response> {
  const loginResponse = page.waitForResponse(
    (res) =>
      res.url().includes(AUTH_LOGIN_ENDPOINT) &&
      res.request().method() === "POST",
    { timeout: 10_000 },
  );

  const loginRequestFailure = page
    .waitForEvent("requestfailed", {
      predicate: (request) => request.url().includes(AUTH_LOGIN_ENDPOINT),
      timeout: 10_000,
    })
    .then((request) => {
      const failure = request.failure()?.errorText ?? "unknown browser/network error";
      throw new Error(
        `Login API request failed before a POST response was received: ${request.method()} ${request.url()} - ${failure}. Check FastAPI CORS, backend port, and VITE_API_BASE_URL.`,
      );
    })
    .catch((error) => {
      if (String(error).includes("Timeout")) {
        return new Promise<never>(() => undefined);
      }

      throw error;
    });

  const [response] = await Promise.all([
    Promise.race([loginResponse, loginRequestFailure]),
    action(),
  ]);

  return response;
}

class LoginPage {
  constructor(private readonly page: Page) {}

  readonly heading = this.page.getByRole("heading", { name: "Đăng nhập" });
  readonly username = this.page.getByLabel("Username");
  readonly password = this.page.getByLabel("Password");
  readonly submit = this.page.getByRole("button", { name: "Đăng nhập" });
  readonly alert = this.page.getByRole("alert");

  async open() {
    await this.page.goto("/login", { waitUntil: "domcontentloaded" });
    await expect(this.heading).toBeVisible();
  }

  async fillCredentials(username: string, password: string) {
    await this.username.fill(username);
    await this.password.fill(password);
  }

  async loginExpectSuccess(username: string, password: string) {
    await this.fillCredentials(username, password);

    const response = await waitForLoginResponseAfter(this.page, () =>
      this.submit.click(),
    );

    expect(response.ok()).toBeTruthy();
  }

  async loginExpectUnauthorized(username: string, password: string) {
    await this.fillCredentials(username, password);

    const response = await waitForLoginResponseAfter(this.page, () =>
      this.submit.click(),
    );

    expect(response.status()).toBe(401);
    await expect(this.alert).toContainText("Tài khoản hoặc mật khẩu không chính xác");
  }
}

class AppSession {
  constructor(
    private readonly page: Page,
    private readonly recorder: ScreenshotRecorder,
  ) {}

  async loginAsManager(stepName = "manager_login_redirect_dashboard") {
    const login = new LoginPage(this.page);
    await clearClientAuth(this.page);
    await login.open();
    await login.loginExpectSuccess(MANAGER.username, MANAGER.password);
    await expect(this.page).toHaveURL(/\/dashboard(?:$|[?#])/);
    await expect(
      this.page.getByRole("heading", { name: "Dashboard tải lượng nhân sự" }),
    ).toBeVisible();
    await this.recorder.passed(stepName, this.page.locator("body"));
  }
}

class DashboardPage {
  constructor(
    private readonly page: Page,
    private readonly recorder: ScreenshotRecorder,
  ) {}

  readonly heatmap = this.page.locator("section").filter({
    has: this.page.getByRole("heading", { name: "Bản đồ tải lượng nhân sự" }),
  });

  async open() {
    await this.page.goto("/dashboard", { waitUntil: "domcontentloaded" });
    await expect(
      this.page.getByRole("heading", { name: "Dashboard tải lượng nhân sự" }),
    ).toBeVisible();
    await expect(
      this.page.getByRole("heading", { name: "Bản đồ tải lượng nhân sự" }),
    ).toBeVisible({ timeout: 15_000 });
  }

  async assertProgressTones() {
    await expect(this.page.locator(".bg-green-500").first()).toBeVisible();
    await expect(this.page.locator(".bg-yellow-500").first()).toBeVisible();

    const overloadedStaff = this.page
      .locator("article")
      .filter({ hasText: /Hoàng Thị Cúc|staff_a4/ })
      .first();

    await expect(overloadedStaff).toBeVisible();
    await expect(
      overloadedStaff.locator(".bg-red-500.animate-pulse").first(),
    ).toBeVisible();
  }

  async captureHeatmap() {
    await this.recorder.passed("heatmap_staff_a4_red_pulse", this.heatmap.first());
  }

  async captureTotalRunningTasksWidget() {
    const widget = this.page
      .locator("section")
      .filter({ hasText: "Tác vụ đang chạy hôm nay" })
      .first();
    await expect(widget).toBeVisible();

    const valueText = (await widget.locator("p").nth(1).innerText()).trim();
    expect(valueText).toMatch(/^\d+$/);

    await this.recorder.passed("widget_total_running_tasks", widget);
  }
}

class TaskCenterPage {
  constructor(
    private readonly page: Page,
    private readonly recorder: ScreenshotRecorder,
  ) {}

  readonly statusFilter = this.page.getByLabel("Trạng thái");
  readonly departmentFilter = this.page.getByLabel("Phòng ban");
  readonly table = this.page.locator("table");
  readonly processingRows = this.page
    .locator("tbody tr")
    .filter({ hasText: "Đang xử lý" });
  readonly drawer = this.page
    .locator(".fixed.inset-0 aside")
    .filter({ hasText: "Hồ sơ" });
  readonly successToast = this.page.getByRole("status").filter({
    hasText: "Luân chuyển bước thành công.",
  });

  async open() {
    await this.page.goto("/tasks", { waitUntil: "domcontentloaded" });
    await expect(
      this.page.getByRole("heading", { name: "Trung tâm quản lý hồ sơ" }),
    ).toBeVisible();
    await this.waitForTableLoaded();
  }

  async waitForTableLoaded() {
    await expect(this.page.getByText("Đang tải danh sách hồ sơ")).toHaveCount(0, {
      timeout: 15_000,
    });
  }

  async applyProcessingFilters(taskCode = TASK_CONTROL_FIXTURE_CODE) {
    await this.statusFilter.selectOption("Đang xử lý");
    await this.departmentFilter.selectOption("A");
    await this.waitForTableLoaded();

    const targetRows = this.processingRows.filter({ hasText: taskCode });
    if ((await targetRows.count()) === 0) {
      await this.departmentFilter.selectOption("Tất cả");
      await this.waitForTableLoaded();
    }

    await expect(this.processingRows.filter({ hasText: taskCode }).first()).toBeVisible();
    await this.recorder.passed(
      "filters_status_processing_department",
      this.page.locator("section").filter({ hasText: "Trạng thái" }).first(),
    );
  }

  async openFirstProcessingTaskDetail(taskCode = TASK_CONTROL_FIXTURE_CODE) {
    const row = this.processingRows.filter({ hasText: taskCode }).first();
    await expect(row).toBeVisible();

    const visibleTaskCode = (await row.locator("td").first().innerText()).trim();
    const beforeRowText = (await row.innerText()).trim();

    await row.getByRole("button", { name: "Xem chi tiết" }).click();
    await expect(this.drawer).toBeVisible();
    await expect(
      this.drawer.getByText(/Hoàn thành:|Chưa có dữ liệu tiến trình/).first(),
    ).toBeVisible();
    await this.recorder.passed("task_timeline_drawer", this.drawer);

    return { taskCode: visibleTaskCode, beforeRowText };
  }

  async completeCurrentStep(taskCode: string, beforeRowText: string) {
    const reloadGuard = await setReloadGuard(this.page);
    const completeButton = this.drawer.getByRole("button", {
      name: "Hoàn thành bước hiện tại",
    });

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (res) =>
          res.url().includes("/api/v1/tasks/") &&
          res.url().includes("/next-step") &&
          res.request().method() === "POST",
      ),
      completeButton.click(),
    ]);

    expect(response.ok()).toBeTruthy();
    await expect(this.successToast).toBeVisible({ timeout: 15_000 });
    await this.recorder.passed("task_next_step_success_toast", this.successToast);

    await expect(this.drawer).toHaveCount(0);
    await this.waitForTableLoaded();
    await expectNoFullPageReload(this.page, reloadGuard);

    const visibleRows = this.page.locator("tbody tr");
    const changedOrRemoved = await visibleRows.evaluateAll(
      (rows, args) => {
        const { code, before } = args as { code: string; before: string };
        const matching = rows.find((row) => row.textContent?.includes(code));
        return !matching || matching.textContent?.trim() !== before;
      },
      { code: taskCode, before: beforeRowText },
    );
    expect(changedOrRemoved).toBeTruthy();

    await this.recorder.passed("task_table_updated_no_reload", this.table);
  }
}

class AlertsPage {
  constructor(
    private readonly page: Page,
    private readonly recorder: ScreenshotRecorder,
  ) {}

  readonly alertCards = this.page.locator("article").filter({
    hasText: "Cần điều phối",
  });
  readonly aiModal = this.page
    .locator("section")
    .filter({ hasText: "AI-powered Decision Support" })
    .first();
  readonly successToast = this.page.getByRole("status").filter({
    hasText: "Đã luân chuyển hồ sơ thành công!",
  });

  async open() {
    await this.page.goto("/alerts", { waitUntil: "domcontentloaded" });
    await expect(this.page.getByRole("heading", { name: "Cảnh báo hệ thống" })).toBeVisible();
    await expect(this.page.getByText("Đang chờ xử lý")).toBeVisible();
  }

  async assertAmberAlertsAndCaptureList() {
    const firstCard = this.alertCards.first();
    await expect(firstCard).toBeVisible({ timeout: 15_000 });
    await expect(firstCard).toHaveClass(/border-amber-200/);
    await expect(firstCard).toHaveClass(/bg-amber-50/);
    await this.recorder.passed("amber_alert_list", this.page.locator("main"));
  }

  async openFirstAIResolutionModal() {
    const firstCard = this.alertCards.first();
    await expect(firstCard).toBeVisible();

    const firstCardHandle = await firstCard.elementHandle();
    if (!firstCardHandle) {
      throw new Error("Không lấy được DOM handle của thẻ Cảnh báo đầu tiên.");
    }

    await firstCard.getByRole("button", { name: "Xử lý điều phối" }).click();
    await expect(this.aiModal).toBeVisible();

    const firstCandidate = this.aiModal.locator("article").first();
    await expect(firstCandidate).toBeVisible();

    const matchingScore = (
      await firstCandidate.getByText(/^\d+% Phù hợp$/).innerText()
    ).trim();
    expect(matchingScore).toMatch(/^\d+% Phù hợp$/);

    await this.recorder.passed("ai_popup_matching_score", this.aiModal);
    return firstCardHandle;
  }

  async approveFirstSuggestionAndAssertCardRemoved(
    firstCardHandle: ElementHandle<SVGElement | HTMLElement>,
  ) {
    const reloadGuard = await setReloadGuard(this.page);
    const firstCandidate = this.aiModal.locator("article").first();
    const approveButton = firstCandidate.getByRole("button", {
      name: "Phê duyệt điều chuyển",
    });

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (res) =>
          res.url().includes("/api/v1/analytics/overloads/") &&
          res.url().includes("/resolve") &&
          res.request().method() === "POST",
      ),
      approveButton.click(),
    ]);

    expect(response.ok()).toBeTruthy();
    await expect(this.successToast).toBeVisible({ timeout: 15_000 });
    await this.recorder.passed("ai_approve_success_toast", this.successToast);

    await expect(this.aiModal).toHaveCount(0);
    await this.page.waitForFunction(
      (element) => !document.body.contains(element as Element),
      firstCardHandle,
      { timeout: 10_000 },
    );
    await expectNoFullPageReload(this.page, reloadGuard);
    await this.recorder.passed(
      "alert_card_removed_no_reload",
      this.page.locator("main"),
    );
  }
}

test.describe("AI-powered Workforce Management Sanity Check", () => {
  test("Auth_Route_Guard_sanity", async ({ page }, testInfo) => {
    const recorder = new ScreenshotRecorder(page, testInfo);
    const login = new LoginPage(page);

    await clearClientAuth(page);
    await page.goto("/dashboard", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/login(?:$|[?#])/);
    await expect(login.heading).toBeVisible();
    await recorder.passed(
      "unauthenticated_dashboard_redirect_login",
      page.locator("body"),
    );

    await login.loginExpectUnauthorized(MANAGER.username, "wrong-password");
    await recorder.passed("invalid_password_error_form", page.locator(".login-form"));

    await clearClientAuth(page);
    await login.open();
    await login.loginExpectSuccess(STAFF.username, STAFF.password);
    await expect(page).toHaveURL(/\/login(?:$|[?#])/);

    const storedCredentials = await page.evaluate(() => {
      return {
        token: localStorage.getItem("auth_token"),
        user: localStorage.getItem("auth_user"),
      };
    });
    expect(storedCredentials).toEqual({ token: null, user: null });

    await page.goto("/tasks", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/login(?:$|[?#])/);
    await expect(page.getByRole("link", { name: "Danh sách Hồ sơ" })).toHaveCount(
      0,
    );
    await expect(page.getByRole("link", { name: "Cảnh báo Quá tải" })).toHaveCount(
      0,
    );
    await recorder.passed("staff_blocked_manager_features", page.locator("body"));

    await clearClientAuth(page);
    await login.open();
    await login.loginExpectSuccess(MANAGER.username, MANAGER.password);
    await expect(page).toHaveURL(/\/dashboard(?:$|[?#])/);
    await expect(
      page.getByRole("heading", { name: "Dashboard tải lượng nhân sự" }),
    ).toBeVisible();
    await recorder.passed("manager_login_dashboard_success", page.locator("body"));
  });

  test("Dashboard_Workload_Heatmap_sanity", async ({ page }, testInfo) => {
    const recorder = new ScreenshotRecorder(page, testInfo);
    const session = new AppSession(page, recorder);
    const dashboard = new DashboardPage(page, recorder);

    await session.loginAsManager();
    await dashboard.open();
    await dashboard.assertProgressTones();
    await dashboard.captureHeatmap();
    await dashboard.captureTotalRunningTasksWidget();
  });

  test("Task_Control_Center_state_machine_sanity", async ({ page }, testInfo) => {
    const recorder = new ScreenshotRecorder(page, testInfo);
    const session = new AppSession(page, recorder);
    const tasks = new TaskCenterPage(page, recorder);

    ensureTaskControlFixture();
    await session.loginAsManager();
    await tasks.open();
    await tasks.applyProcessingFilters(TASK_CONTROL_FIXTURE_CODE);
    const { taskCode, beforeRowText } =
      await tasks.openFirstProcessingTaskDetail(TASK_CONTROL_FIXTURE_CODE);
    await tasks.completeCurrentStep(taskCode, beforeRowText);
  });

  test("AI_Overload_Mitigation_sanity", async ({ page }, testInfo) => {
    const recorder = new ScreenshotRecorder(page, testInfo);
    const session = new AppSession(page, recorder);
    const alerts = new AlertsPage(page, recorder);

    ensureAIOverloadFixture();
    await session.loginAsManager();
    await alerts.open();
    await alerts.assertAmberAlertsAndCaptureList();
    const firstCardHandle = await alerts.openFirstAIResolutionModal();
    await alerts.approveFirstSuggestionAndAssertCardRemoved(firstCardHandle);
  });
});
