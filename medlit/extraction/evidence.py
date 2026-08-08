"""Evidence extraction from parsed text.

This MVP uses deterministic extraction to create a grounded first pass. Codex
can then read the local parsed text and refine the evidence if needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NUMBER_PATTERNS = [
    r"\b(?:HR|OR|RR)\s*[=:]?\s*\d+(?:\.\d+)?(?:\s*\([^)]+\))?",
    r"\b95%\s*CI\s*[,=:]?\s*[^.;\n]+",
    r"\bp\s*[<=>]\s*0?\.\d+",
    r"\b\d+(?:\.\d+)?%",
    r"\bN\s*=\s*\d+",
]


@dataclass
class EvidenceExtractor:
    max_chars: int = 20000

    def extract(self, parsed_sources: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_pmid = {str(r.get("pmid", "")): r for r in records}
        out = []
        for item in parsed_sources:
            pmid = str(item.get("pmid", ""))
            path = item.get("parsed_text", "")
            record = by_pmid.get(pmid, {})
            if not path or not Path(path).exists():
                out.append(self._failed(pmid, record, "No parsed text file available."))
                continue
            text = Path(path).read_text(encoding="utf-8", errors="replace")[: self.max_chars]
            out.append(self._extract_one(pmid, record, text, item))
        return out

    def _extract_one(self, pmid: str, record: dict[str, Any], text: str, parsed: dict[str, Any]) -> dict[str, Any]:
        numbers = self._numbers(text)
        study_design = self._study_design(record, text)
        return {
            "paper_ref": pmid or record.get("doi", ""),
            "title": record.get("title", ""),
            "source_granularity": parsed.get("source_granularity", "abstract"),
            "study_design": study_design,
            "population": self._best_sentence(text, ["patient", "participant", "population", "adult", "children"]),
            "methods": self._section_or_sentence(text, "method", ["random", "cohort", "trial", "study"]),
            "main_results": self._section_or_sentence(text, "result", ["result", "significant", "improved", "reduced", "associated"]),
            "numbers": numbers[:12],
            "limitations": self._section_or_sentence(text, "limitation", ["limitation", "bias", "small sample"]),
            "matched_pico": [],
            "local_source": parsed.get("parsed_text", ""),
            "extraction_status": "ok",
        }

    def _failed(self, pmid: str, record: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            "paper_ref": pmid or record.get("doi", ""),
            "title": record.get("title", ""),
            "source_granularity": "none",
            "study_design": "",
            "population": "",
            "methods": "",
            "main_results": "",
            "numbers": [],
            "limitations": reason,
            "matched_pico": [],
            "local_source": "",
            "extraction_status": "failed",
        }

    def _numbers(self, text: str) -> list[str]:
        hits = []
        for pattern in NUMBER_PATTERNS:
            hits.extend(re.findall(pattern, text, flags=re.I))
        return sorted(set(" ".join(hit.split()) for hit in hits), key=len, reverse=True)

    def _study_design(self, record: dict[str, Any], text: str) -> str:
        pub_types = " ".join(record.get("publication_types", [])).lower()
        lower = text.lower()
        for label, needles in [
            ("systematic_review_or_meta_analysis", ["systematic review", "meta-analysis", "meta analysis"]),
            ("randomized_controlled_trial", ["randomized controlled trial", "randomised controlled trial"]),
            ("clinical_trial", ["clinical trial"]),
            ("cohort_study", ["cohort"]),
            ("case_control_study", ["case-control", "case control"]),
            ("cross_sectional_study", ["cross-sectional", "cross sectional"]),
            ("case_report", ["case report"]),
        ]:
            if any(n in pub_types or n in lower for n in needles):
                return label
        return "unclassified"

    def _section_or_sentence(self, text: str, section_name: str, keywords: list[str]) -> str:
        match = re.search(rf"(?is)##\s*{section_name}[^\n]*\n(.+?)(?:\n##\s+|\Z)", text)
        if match:
            return self._trim(match.group(1))
        return self._best_sentence(text, keywords)

    def _best_sentence(self, text: str, keywords: list[str]) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
        for sentence in sentences:
            lower = sentence.lower()
            if any(k in lower for k in keywords):
                return self._trim(sentence)
        return self._trim(sentences[0] if sentences else "")

    def _trim(self, text: str, limit: int = 900) -> str:
        text = " ".join(text.split())
        return text[:limit] + ("..." if len(text) > limit else "")

