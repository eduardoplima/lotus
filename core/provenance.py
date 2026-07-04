"""Reproducibility helpers (§6.3).

Every backtest run records the exact code version (git SHA) and a deterministic
hash of its full configuration, so a result is always traceable to the inputs
that produced it and an identical run is not silently double-counted.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import Any


def git_sha(short: bool = False) -> str:
    """Return the current git commit SHA, or 'unknown' outside a repo.

    A dirty working tree is flagged with a '-dirty' suffix so a run pinned to a
    SHA is not mistaken for a clean checkout.
    """
    try:
        args = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
        sha = subprocess.check_output(args, stderr=subprocess.DEVNULL).decode().strip()
        dirty = subprocess.run(
            ["git", "diff", "--quiet"], stderr=subprocess.DEVNULL
        ).returncode
        return f"{sha}-dirty" if dirty else sha
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def config_hash(*parts: Any) -> str:
    """Deterministic SHA-256 over JSON-serializable config parts.

    Used as `backtest_run.config_hash` (unique) to prevent duplicate runs of an
    identical configuration (§9).
    """
    blob = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()
