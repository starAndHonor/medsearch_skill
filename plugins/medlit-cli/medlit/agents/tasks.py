"""File-based task queue for optional subagent work."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TaskQueue:
    root: Path

    def spawn_tasks(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        tasks = []
        if state.get("query_attempts") and not state.get("accepted_query_attempt_id"):
            tasks.append(self._task(
                "search_planner",
                "Review PubMed query attempts and choose whether to accept or rewrite the query.",
                {"query_attempts": state.get("query_attempts", [])},
            ))
        for record in state.get("records", []):
            pmid = record.get("pmid")
            if pmid and not any(f.get("pmid") == pmid for f in state.get("fulltexts", [])):
                tasks.append(self._task("fulltext_localizer", "Localize open-access full text for one PubMed record.", {"record": record}))
        for parsed in state.get("parsed_sources", []):
            pmid = parsed.get("pmid")
            if pmid and parsed.get("status") == "parsed" and not any(e.get("paper_ref") == pmid for e in state.get("evidence", [])):
                tasks.append(self._task("paper_reader", "Extract structured evidence from one parsed paper.", {"parsed_source": parsed}))
        if state.get("evidence") and not state.get("verification"):
            tasks.append(self._task("verifier", "Verify evidence references and local-source traceability.", {"evidence_count": len(state.get("evidence", []))}))

        task_dir = self.root / "tasks"
        task_dir.mkdir(parents=True, exist_ok=True)
        existing = len(list(task_dir.glob("task_*.json")))
        written = []
        for offset, task in enumerate(tasks, 1):
            task["task_id"] = f"task_{existing + offset:03d}"
            path = task_dir / f"{task['task_id']}.json"
            path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
            task["path"] = str(path)
            written.append(task)
        state.setdefault("tasks", []).extend(written)
        return written

    def merge_output(self, state: dict[str, Any], output_file: str | Path) -> dict[str, Any]:
        data = json.loads(Path(output_file).read_text(encoding="utf-8"))
        state.setdefault("task_outputs", []).append(data)
        return {"merged": True, "output_file": str(output_file), "type": data.get("type", "unknown")}

    def _task(self, role: str, instruction: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"role": role, "instruction": instruction, "payload": payload, "status": "open"}
