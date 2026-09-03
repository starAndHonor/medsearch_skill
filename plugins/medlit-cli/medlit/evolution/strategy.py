"""Simple strategy evolution for query refinement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StrategyEvolver:
    """Generate conservative next-step suggestions from diagnostics."""

    def evolve(self, state: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:
        metrics = diagnostics.get("metrics", {})
        suggestions = []
        attempts = state.get("query_attempts", [])
        latest = attempts[-1] if attempts else {}
        if not attempts:
            suggestions.append(
                "Author a PubMed query from the question's distinctive biomedical entities."
            )
        elif not latest.get("pmids"):
            suggestions.append(
                "Inspect PubMed warnings and translation, then remove an unsupported or overly strict condition."
            )
        elif not state.get("accepted_query_attempt_id"):
            suggestions.append(
                "Inspect the latest titles and abstracts, then accept the attempt or author a materially improved query."
            )
        if metrics.get("fulltext_hit_rate", 0.0) < 0.25 and metrics.get("records", 0):
            suggestions.append("Prioritize PMC/Europe PMC records or reviews with PMCID to improve full-text hit rate.")
        if not suggestions:
            suggestions.append("Keep current strategy; evidence appears sufficient for a first report.")
        strategy = {
            "strategy_id": f"s_{len(state.get('evolution_memory', [])) + 1:03d}",
            "diagnostic_status": diagnostics.get("status"),
            "suggestions": suggestions,
            "decision": "suggested",
        }
        state.setdefault("evolution_memory", []).append(strategy)
        return strategy
