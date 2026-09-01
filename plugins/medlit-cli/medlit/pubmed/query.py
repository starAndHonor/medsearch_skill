"""PubMed term planning and query construction helpers."""

from __future__ import annotations

import re
from typing import Any


_QUESTION_OPENERS = frozenset({
    "describe", "list", "name", "give", "provide", "explain", "define", "tell",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "is", "are", "was", "were", "do", "does", "did", "can", "could", "would",
    "should", "may", "might", "shall", "must", "have", "has",
})

_STOPWORDS = frozenset({
    "the", "a", "an", "of", "or", "and", "in", "on", "for", "with", "to", "as",
    "by", "at", "from", "into", "it", "its", "this", "that", "these", "those",
    "there", "their", "be", "been", "being", "not", "no", "between", "versus", "vs",
    "than", "such", "any",
})

# Single terms that are too broad to enter a recall OR lane. They remain in
# the untagged natural-language lane where PubMed ATM can interpret context.
_GENERIC_TERMS = frozenset({
    "action", "actions", "associated", "association", "associations", "basis",
    "case", "cases", "cancer", "cancers", "cause", "caused", "classification",
    "clinical", "complication", "complications", "current", "disease", "diseases",
    "disorder", "disorders", "effect", "effects", "factor", "factors", "feature",
    "features", "gene", "genes", "group", "groups", "human", "humans", "identified",
    "incidence", "involved", "life", "list", "long", "management", "marker", "markers",
    "mechanism", "mechanisms", "new", "outcome", "outcomes", "patient", "patients",
    "pathophysiology", "practice", "prevalence", "prognosis", "protein", "proteins",
    "rate", "rates", "recent", "reduce", "reduced", "reduces", "review", "risk", "role",
    "routine", "safety", "short", "study", "studies", "symptom", "symptoms", "syndrome",
    "target", "therapy", "therapies", "treatment", "treatments", "type", "types", "use",
    "used", "using",
})

# These words must terminate a phrase. This prevents constructions such as
# "Plozasiran reduce" and "MR-PheWAS identified" from being quoted as entities.
_PHRASE_BREAKERS = _STOPWORDS | _QUESTION_OPENERS | _GENERIC_TERMS
_PAREN_RE = re.compile(r"\(([A-Za-z0-9][A-Za-z0-9-]{0,20})\)")
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
_TRAILING_PUNCT = " .,;:!?"
_MAX_BLOCKS = 10
_MAX_PHRASE_WORDS = 4


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = " ".join(str(value).split()).strip(_TRAILING_PUNCT)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _informative(term: str) -> bool:
    words = term.replace("-", " ").split()
    content = [word for word in words if not word.isdigit() and word.casefold() not in _GENERIC_TERMS]
    return bool(content) and (len(words) > 1 or len(content[0]) >= 3)


def _looks_like_question(text: str) -> bool:
    tokens = _TOKEN_RE.findall(text)
    return bool(text.rstrip().endswith("?") or (tokens and tokens[0].casefold() in _QUESTION_OPENERS))


def clean_natural_query(text: str) -> str:
    """Remove only leading question scaffolding and leave biomedical context."""
    cleaned = " ".join(str(text or "").strip().strip(_TRAILING_PUNCT).split())
    patterns = (
        r"^(?:please\s+)?(?:describe|list|name|give|provide|explain|define|tell)\s+",
        r"^(?:what|which|who|where|when|why|how)\s+(?:is|are|was|were|do|does|did|has|have|can|could|would|should)\s+",
        r"^(?:is|are|was|were|do|does|did|has|have|can|could|would|should|may|might)\s+",
        r"^(?:what|which|who|where|when|why|how)\s+",
    )
    for pattern in patterns:
        updated = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE)
        if updated != cleaned:
            cleaned = updated
            break
    cleaned = re.sub(r"^the\s+", "", cleaned, count=1, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bbe\s+(used|treated|found|associated)\b", r"\1", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(_TRAILING_PUNCT)


class TermPlanner:
    """Create a conservative term plan from explicit PICO fields."""

    def plan(self, pico: dict[str, Any]) -> dict[str, Any]:
        concepts: list[dict[str, Any]] = []
        fields = (
            ("population", pico.get("population", "")),
            ("intervention_or_exposure", pico.get("intervention_or_exposure", "")),
            ("comparator", pico.get("comparator", "")),
            ("outcome", pico.get("outcome", "")),
        )
        for label, raw_value in fields:
            value = str(raw_value or "").strip()
            if not value:
                continue
            title_abstract_terms = self._title_abstract_terms(value)
            concepts.append({
                "name": label,
                "raw": value,
                "mesh_terms": [self._title_case(term) for term in title_abstract_terms[:_MAX_BLOCKS]],
                "title_abstract_terms": title_abstract_terms,
                "notes": "Conservative entity/phrase terms; MeSH candidates require validation.",
            })

        raw_question = str(pico.get("question") or pico.get("raw_question") or "").strip()
        if not raw_question:
            populated = [str(value or "").strip() for _, value in fields if str(value or "").strip()]
            if len(populated) == 1 and _looks_like_question(populated[0]):
                raw_question = populated[0]

        filters: dict[str, Any] = {}
        if isinstance(pico.get("filters"), dict):
            filters.update(pico["filters"])
        if "humans" in pico:
            filters["humans"] = bool(pico["humans"])
        if pico.get("language"):
            filters["language"] = str(pico["language"])

        return {
            "raw_question": raw_question,
            "cleaned_natural_query": clean_natural_query(raw_question) if raw_question else "",
            "concepts": concepts,
            "filters": filters,
            "warnings": [],
        }

    def _title_case(self, text: str) -> str:
        return " ".join(part.capitalize() for part in text.split())

    def _blocks(self, text: str) -> list[list[str]]:
        blocks: list[list[str]] = []
        current: list[str] = []
        for token in _TOKEN_RE.findall(text):
            if token.casefold() in _PHRASE_BREAKERS:
                if current:
                    blocks.append(current)
                    current = []
                continue
            current.append(token)
        if current:
            blocks.append(current)
        return blocks

    def _block_terms(self, block: list[str]) -> list[str]:
        if not block:
            return []
        if len(block) <= _MAX_PHRASE_WORDS:
            phrase = " ".join(block)
            terms = [phrase]
            terms.extend(token for token in block if self._distinctive_token(token))
            return [term for term in terms if _informative(term)]

        terms = [token for token in block if self._distinctive_token(token)]
        for width in (3, 2):
            for start in range(len(block) - width + 1):
                phrase = " ".join(block[start:start + width])
                if _informative(phrase):
                    terms.append(phrase)
        return terms[:12]

    def _distinctive_token(self, token: str) -> bool:
        if len(token) < 3 or token.casefold() in _GENERIC_TERMS:
            return False
        return bool(
            any(char.isdigit() for char in token)
            or "-" in token
            or (any(char.islower() for char in token) and any(char.isupper() for char in token))
            or token.isupper()
        )

    def _title_abstract_terms(self, text: str) -> list[str]:
        abbreviations = _PAREN_RE.findall(text)
        without_parentheticals = _PAREN_RE.sub(" ", text)
        terms: list[str] = list(abbreviations)
        for block in self._blocks(without_parentheticals)[:_MAX_BLOCKS]:
            terms.extend(self._block_terms(block))

        lower = text.casefold()
        if "type 2" in lower and "diabetes" in lower:
            terms.extend(["type 2 diabetes", "T2DM", "Diabetes Mellitus, Type 2"])
        if "glp" in lower or "semaglutide" in lower:
            terms.extend(["GLP-1 receptor agonist", "glucagon-like peptide-1 receptor agonist"])
        if "phosphodiesterase" in lower and "5" in lower:
            terms.extend(["PDE5", "phosphodiesterase type 5 inhibitor"])
        if "half life" in lower or "half-life" in lower:
            terms.extend(["half-life", "pharmacokinetics"])
        return [term for term in _dedupe(terms) if _informative(term)]


class QueryBuilder:
    """Build complementary natural, structured, and focused PubMed lanes."""

    def build(
        self, term_plan: dict[str, Any], mesh_validation: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        validation = {str(item.get("candidate", "")): item for item in mesh_validation or []}
        blocks_by_concept: dict[str, str] = {}
        ta_by_concept: dict[str, list[str]] = {}

        for concept in term_plan.get("concepts", []):
            parts: list[str] = []
            for candidate in concept.get("mesh_terms", []):
                item = validation.get(str(candidate))
                if item and item.get("status") in {"valid", "entry_term"}:
                    preferred = item.get("preferred_term") or candidate
                    parts.append(f'"{preferred}"[MeSH Terms]')
            ta_terms = [term for term in concept.get("title_abstract_terms", []) if _informative(term)]
            ta_by_concept[str(concept.get("name", ""))] = ta_terms
            parts.extend(f'"{term}"[Title/Abstract]' for term in ta_terms)
            if parts:
                blocks_by_concept[str(concept.get("name", ""))] = "(" + " OR ".join(_dedupe(parts)) + ")"

        broad_names = ("population", "intervention_or_exposure", "outcome")
        broad_blocks = [blocks_by_concept[name] for name in broad_names if blocks_by_concept.get(name)]
        all_names = ("population", "intervention_or_exposure", "comparator", "outcome")
        all_blocks = [blocks_by_concept[name] for name in all_names if blocks_by_concept.get(name)]
        base = " AND ".join(broad_blocks or all_blocks)
        comparator_base = " AND ".join(all_blocks)

        filters: list[str] = []
        cfg_filters = term_plan.get("filters", {}) or {}
        if cfg_filters.get("humans") is True:
            filters.append("humans[MeSH Terms]")
        if cfg_filters.get("language"):
            filters.append(f'{cfg_filters["language"]}[Language]')
        focused = " AND ".join([base, *filters]) if base and filters else ""

        ladder: list[dict[str, Any]] = []
        natural = str(term_plan.get("cleaned_natural_query", "")).strip()
        if natural:
            ladder.append(self._lane("Q0_cleaned_natural", "Untagged cleaned question using PubMed ATM", natural))
        if base:
            ladder.append(self._lane("Q1_structured_recall", "Conservative Title/Abstract entities with optional validated MeSH", base))

        anchor_query = self._anchor_query(ta_by_concept)
        if anchor_query and anchor_query != base:
            ladder.append(self._lane("Q1b_entity_anchor", "Specific entity phrases required to co-occur", anchor_query))
        if focused and focused != base:
            ladder.append(self._lane("Q2_explicit_filters", "Only user-requested population/language filters", focused))
        if comparator_base and comparator_base != base:
            ladder.append(self._lane("Q3_with_comparator", "Structured lane including comparator", comparator_base))
        return ladder

    def _anchor_query(self, ta_by_concept: dict[str, list[str]]) -> str:
        concept_groups: list[str] = []
        for name in ("population", "intervention_or_exposure", "outcome"):
            ranked = sorted(
                ta_by_concept.get(name, []),
                key=lambda term: (len(term.split()), len(term)),
                reverse=True,
            )
            if not ranked:
                continue
            chosen: list[str] = []
            for term in ranked:
                if any(term.casefold() in kept.casefold() or kept.casefold() in term.casefold() for kept in chosen):
                    continue
                chosen.append(term)
                if len(chosen) == 2:
                    break
            group = " AND ".join(f'"{term}"[Title/Abstract]' for term in chosen)
            if group:
                concept_groups.append(f"({group})")
        return " AND ".join(concept_groups)

    def _lane(self, query_id: str, purpose: str, exact_query: str) -> dict[str, Any]:
        return {
            "query_id": query_id,
            "purpose": purpose,
            "exact_query": exact_query,
            "source": "tool_generated",
            "executed": False,
        }
