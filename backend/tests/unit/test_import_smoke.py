"""Phase 11 Sprint 4: import-time smoke test.

Regression gate for the k8s_agent.py corruption class of failure: any syntax
error or import-time side effect (DB/Redis connect, network calls) that breaks
`import app.main` must fail CI here first, with a clear exit code.

Runs the import in a clean subprocess so a poisoned ambient env (real
REDIS_HOST, etc.) can't mask a regression, and so import-time os.exit / signal
handlers can't take down the pytest process.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Minimal env so Settings validates; service endpoints pointed at a closed
# port on 127.0.0.1 — import must NOT attempt to connect to them.
DEAD_SERVICE_ENV = {
    "REDIS_HOST": "127.0.0.1",
    "REDIS_PORT": "1",
    "DATABASE_URL": "postgresql+asyncpg://127.0.0.1:1/dead",
}

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "AUTH_SECRET": "test-secret-0123456789abc",
    "API_KEYS": '["test-key"]',
}


def _import_main(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_import_main_with_minimal_env() -> None:
    """import app.main succeeds with no service env vars at all."""
    result = _import_main(BASE_ENV)
    assert result.returncode == 0, f"import failed:\n{result.stderr[-2000:]}"


def test_import_main_with_unreachable_redis_and_db() -> None:
    """import app.main must not connect to Redis/Postgres at import time."""
    result = _import_main({**BASE_ENV, **DEAD_SERVICE_ENV})
    assert result.returncode == 0, f"import failed:\n{result.stderr[-2000:]}"
