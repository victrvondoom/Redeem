import os
import subprocess
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]


def _alembic(db, *args):
    env = {**os.environ, "REDEEM_DATABASE_URL": f"sqlite:///{db}"}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=API, env=env, capture_output=True, text=True)


def test_migration_upgrades_and_matches_models(tmp_path):
    db = tmp_path / "m.db"
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    chk = _alembic(db, "check")  # fails if models drift from the migration
    assert chk.returncode == 0, chk.stdout + chk.stderr
