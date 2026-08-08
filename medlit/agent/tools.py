"""Tool runner for the MedLit CLI toolbox."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NETWORK_ACTIONS = {"validate-mesh", "search-pubmed", "fetch-records", "localize-fulltext"}


@dataclass
class ToolResult:
    action: str
    returncode: int
    stdout: str
    stderr: str

    def json_payload(self) -> Any:
        try:
            return json.loads(self.stdout)
        except json.JSONDecodeError:
            return None


class ToolRunner:
    def __init__(self, root: Path, state_path: str):
        self.root = root
        self.state_path = state_path
        self.script = root / "scripts" / "medlit_cli.py"

    def run(self, action: str, args: list[str] | None = None) -> ToolResult:
        cmd = [sys.executable, str(self.script), "--state", self.state_path, action]
        if args:
            cmd.extend(args)
        completed = subprocess.run(cmd, cwd=str(self.root), text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
        return ToolResult(action=action, returncode=completed.returncode, stdout=completed.stdout.strip(), stderr=completed.stderr.strip())

