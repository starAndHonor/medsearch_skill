"""PubMed term planning and query construction helpers."""

from __future__ import annotations

import re

# Words that open interrogative/imperative BioASQ questions; they never
# contribute to retrieval.
_QUESTION_WORDS = frozenset({
    "describe", "list", "name", "give", "provide", "explain", "define", "tell",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "is", "are", "was", "were", "do", "does", "did", "can", "could", "would",
    "should", "may", "might", "shall", "must",
})

_STOPWORDS = frozenset({
    "the", "a", "an", "of", "or", "and", "in", "on", "for", "with", "to", "as",
    "by", "at", "from", "into", "it", "its", "this", "that", "these", "those",
    "there", "their", "be", "been", "being", "has", "have", "had", "not", "no",
    "between", "versus", "vs", "than", "such",
})

# Single-token blocks from this set explode OR queries without adding signal.
_GENERIC_TERMS = frozenset({
    "disease", "diseases", "cancer", "cancers", "treatment", "treatments",
    "therapy", "therapies", "patients", "patient", "effect", "effects", "role",
    "association", "associations", "mechanism", "mechanisms", "review", "study",
    "studies", "syndrome", "gene", "genes", "protein", "proteins", "cell",
    "cells", "human", "humans", "use", "used", "using", "based", "type",
    "types", "disorder", "disorders", "level", "levels", "rate", "rates",
    "risk", "outcome", "outcomes", "factor", "factors", "marker", "markers",
})

_MAX_BLOCKS = 8


class TermPlanner:
    """Create a conservative term plan from PICO fields."""

    def plan(self, pico: dict) -> dict:
        concepts = []
        for label, value in [
            ("population", pico.get("population", "")),
            ("intervention_or_exposure", pico.get("intervention_or_exposure", "")),
            ("comparator", pico.get("comparator", "")),
            ("outcome", pico.get("outcome", "")),
        ]:
            value = str(value or "").strip()
            if not value:
                continue
            concepts.append({
                "name": label,
                "raw": value,
                "mesh_terms": [self._title_case(value)],
                "title_abstract_terms": self._synonymish_terms(value),
                "notes": "Initial term plan; validate MeSH before using [MeSH Terms].",
            })
        return {"concepts": concepts, "filters": {"humans": True, "language": "english"}, "warnings": []}

    def _title_case(self, text: str) -> str:
        return " ".join(part.capitalize() for part in text.split())

    def _content_blocks(self, text: str) -> list[list[str]]:
        """Split text into maximal runs of content words.

        Question openers ("Describe", "Is") and stopwords break runs, so
        "Is Hirschsprung disease a mendelian or a multifactorial disorder?"
        yields ["Hirschsprung", "disease"], ["mendelian"],
        ["multifactorial", "disorder"]. Original casing is preserved.
        """
        words = re.findall(r"[A-Za-z0-9\-]+", text)
        blocks: list[list[str]] = []
        current: list[str] = []
        for word in words:
            lowered = word.lower()
            if lowered in _QUESTION_WORDS or lowered in _STOPWORDS:
                if current:
                    blocks.append(current)
                    current = []
                continue
            current.append(word)
        if current:
            blocks.append(current)
        return blocks

    def _synonymish_terms(self, text: str) -> list[str]:
        terms = [text]
        cleaned = text.replace("-", " ")
        if cleaned != text:
            terms.append(cleaned)
        # Generic decomposition: full original phrase stays (high precision),
        # multi-word content blocks add recall, informative single tokens
        # cover entities with no fixed phrase form (e.g. "RankMHC").
        for block in self._content_blocks(text)[:_MAX_BLOCKS]:
            if len(block) > 1:
                terms.append(" ".join(block))
            elif block[0].lower() not in _GENERIC_TERMS and len(block[0]) >= 3:
                terms.append(block[0])
        lower = text.lower()
        if "type 2" in lower and "diabetes" in lower:
            terms.extend(["type 2 diabetes", "T2DM", "Diabetes Mellitus, Type 2"])
        if "glp" in lower or "semaglutide" in lower:
            terms.extend([
                "GLP-1 receptor agonist",
                "glucagon-like peptide-1 receptor agonist",
                "semaglutide",
                "liraglutide",
                "dulaglutide",
            ])
        if "cardiovascular" in lower or "myocardial" in lower or "stroke" in lower:
            terms.extend([
                "cardiovascular events",
                "major adverse cardiovascular events",
                "MACE",
                "cardiovascular death",
                "myocardial infarction",
                "stroke",
            ])
        return sorted(set(t for t in terms if t.strip()))


class QueryBuilder:
    """Build PubMed query ladder from a term plan and MeSH validation."""

    def build(self, term_plan: dict, mesh_validation: list[dict] | None = None) -> list[dict]:
        validation_by_candidate = {v.get("candidate", ""): v for v in mesh_validation or []}
        blocks_by_concept = {}
        for concept in term_plan.get("concepts", []):
            parts = []
            for mesh in concept.get("mesh_terms", []):
                val = validation_by_candidate.get(mesh)
                if val and val.get("status") in {"valid", "entry_term"}:
                    preferred = val.get("preferred_term") or mesh
                    parts.append(f'"{preferred}"[MeSH Terms]')
            for term in concept.get("title_abstract_terms", []):
                parts.append(f'"{term}"[Title/Abstract]')
            if parts:
                blocks_by_concept[concept.get("name", "")] = "(" + " OR ".join(sorted(set(parts))) + ")"

        broad_names = ["population", "intervention_or_exposure", "outcome"]
        broad_blocks = [blocks_by_concept[name] for name in broad_names if blocks_by_concept.get(name)]
        all_blocks = [blocks_by_concept[name] for name in ["population", "intervention_or_exposure", "comparator", "outcome"] if blocks_by_concept.get(name)]
        base = " AND ".join(broad_blocks or all_blocks)
        comparator_base = " AND ".join(all_blocks)
        filters = []
        cfg_filters = term_plan.get("filters", {})
        if cfg_filters.get("humans", True):
            filters.append("humans[MeSH Terms]")
        if cfg_filters.get("language"):
            filters.append(f'{cfg_filters["language"]}[Language]')
        focused = " AND ".join([base, *filters]) if base else " AND ".join(filters)
        ladder = []
        if base:
            ladder.append({"query_id": "Q1_broad_conceptual", "purpose": "Broad concept query for recall", "exact_query": base, "source": "tool_generated", "executed": False})
        if focused and focused != base:
            ladder.append({"query_id": "Q2_focused_primary", "purpose": "Focused query with basic filters", "exact_query": focused, "source": "tool_generated", "executed": False})
        if comparator_base and comparator_base != base:
            ladder.append({"query_id": "Q3_with_comparator", "purpose": "Narrow query including comparator terms", "exact_query": comparator_base, "source": "tool_generated", "executed": False})
        if focused:
            ladder.append({"query_id": "Q4_reviews", "purpose": "Systematic review/meta-analysis oriented query", "exact_query": f"({focused}) AND (systematic review[Publication Type] OR meta-analysis[Publication Type])", "source": "tool_generated", "executed": False})
            ladder.append({"query_id": "Q5_trials", "purpose": "Clinical trial oriented query", "exact_query": f"({focused}) AND (clinical trial[Publication Type] OR randomized controlled trial[Publication Type])", "source": "tool_generated", "executed": False})
        return ladder
