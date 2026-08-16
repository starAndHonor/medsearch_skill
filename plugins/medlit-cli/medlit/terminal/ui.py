"""Small terminal UI helpers for agent-readable progress."""

from __future__ import annotations

import json
import sys
from typing import Any


class Console:
    """Consistent, lightweight status output.

    Progress goes to stderr so stdout can stay machine-readable JSON.
    """

    def __init__(self, quiet: bool = False):
        self.quiet = quiet

    def step(self, message: str) -> None:
        self._err(f"[..] {message}")

    def ok(self, message: str) -> None:
        self._err(f"[OK] {message}")

    def warn(self, message: str) -> None:
        self._err(f"[!!] {message}")

    def blocked(self, message: str) -> None:
        self._err(f"[BLOCKED] {message}")

    def fail(self, message: str) -> None:
        self._err(f"[FAIL] {message}")

    def json(self, payload: Any) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        try:
            print(text)
        except UnicodeEncodeError:
            print(json.dumps(payload, ensure_ascii=True, indent=2))

    def _err(self, message: str) -> None:
        if self.quiet:
            return
        try:
            sys.stderr.write(message + "\n")
        except UnicodeEncodeError:
            sys.stderr.write(message.encode(sys.stderr.encoding or "utf-8", errors="backslashreplace").decode(sys.stderr.encoding or "utf-8") + "\n")
