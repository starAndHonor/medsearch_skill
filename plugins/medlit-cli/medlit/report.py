"""Markdown report generation and verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ReportWriter:
    output_dir: Path

    def write(self, state: dict[str, Any]) -> str:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / "report.md"
        diag = state.get("diagnostics", {})
        lines = [
            "# Medical Literature Research Report",
            "",
            f"Question: {state.get('question', '')}",
            "",
            "## Status",
            "",
            f"- State: {diag.get('status', state.get('status', 'unknown'))}",
            f"- Records: {len(state.get('records', []))}",
            f"- Evidence items: {len(state.get('evidence', []))}",
            f"- Full-text hit rate: {diag.get('metrics', {}).get('fulltext_hit_rate', 'N/A')}",
            "",
            "## Accepted PubMed Query",
            "",
        ]
        accepted_id = state.get("accepted_query_attempt_id", "")
        accepted = next(
            (
                item
                for item in state.get("query_attempts", [])
                if item.get("attempt_id") == accepted_id
            ),
            {},
        )
        lines.extend([
            f"- Attempt: {accepted_id or 'none'}",
            f"- Query: `{accepted.get('exact_query', '')}`",
            f"- PubMed hits: {accepted.get('count', 0)}",
        ])
        lines.extend(["", "## Evidence", ""])
        for idx, item in enumerate(state.get("evidence", []), 1):
            lines.extend([
                f"### {idx}. {item.get('title') or item.get('paper_ref')}",
                "",
                f"- Source: {item.get('paper_ref')} ({item.get('source_granularity')})",
                f"- Study design: {item.get('study_design')}",
                f"- Local source: `{item.get('local_source')}`",
                "",
                f"Methods: {item.get('methods', '')}",
                "",
                f"Main results: {item.get('main_results', '')}",
                "",
            ])
            if item.get("numbers"):
                lines.append("Numbers:")
                for number in item.get("numbers", []):
                    lines.append(f"- {number}")
                lines.append("")
            if item.get("limitations"):
                lines.append(f"Limitations: {item.get('limitations')}")
                lines.append("")
        if state.get("blockers"):
            lines.extend(["## Blockers and Degradations", ""])
            for blocker in state.get("blockers", []):
                lines.append(f"- {blocker.get('kind')}: {blocker.get('message')} {blocker.get('advice', '')}")
            lines.append("")
        lines.extend(["## Search Audit", ""])
        for attempt in state.get("query_attempts", []):
            marker = " (accepted)" if attempt.get("attempt_id") == accepted_id else ""
            lines.append(
                f"- {attempt.get('attempt_id')}{marker}: "
                f"{attempt.get('count')} hits; query `{attempt.get('exact_query')}`"
            )
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)


class Verifier:
    def verify(self, state: dict[str, Any]) -> dict[str, Any]:
        record_ids = {str(r.get("pmid", "")) for r in state.get("records", []) if r.get("pmid")}
        errors = []
        for item in state.get("evidence", []):
            ref = str(item.get("paper_ref", ""))
            if ref and ref not in record_ids and not item.get("title"):
                errors.append(f"Evidence reference not found in records: {ref}")
            if item.get("source_granularity") == "fulltext" and not item.get("local_source"):
                errors.append(f"Fulltext evidence lacks local source: {ref}")
        return {"ok": not errors, "errors": errors, "checked_records": len(record_ids), "checked_evidence": len(state.get("evidence", []))}
