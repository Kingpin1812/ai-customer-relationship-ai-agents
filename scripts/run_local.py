"""Run the whole app on Windows without Docker: PostgreSQL, migrations, seed, API and web UI.

Run from the project root:
    backend\\.venv\\Scripts\\python.exe scripts\\run_local.py

Options:
    --api-only          do not start the web UI
    --production-web    serve the built frontend (run `npm run build` first)
Press Ctrl+C to stop everything.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pixeltable_pgserver

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
LOCAL = Path(os.environ.get("LOCAL_DATA_DIR", ROOT / ".local"))
API_PORT = os.environ.get("API_PORT", "8000")
WEB_PORT = os.environ.get("WEB_PORT", "3000")


def wait_for(url: str, name: str, timeout: float = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3):  # noqa: S310 - fixed localhost URL
                print(f"[ok] {name} is ready: {url}", flush=True)
                return
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    raise SystemExit(f"{name} did not start within {timeout:.0f} seconds. See the output above.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--production-web", action="store_true")
    args = parser.parse_args()

    LOCAL.mkdir(parents=True, exist_ok=True)
    print("[..] Starting embedded PostgreSQL", flush=True)
    postgres = pixeltable_pgserver.get_server(str(LOCAL / "pgdata"), cleanup_mode="stop")
    env = {
        **os.environ,
        "DATABASE_URL": postgres.get_uri().replace("postgresql://", "postgresql+psycopg://", 1),
        "ENVIRONMENT": os.environ.get("ENVIRONMENT", "development"),
        "AUTH_MODE": "dev",
        "TASK_EXECUTOR": "thread",
        "STORAGE_BACKEND": "local",
        "STORAGE_LOCAL_PATH": str(LOCAL / "artifacts"),
        "ENABLE_FAULT_INJECTION": os.environ.get("ENABLE_FAULT_INJECTION", "true"),
        "CORS_ORIGINS": f"http://localhost:{WEB_PORT}",
        "BACKEND_URL": f"http://127.0.0.1:{API_PORT}",
        "PYTHONUTF8": "1",
    }
    processes: list[subprocess.Popen] = []
    try:
        print("[..] Applying migrations", flush=True)
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True
        )
        print("[..] Loading demo data", flush=True)
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "app.seed"], cwd=BACKEND, env=env, check=True
        )
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "app.bootstrap"], cwd=BACKEND, env=env, check=True
        )
        processes.append(
            subprocess.Popen(  # noqa: S603
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    API_PORT,
                ],
                cwd=BACKEND,
                env=env,
            )
        )
        wait_for(f"http://127.0.0.1:{API_PORT}/api/v1/health/ready", "API")

        if not args.api_only:
            npm = shutil.which("npm")
            if npm is None:
                raise SystemExit("npm was not found. Install Node.js, then try again.")
            script = "start" if args.production_web else "dev"
            processes.append(
                subprocess.Popen(  # noqa: S603
                    [npm, "run", script, "--", "--port", WEB_PORT], cwd=FRONTEND, env=env
                )
            )
            wait_for(f"http://localhost:{WEB_PORT}/login", "Web UI", timeout=180)
            print(f"\nOpen http://localhost:{WEB_PORT}  (Ctrl+C to stop)\n", flush=True)

        while all(p.poll() is None for p in processes):
            time.sleep(1)
        print("A service stopped unexpectedly; shutting down.", flush=True)
        return 1
    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
        return 0
    finally:
        for process in processes:
            if os.name == "nt":
                subprocess.run(  # noqa: S603
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],  # noqa: S607
                    capture_output=True,
                    check=False,
                )
            else:
                process.terminate()
        postgres.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
