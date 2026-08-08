#!/usr/bin/env python
"""Thin script wrapper for the MedLit CLI."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medlit.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

