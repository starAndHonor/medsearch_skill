"""MeSH validation through NCBI E-utilities."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from medlit.http import HttpClient, ncbi_identity, urlencode


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class MeshValidator:
    http: HttpClient

    def validate_term_plan(self, term_plan: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for concept in term_plan.get("concepts", []):
            for candidate in concept.get("mesh_terms", []):
                out.append(self.validate(candidate, concept.get("name", ""), concept.get("title_abstract_terms", [])))
        return out

    def validate(self, candidate: str, concept: str = "", fallback_terms: list[str] | None = None) -> dict[str, Any]:
        cleaned = self._clean(candidate)
        if not cleaned:
            return {"candidate": candidate, "concept": concept, "status": "empty", "fallback_terms": fallback_terms or [], "warning": "Empty MeSH candidate."}
        try:
            summaries = self._fetch(cleaned)
            return self._parse_summary(candidate, cleaned, concept, fallback_terms or [], summaries)
        except Exception as exc:
            return {
                "candidate": candidate,
                "concept": concept,
                "status": "fallback",
                "preferred_term": "",
                "entry_terms": [],
                "tree_numbers": [],
                "field_tag": "Title/Abstract",
                "fallback_terms": fallback_terms or [cleaned],
                "warning": f"MeSH lookup failed; use Title/Abstract fallback. {exc}",
            }

    def _fetch(self, term: str) -> list[dict[str, Any]]:
        params = {"db": "mesh", "term": f'"{term}"[MeSH Terms] OR "{term}"[Title]', "retmode": "xml"}
        params.update(ncbi_identity())
        history = self.http.get_text(f"{EUTILS_BASE}/esearch.fcgi?{urlencode(params)}")
        ids = []
        try:
            root = ET.fromstring(history)
            ids = [elem.text for elem in root.findall(".//Id") if elem.text]
        except ET.ParseError:
            pass
        if not ids:
            return []
        fetch_params = {"db": "mesh", "id": ",".join(ids[:5]), "retmode": "json"}
        fetch_params.update(ncbi_identity())
        data = self.http.get_json(f"{EUTILS_BASE}/esummary.fcgi?{urlencode(fetch_params)}")
        result = data.get("result", {})
        return [result[uid] for uid in result.get("uids", []) if uid in result]

    def _parse_summary(self, candidate: str, cleaned: str, concept: str, fallback_terms: list[str], summaries: list[dict[str, Any]]) -> dict[str, Any]:
        if not summaries:
            return {"candidate": candidate, "concept": concept, "status": "fallback", "preferred_term": "", "entry_terms": [], "tree_numbers": [], "field_tag": "Title/Abstract", "fallback_terms": fallback_terms or [cleaned], "warning": "No MeSH record returned."}
        best = self._best_summary(cleaned, summaries)
        mesh_terms = [self._norm(term) for term in best.get("ds_meshterms", []) if term]
        preferred = mesh_terms[0] if mesh_terms else ""
        entry_terms = mesh_terms[1:]
        tree_numbers = [self._norm(str(item.get("treenum", ""))) for item in best.get("ds_idxlinks", []) if item.get("treenum")]
        if preferred and self._same(cleaned, preferred):
            status = "valid"
        elif any(self._same(cleaned, item) for item in entry_terms):
            status = "entry_term"
        else:
            status = "candidate_mismatch"
        return {
            "candidate": candidate,
            "concept": concept,
            "status": status if status in {"valid", "entry_term"} else "fallback",
            "preferred_term": preferred,
            "entry_terms": entry_terms,
            "tree_numbers": tree_numbers,
            "field_tag": "MeSH Terms" if status in {"valid", "entry_term"} else "Title/Abstract",
            "fallback_terms": fallback_terms,
            "warning": "" if status in {"valid", "entry_term"} else "Candidate did not cleanly map to a MeSH heading.",
        }

    def _best_summary(self, cleaned: str, summaries: list[dict[str, Any]]) -> dict[str, Any]:
        for item in summaries:
            terms = [self._norm(term) for term in item.get("ds_meshterms", []) if term]
            if terms and self._same(cleaned, terms[0]):
                return item
        for item in summaries:
            terms = [self._norm(term) for term in item.get("ds_meshterms", []) if term]
            if any(self._same(cleaned, term) for term in terms[1:]):
                return item
        return summaries[0]

    def _clean(self, text: str) -> str:
        return self._norm(text.replace('"', "").replace("*", "").split("/", 1)[0])

    def _norm(self, text: str) -> str:
        return " ".join(text.split())

    def _same(self, left: str, right: str) -> bool:
        return self._norm(left).lower() == self._norm(right).lower()

    def _first(self, root: ET.Element, paths: list[str]) -> str:
        for path in paths:
            elem = root.find(path)
            if elem is not None and elem.text:
                return self._norm(elem.text)
        return ""
