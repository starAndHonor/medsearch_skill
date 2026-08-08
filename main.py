#!/usr/bin/env python
"""Project entrypoint for the MedLit Codex-style terminal agent."""

from __future__ import annotations

import sys
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from medlit.agent.shell import main


if __name__ == "__main__":
    raise SystemExit(main())
