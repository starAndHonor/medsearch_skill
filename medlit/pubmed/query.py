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
# Subset safe to drop everywhere, not just at question start.
_ALWAYS_DROP = frozenset({
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
    "pathophysiology", "prognosis", "diagnosis", "management", "efficacy",
    "safety", "prevalence", "incidence", "etiology", "aetiology", "please",
    "short", "long", "new", "current", "recent", "clinical", "any", "list",
    "cases", "case", "groups", "group", "proportion", "assignable",
    "life", "half", "inhibitors", "inhibitor",
})

# Parenthetical abbreviations are often answer-bearing; keep them out of phrases.
_PAREN_RE = re.compile(r"\(([A-Za-z0-9][A-Za-z0-9\-]{0,14})\)")
# Trailing punctuation that would otherwise glue onto phrases.
_TRAILING_PUNCT = " .,;:!?"

_MAX_BLOCKS = 8
_MAX_PHRASE_WORDS = 4


def _informative(phrase: str) -> bool:
    if _is_noise_phrase(phrase):
        return False
    # Normalize hyphenated compounds so "half-life" matches "half life".
    words = phrase.replace("-", " ").split()
    if len(words) == 1:
        w = words[0]
        if w.isdigit():
            return False
        return w.lower() not in _GENERIC_TERMS and len(w) >= 3
    # Phrases whose only signal is a generic word add noise, not recall.
    informative = [w for w in words if w.lower() not in _GENERIC_TERMS]
    # Numeric-only informative words (e.g. "5") don't count as signal.
    informative = [w for w in informative if not w.isdigit()]
    return bool(informative)


def _is_noise_phrase(phrase: str) -> bool:
    """True if a phrase carries no usable signal.

    Covers: pure digits, digit+generic ("5 inhibitor"), and phrases where
    removing generics leaves nothing ("short half life").
    """
    words = phrase.replace("-", " ").split()
    if all(w.isdigit() or w.lower() in _GENERIC_TERMS for w in words):
        return True
    # Mixed digit+content: content words must be >1 char to count.
    content = [w for w in words if not w.isdigit() and w.lower() not in _GENERIC_TERMS]
    if any(w.isdigit() for w in words) and not any(len(w) > 1 for w in content):
        return True
    # Generic-starting phrases are noise unless the phrase is a known
    # property term ("half life") or the generic word is the whole point.
    if phrase.lower() in {"half life", "half-life"}:
        return False
    if words[0].lower() in _GENERIC_TERMS:
        return True
    return False


def _is_domain_term(phrase: str) -> bool:
    """True if the phrase names a concrete entity/drug/class, not a property."""
    lowered = phrase.lower()
    if lowered in {"half-life", "half life", "pharmacokinetic", "pharmacokinetics", "efficacy", "safety", "toxicity", "dosing"}:
        return False
    return _informative(phrase)


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
                "mesh_terms": self._mesh_candidates(value),
                "title_abstract_terms": self._synonymish_terms(value),
                "notes": "Initial term plan; validate MeSH before using [MeSH Terms].",
            })
        return {"concepts": concepts, "filters": {"humans": True, "language": "english"}, "warnings": []}

    def _title_case(self, text: str) -> str:
        return " ".join(part.capitalize() for part in text.split())

    def _mesh_candidates(self, text: str) -> list[str]:
        """MeSH lookups run per cleaned block phrase, not on raw question text."""
        cleaned, _ = self._clean_raw(text)
        candidates = []
        for block in self._content_blocks(cleaned)[:_MAX_BLOCKS]:
            for phrase in self._split_block(block):
                if _informative(phrase):
                    candidates.append(self._title_case(phrase))
        return candidates

    def _clean_raw(self, text: str) -> str:
        """Strip parentheticals and trailing punctuation; keep parenthetical content."""
        abbreviations = _PAREN_RE.findall(text)
        cleaned = _PAREN_RE.sub(" ", text).strip(_TRAILING_PUNCT)
        cleaned = " ".join(cleaned.split())
        return cleaned, abbreviations

    def _content_blocks(self, text: str) -> list[list[str]]:
        """Split text into maximal runs of content words.

        Question openers ("Describe", "Is") and stopwords break runs, so
        "Is Hirschsprung disease a mendelian or a multifactorial disorder?"
        yields ["Hirschsprung", "disease"], ["mendelian"],
        ["multifactorial", "disorder"]. Parentheses break runs too: their
        content (usually an abbreviation) becomes its own block.
        """
        words = re.findall(r"[A-Za-z0-9\-]+|[().,;:!?]", text)
        blocks: list[list[str]] = []
        current: list[str] = []
        first_word = True
        for word in words:
            lowered = word.lower()
            if word in "().,;:!?" or lowered in _QUESTION_WORDS or lowered in _STOPWORDS:
                if current:
                    blocks.append(current)
                    current = []
                # Only the opening word of a question is discarded; elsewhere
                # ("List A and B" vs "shopping list") the word may be content.
                if (not first_word and lowered not in _STOPWORDS
                        and lowered in _QUESTION_WORDS and lowered not in _ALWAYS_DROP):
                    current.append(word)
                first_word = False
                continue
            current.append(word)
            first_word = False
        if current:
            blocks.append(current)
        return blocks

    def _synonymish_terms(self, text: str) -> list[str]:
        cleaned, abbreviations = self._clean_raw(text)
        terms = []
        terms.extend(abbreviations)
        for block in self._content_blocks(cleaned)[:_MAX_BLOCKS]:
            if len(block) == 1:
                if _informative(block[0]):
                    terms.append(block[0])
                continue
            for phrase in self._split_block(block):
                # Keep only the full split and word-drop variants; raw
                # sub-grams like "life Phosphodiesterase" are dropped.
                variants = [phrase] + self._word_drop_variants(phrase)
                for v in variants:
                    # Reject sub-grams that start with a generic word unless the
                    # full phrase also starts with it ("short half life" is OK,
                    # "life Phosphodiesterase" is not).
                    if (v != phrase and v.split()[0].lower() in _GENERIC_TERMS
                            and v.split()[0].lower() != phrase.split()[0].lower()):
                        continue
                    if _informative(v):
                        terms.append(v)
                        hyphenless = v.replace("-", " ")
                        if hyphenless != v:
                            terms.append(hyphenless)
                        hyphenated = v.replace(" ", "-", 1) if "half life" in v.lower() else ""
                        if hyphenated:
                            terms.append(hyphenated)
                        terms.extend(self._singular_variants(v))
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
        if "half life" in lower or "half-life" in lower:
            terms.extend(["half-life", "pharmacokinetics", "pharmacokinetic"])
        if "phosphodiesterase" in lower and "5" in lower:
            terms.extend(["PDE5", "phosphodiesterase type 5 inhibitor"])
        # Strip pure-noise grams: single digit, digit+generic, or all-generic.
        cleaned = []
        for t in terms:
            if _is_noise_phrase(t):
                continue
            cleaned.append(t)
        # Property terms that were filtered out earlier but are known to be
        # useful when combined with a drug class.
        if any("phosphodiesterase" in t.lower() or "pde5" in t.lower() for t in cleaned):
            if "half life" in lower or "half-life" in lower:
                cleaned.append("half-life")
        return sorted(set(t for t in cleaned if t.strip()))

    def _singular_variants(self, phrase: str) -> list[str]:
        """Drop a trailing 's' on the last word so phrases match singular usage.

        "consensus molecular subtypes" -> "consensus molecular subtype".
        Applied only when the phrase itself is plural-looking.
        """
        words = phrase.split()
        variants = []
        if len(words) >= 2 and words[-1].endswith("s") and len(words[-1]) > 3:
            variants.append(" ".join(words[:-1] + [words[-1][:-1]]))
        return variants

    def _word_drop_variants(self, phrase: str) -> list[str]:
        """Drop generic trailing/leading words so phrases match canonical usage.

        "consensus molecular subtype groups" -> "consensus molecular subtype".
        """
        words = phrase.split()
        variants = []
        # Strip leading generic words first ("short half life" -> "half life").
        while len(words) >= 2 and words[0].lower() in _GENERIC_TERMS:
            words = words[1:]
        # Then strip trailing generic words ("subtype groups" -> "subtype").
        while len(words) >= 2 and words[-1].lower() in _GENERIC_TERMS:
            words = words[:-1]
        if len(words) >= 2 and " ".join(words) != phrase:
            variants.append(" ".join(words))
            variants.extend(self._singular_variants(" ".join(words)))
        return variants

    def _split_block(self, block: list[str]) -> list[str]:
        """Emit phrase candidates from a content block.

        Short blocks pass through. Long runs are unlikely to be real phrases,
        so emit tail grams ("Phosphodiesterase 5 inhibitors") plus bigrams
        ("half life", "colorectal cancer").
        """
        if len(block) <= _MAX_PHRASE_WORDS:
            return [" ".join(block)]
        grams = []
        # Prefer the tail: last 2, 3, and 4 words ("Phosphodiesterase 5 inhibitors").
        tail = [" ".join(block[i:]) for i in range(max(len(block) - 4, 0), len(block) - 1)]
        grams.extend(g for g in tail if 2 <= len(g.split()) <= 4)
        # Only keep bigrams/trigrams that don't start with a generic word;
        # they add noise without precision. Tail grams are always kept.
        for i in range(len(block) - 1):
            bigram = " ".join(block[i:i + 2])
            if (not bigram.split()[0].isdigit() and not bigram.split()[-1].isdigit()
                    and bigram.split()[0].lower() not in _GENERIC_TERMS):
                grams.append(bigram)
        for i in range(len(block) - 2):
            trigram = " ".join(block[i:i + 3])
            if (not trigram.split()[0].isdigit() and not trigram.split()[-1].isdigit()
                    and trigram.split()[0].lower() not in _GENERIC_TERMS):
                grams.append(trigram)
        seen = []
        for gram in grams:
            if gram not in seen and _informative(gram):
                seen.append(gram)
        # Also include the longest informative tail gram even if it starts
        # with a generic word (it may contain the full entity name).
        for g in tail:
            if g not in seen and _informative(g):
                seen.insert(0, g)
        # Keep only the most specific phrases: drop any phrase that is a
        # sub-phrase of another kept phrase.
        deduped = []
        for phrase in seen:
            if any(phrase != other and phrase in other for other in seen):
                continue
            deduped.append(phrase)
        return deduped[:8]


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
                    for entry in (val.get("entry_terms") or [])[:3]:
                        if entry.lower() != preferred.lower():
                            parts.append(f'"{entry}"[Title/Abstract]')
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

        # AND-of-terms variant: improves precision for noisy single-concept
        # questions by requiring the two most specific phrases to co-occur.
        # Falls back to OR between the two halves if AND would return nothing.
        and_query = ""
        concept = next(iter(term_plan.get("concepts", [])), {})
        informative_ta = [
            t for t in concept.get("title_abstract_terms", [])
            if _informative(t) and not t.isupper()
        ]
        # Rank by word count (most specific first) and take the top 2 so the
        # AND stays tight but not over-constrained.
        ranked = sorted(informative_ta, key=lambda t: len(t.split()), reverse=True)
        deduped = []
        for t in ranked:
            if any(t.rstrip("s") == kept.rstrip("s") for kept in deduped):
                continue
            deduped.append(t)
        if len(deduped) >= 2:
            and_query = " AND ".join(f'"{t}"[Title/Abstract]' for t in deduped[:2])

        # Drug-class + property variant: catches "short half life PDE5
        # inhibitors" style questions where the class is MeSH-indexed and the
        # property is a free-text concept.
        drugclass_query = ""
        mesh_terms = []
        for part in (blocks_by_concept.get("population", "") or "").split(" OR "):
            part = part.strip().strip("()")
            if "[MeSH Terms]" in part:
                mesh_terms.append(part.split('"')[1])
        ta_singles = [t for t in concept.get("title_abstract_terms", [])
                      if _is_domain_term(t) and len(t.split()) <= 3]
        # Property terms (non-domain) that can be ANDed with a MeSH class.
        ta_props = [t for t in concept.get("title_abstract_terms", [])
                    if _informative(t) and not _is_domain_term(t)]
        # "half-life" is a property term even though _is_domain_term returns False.
        if "half-life" in concept.get("title_abstract_terms", []) and "half-life" not in ta_props:
            ta_props.append("half-life")
        if mesh_terms and (ta_singles or ta_props):
            # Use TA synonyms only (no MeSH) so papers not yet MeSH-indexed
            # are still caught. Prefer longer (more specific) phrases, but
            # keep the shortest one too (e.g. "PDE5") for recall.
            ranked = sorted(ta_singles, key=lambda t: len(t.split()), reverse=True)
            left_terms = ranked[:3]
            # Always include the shortest domain term (highest recall).
            if ta_singles:
                shortest = min(ta_singles, key=lambda t: len(t.split()))
                if shortest not in left_terms:
                    left_terms.append(shortest)
            left = " OR ".join(f'"{t}"[Title/Abstract]' for t in left_terms[:4])
            right_terms = (ta_props + ta_singles[3:])[:3]
            right = " OR ".join(f'"{t}"[Title/Abstract]' for t in right_terms)
            drugclass_query = f"({left}) AND ({right})"

        ladder = []
        if base:
            ladder.append({"query_id": "Q1_broad_conceptual", "purpose": "Broad concept query for recall", "exact_query": base, "source": "tool_generated", "executed": False})
        if and_query:
            ladder.append({"query_id": "Q1b_and_terms", "purpose": "All informative phrases ANDed for precision", "exact_query": and_query, "source": "tool_generated", "executed": False})
        if drugclass_query and drugclass_query != and_query:
            ladder.append({"query_id": "Q1c_drugclass_property", "purpose": "MeSH drug class AND free-text property", "exact_query": drugclass_query, "source": "tool_generated", "executed": False})
        if focused and focused != base:
            ladder.append({"query_id": "Q2_focused_primary", "purpose": "Focused query with basic filters", "exact_query": focused, "source": "tool_generated", "executed": False})
        if comparator_base and comparator_base != base:
            ladder.append({"query_id": "Q3_with_comparator", "purpose": "Narrow query including comparator terms", "exact_query": comparator_base, "source": "tool_generated", "executed": False})
        if focused:
            ladder.append({"query_id": "Q4_reviews", "purpose": "Systematic review/meta-analysis oriented query", "exact_query": f"({focused}) AND (systematic review[Publication Type] OR meta-analysis[Publication Type])", "source": "tool_generated", "executed": False})
            ladder.append({"query_id": "Q5_trials", "purpose": "Clinical trial oriented query", "exact_query": f"({focused}) AND (clinical trial[Publication Type] OR randomized controlled trial[Publication Type])", "source": "tool_generated", "executed": False})
        return ladder
