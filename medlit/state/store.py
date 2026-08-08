"""State model and atomic persistence for MedLit runs."""

from __future__ import annotations

import json
import os
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "medlit-state/v0.1"
DEFAULT_STATE = Path("workspace/latest/state.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StateStore:
    """Load, mutate, and save the research state.

    The state is intentionally plain JSON so Codex can inspect and repair it
    without depending on Python internals.
    """

    def __init__(self, path: str | Path = DEFAULT_STATE):
        self.path = Path(path).resolve()

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise FileNotFoundError(f"State file not found: {self.path}")
        return json.loads(self.path.read_text(encoding="utf-8"))

    def init(self, question: str) -> dict[str, Any]:
        state = {
            "schema_version": SCHEMA_VERSION,
            "question": question,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "status": "running",
            "pico": {},
            "term_plan": {"concepts": [], "filters": {}, "warnings": []},
            "mesh_validation": [],
            "query_ladder": [],
            "retrieval_runs": [],
            "records": [],
            "fulltexts": [],
            "parsed_sources": [],
            "evidence": [],
            "diagnostics": {},
            "evolution_memory": [],
            "tasks": [],
            "blockers": [],
            "errors": [],
            "budgets": {
                "max_rounds": 3,
                "max_pubmed_queries": 6,
                "max_records": 50,
                "max_fulltext_attempts": 30,
                "max_same_blocker": 2,
            },
            "counters": {
                "round": 0,
                "pubmed_queries": 0,
                "fulltext_attempts": 0,
                "same_blocker_repeats": {},
            },
            "report_path": "",
        }
        self.save(state)
        return state

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = utc_now()
        fd, tmp_name = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                json.dump(state, tmp, ensure_ascii=False, indent=2)
                tmp.write("\n")
            tmp_path = Path(tmp_name)
            last_error = None
            for attempt in range(5):
                try:
                    tmp_path.replace(self.path)
                    last_error = None
                    break
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.05 * (attempt + 1))
            if last_error:
                raise last_error
        finally:
            if Path(tmp_name).exists():
                Path(tmp_name).unlink()

    def update(self, mutator) -> dict[str, Any]:
        state = self.load()
        mutator(state)
        self.save(state)
        return state


class StateOps:
    """Utility methods for mutating state consistently."""

    @staticmethod
    def add_error(state: dict[str, Any], stage: str, message: str, *, recoverable: bool = True, details: dict[str, Any] | None = None) -> None:
        state.setdefault("errors", []).append({
            "stage": stage,
            "message": message,
            "recoverable": recoverable,
            "details": details or {},
            "at": utc_now(),
        })

    @staticmethod
    def add_blocker(state: dict[str, Any], kind: str, message: str, *, stage: str = "", advice: str = "", details: dict[str, Any] | None = None) -> None:
        blocker = {
            "kind": kind,
            "stage": stage,
            "message": message,
            "advice": advice,
            "details": details or {},
            "at": utc_now(),
        }
        state.setdefault("blockers", []).append(blocker)
        repeats = state.setdefault("counters", {}).setdefault("same_blocker_repeats", {})
        repeats[kind] = int(repeats.get(kind, 0)) + 1

    @staticmethod
    def replace_by_key(items: list[dict[str, Any]], new_items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        out = deepcopy(items)
        index = {str(item.get(key, "")): i for i, item in enumerate(out) if item.get(key)}
        for item in new_items:
            item_key = str(item.get(key, ""))
            if item_key and item_key in index:
                out[index[item_key]] = item
            else:
                out.append(item)
                if item_key:
                    index[item_key] = len(out) - 1
        return out
