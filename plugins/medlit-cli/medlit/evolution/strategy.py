"""Simple strategy evolution for query refinement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StrategyEvolver:
    """Generate conservative next-step suggestions from diagnostics."""

    def evolve(self, state: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:
        metrics = diagnostics.get("metrics", {})
        coverage = diagnostics.get("coverage", {})
        suggestions = []
        if metrics.get("records", 0) == 0:
            suggestions.append(
                "Keep or broaden Q0_cleaned_natural and remove only explicitly configured strict filters."
            )
        if metrics.get("records", 0) > state.get("budgets", {}).get("max_records", 50):
            suggestions.append("Prefer focused query and add outcome or study-design terms.")
        missing = [k for k, ok in coverage.items() if not ok]
        if missing:
            suggestions.append("Add visible Title/Abstract terms for: " + ", ".join(missing))
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
