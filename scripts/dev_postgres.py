"""Run a command with DATABASE_URL pointing at an embedded PostgreSQL (no Docker needed).

Usage: python scripts/dev_postgres.py <command> [args...]
"""

import os
import subprocess
import sys
from pathlib import Path

import pixeltable_pgserver

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / ".local" / "pgdata"


def start_postgres() -> tuple[object, str]:
    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
    server = pixeltable_pgserver.get_server(str(DATA_DIR), cleanup_mode="stop")
    return server, server.get_uri().replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    server, url = start_postgres()
    command = [sys.executable if sys.argv[1] == "python" else sys.argv[1], *sys.argv[2:]]
    try:
        return subprocess.call(command, env={**os.environ, "DATABASE_URL": url})  # noqa: S603
    finally:
        server.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
