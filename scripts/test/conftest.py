import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
TEMPLATES_DIR = REPO_ROOT / "templates"

# A fake `sbatch` on PATH so rung16/runorca can run end-to-end without a
# real Slurm cluster. It just prints the job script it was given.
FAKE_BIN_DIR = Path(__file__).resolve().parent / "fixtures" / "bin"


@pytest.fixture
def templates_dir():
    return TEMPLATES_DIR


@pytest.fixture
def run_script(tmp_path):
    """Run a script from scripts/ as a subprocess, with cwd defaulting to a fresh tmp_path."""

    def _run(name, *args, cwd=None):
        env = dict(os.environ)
        env["PATH"] = f"{FAKE_BIN_DIR}:{env['PATH']}"
        return subprocess.run(
            [str(SCRIPTS_DIR / name), *(str(a) for a in args)],
            cwd=str(cwd or tmp_path),
            env=env,
            capture_output=True,
            text=True,
        )

    return _run
