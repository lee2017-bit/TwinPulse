"""Finite R3 acceptance runner for a general (non-Isaac) Python process."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sources = [ROOT / "packages" / name / "src" for name in (
    "twinpulse_core", "twinpulse_provider", "twinpulse_app",
)]
command = [
    sys.executable, "-m", "unittest", "-v",
    str(ROOT / "tests" / "integration" / "test_r3_application.py"),
]
environment = __import__("os").environ.copy()
environment["PYTHONPATH"] = __import__("os").pathsep.join(map(str, sources))
temporary_root = ROOT / "tmp-r3-application"
temporary_root.mkdir(parents=True, exist_ok=True)
environment["TWINPULSE_TEST_TMP"] = str(temporary_root)
result = subprocess.run(command, cwd=ROOT, env=environment)
print(f"R3_APPLICATION_RESULT={'PASS' if result.returncode == 0 else 'FAIL'}")
raise SystemExit(result.returncode)
