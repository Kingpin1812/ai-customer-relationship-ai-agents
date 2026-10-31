import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const root = path.resolve(__dirname, "..");
const python =
  process.platform === "win32"
    ? path.join(root, "backend", ".venv", "Scripts", "python.exe")
    : path.join(root, "backend", ".venv", "bin", "python");

export default defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
    launchOptions: { args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] },
  },
  webServer: {
    command: `"${python}" "${path.join(root, "scripts", "run_local.py")}" --production-web`,
    url: "http://localhost:3100/login",
    reuseExistingServer: false,
    timeout: 240_000,
    env: {
      LOCAL_DATA_DIR: path.join(root, ".local", "e2e"),
      API_PORT: "8100",
      WEB_PORT: "3100",
      BACKEND_URL: "http://127.0.0.1:8100",
      PLANNER_MODE: "rules",
    },
  },
});
