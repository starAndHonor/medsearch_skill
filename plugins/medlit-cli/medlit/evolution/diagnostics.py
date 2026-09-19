"""Run-state diagnostics, termination, and blocker classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Diagnoser:
    """Decide whether Codex should continue, degrade, report, or stop."""

    def diagnose(self, state: dict[str, Any]) -> dict[str, Any]:
        records = state.get("records", [])
        fulltexts = state.get("fulltexts", [])
        parsed = state.get("parsed_sources", [])
        evidence = state.get("evidence", [])
        blockers = state.get("blockers", [])
        budgets = state.get("budgets", {})
        counters = state.get("counters", {})

        fulltext_attempts = int(counters.get("fulltext_attempts", 0))
        pubmed_queries = int(counters.get("pubmed_queries", 0))
        max_same_blocker = int(budgets.get("max_same_blocker", 2))
        repeats = counters.get("same_blocker_repeats", {})
        hard_blockers = [
            b for b in blockers
            if repeats.get(b.get("kind", ""), 0) >= max_same_blocker
            or b.get("kind") in {"missing_dependency", "missing_required_config"}
            or (not records and b.get("kind") == "network_unavailable")
        ]

        fulltext_success = [f for f in fulltexts if str(f.get("fulltext_status", "")).endswith("downloaded")]
        parsed_ok = [p for p in parsed if p.get("status") == "parsed"]
        evidence_ok = [e for e in evidence if e.get("extraction_status") == "ok"]
        coverage = self._coverage(state)
        status = "needs_initialization"
        actions = []
        termination_ready = False
        blocked = False
        reason = ""

        if hard_blockers and not records:
            status = "blocked"
            blocked = True
            reason = "Unresolved infrastructure/config blocker before retrieval."
            actions = ["fix_environment_or_config"]
        elif not str(state.get("question", "")).strip():
            status = "needs_question_clarification"
            blocked = True
            reason = "The biomedical research question is empty."
            actions = ["ask_user_for_medical_research_question"]
        elif not state.get("query_attempts"):
            status = "needs_pubmed_query"
            actions = ["author_and_run_pubmed_query"]
        elif not state.get("accepted_query_attempt_id"):
            status = "needs_query_decision"
            actions = ["inspect_query_attempts", "run_another_query_or_accept-query"]
        elif not self._accepted_attempt(state):
            status = "blocked"
            blocked = True
            reason = "The accepted query attempt is missing from state."
            actions = ["repair_accepted_query_attempt_id"]
        elif state.get("task_mode") == "retrieval":
            if state.get("retrieval_export"):
                status = "complete"
                termination_ready = True
                actions = []
            else:
                status = "ready_to_export_retrieval"
                actions = ["export-retrieval"]
        elif not records:
            status = "needs_records"
            actions = ["fetch-records"]
        elif not fulltexts and fulltext_attempts >= int(budgets.get("max_fulltext_attempts", 30)):
            status = "fulltext_budget_exhausted"
            actions = ["parse-fulltext"]
        elif not fulltexts:
            status = "needs_fulltext_localization"
            actions = ["localize-fulltext"]
        elif not parsed_ok:
            status = "needs_parsing"
            actions = ["parse-fulltext"]
        elif not evidence_ok:
            status = "needs_evidence"
            actions = ["extract-evidence"]
        elif not state.get("report_path"):
            status = "ready_to_report"
            actions = ["report", "verify"]
        else:
            status = "complete"
            termination_ready = True
            actions = []

        if hard_blockers and records:
            # Retrieval succeeded, so do not let infra issues loop forever.
            status = "degraded_ready" if evidence_ok else status
            reason = reason or "One or more blockers exist; continue only with available evidence."

        if status in {"ready_to_report", "complete", "degraded_ready"}:
            termination_ready = True

        return {
            "status": status,
            "termination_ready": termination_ready,
            "blocked": blocked,
            "reason": reason,
            "recommended_next_actions": actions,
            "coverage": coverage,
            "metrics": {
                "records": len(records),
                "fulltexts": len(fulltexts),
                "fulltext_downloaded": len(fulltext_success),
                "parsed_sources": len(parsed_ok),
                "evidence_items": len(evidence_ok),
                "fulltext_hit_rate": round(len(fulltext_success) / len(records), 3) if records else 0.0,
                "pubmed_queries": pubmed_queries,
                "fulltext_attempts": fulltext_attempts,
            },
            "hard_blockers": hard_blockers,
            "workflow": {
                "query_attempts": len(state.get("query_attempts", [])),
                "accepted_query_attempt_id": state.get(
                    "accepted_query_attempt_id", ""
                ),
            },
        }

    def _coverage(self, state: dict[str, Any]) -> dict[str, bool]:
        attempt = self._accepted_attempt(state)
        return {
            "accepted_query": bool(attempt),
            "ranked_pmids": bool(state.get("final_ranked_pmids")),
            "records": bool(state.get("records")),
            "evidence": bool(state.get("evidence")),
        }

    def _accepted_attempt(self, state: dict[str, Any]) -> dict[str, Any] | None:
        accepted_id = state.get("accepted_query_attempt_id", "")
        return next(
            (
                item
                for item in state.get("query_attempts", [])
                if item.get("attempt_id") == accepted_id
            ),
            None,
        )
