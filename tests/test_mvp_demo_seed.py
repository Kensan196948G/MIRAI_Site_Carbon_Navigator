"""Integration tests for the MVP demo seed (fictional data only)."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_script(script_name: str, db_path: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["MIRAI_SEED_DEFAULT_USERS"] = "1"
    env["MIRAI_ENV"] = "development"
    env["MIRAI_DEMO_MODE"] = "1"
    result = subprocess.run(
        [sys.executable, str(ROOT / script_name)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_mvp_demo_seed_is_operable(tmp_path):
    db_path = tmp_path / "mvp_demo.db"
    _run_script("scripts/seed_mvp_demo.py", db_path)
    assert db_path.exists()
    _run_script("scripts/verify_mvp_demo.py", db_path)


def test_mvp_demo_seed_is_idempotent(tmp_path):
    db_path = tmp_path / "mvp_demo.db"
    _run_script("scripts/seed_mvp_demo.py", db_path)
    _run_script("scripts/seed_mvp_demo.py", db_path)
    _run_script("scripts/verify_mvp_demo.py", db_path)
