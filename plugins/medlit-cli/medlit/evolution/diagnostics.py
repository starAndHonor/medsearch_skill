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
        mesh_required = bool(
            state.get("query_configuration", {}).get("mesh_enabled", False)
        )
        mesh_status = state.get("mesh_validation_status", {}) or {}
        if "completed" in mesh_status:
            mesh_validation_completed = bool(mesh_status.get("completed"))
        else:
            # Compatibility for states created before explicit completion was
            # recorded: a non-empty validation list proves the stage ran.
            mesh_validation_completed = bool(state.get("mesh_validation"))

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
        elif not state.get("pico"):
            status = "needs_pico"
            actions = ["decompose"]
        elif not any(str(state.get("pico", {}).get(key, "")).strip() for key in ("population", "intervention_or_exposure", "outcome")):
            status = "needs_question_clarification"
            blocked = True
            reason = "The input does not look like a usable biomedical research question."
            actions = ["ask_user_for_medical_research_question"]
        elif not state.get("term_plan", {}).get("concepts"):
            status = "needs_term_plan"
            actions = ["plan-terms"]
        elif state.get("term_plan", {}).get("concepts") == [] and state.get("pico"):
            status = "needs_question_clarification"
            blocked = True
            reason = "No searchable biomedical concepts could be planned from the question."
            actions = ["ask_user_for_medical_research_question"]
        elif mesh_required and not mesh_validation_completed:
            status = "needs_mesh_validation"
            actions = ["validate-mesh"]
        elif not state.get("query_ladder"):
            status = "needs_query"
            actions = ["build-query --use-mesh" if mesh_required else "build-query"]
        elif not records and pubmed_queries >= int(budgets.get("max_pubmed_queries", 6)):
            status = "blocked"
            blocked = True
            reason = "PubMed query budget exhausted without records."
            actions = ["report_failure"]
        elif not records:
            status = "needs_pubmed_search"
            actions = ["search-pubmed", "fetch-records"]
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
                "mesh_required": mesh_required,
                "mesh_validation_completed": mesh_validation_completed,
            },
        }

    def _coverage(self, state: dict[str, Any]) -> dict[str, bool]:
        pico = state.get("pico", {})
        term_plan = state.get("term_plan", {})
        query_text = " ".join(q.get("exact_query", "") for q in state.get("query_ladder", []))
        evidence_text = " ".join(str(e) for e in state.get("evidence", []))
        out = {}
        for field in ("population", "intervention_or_exposure", "comparator", "outcome"):
            value = str(pico.get(field, "")).lower()
            if not value:
                out[field] = field == "comparator"
                continue
            tokens = [t for t in value.split() if len(t) > 2]
            out[field] = any(t in query_text.lower() or t in evidence_text.lower() for t in tokens)
        return out
