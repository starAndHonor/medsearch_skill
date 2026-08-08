"""Agent shell configuration."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


CONFIG_PATH = Path(".medlit_agent/config.json")


@dataclass
class AgentConfig:
    backend: str = "external-codex"  # external-codex | openai-api
    model: str = ""
    approval_mode: str = "on-network"  # never | on-network | on-step
    state_path: str = "workspace/latest/state.json"
    max_agent_steps: int = 20
    api_base: str = "https://api.openai.com/v1"
    verbosity: str = "medium"
    debug_json: bool = False
    codex_path: str = ""
    planner_timeout_seconds: int = 60
    agent_timeout_seconds: int = 600
    codex_sandbox_mode: str = "workspace-write"  # read-only | workspace-write | danger-full-access

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "AgentConfig":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        allowed = {field for field in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def api_key(self, session_key: str = "") -> str:
        return session_key or os.environ.get("OPENAI_API_KEY", "")
