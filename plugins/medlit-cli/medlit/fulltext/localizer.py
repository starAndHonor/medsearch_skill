"""Open-access full-text localization and download attempts."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from medlit.http import HttpClient, NetworkBlockedError


PMC_IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UNPAYWALL = "https://api.unpaywall.org/v2"


@dataclass
class FulltextLocalizer:
    http: HttpClient
    output_dir: Path

    def localize_records(self, records: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
        manifests = []
        for record in records[: limit or len(records)]:
            manifests.append(self.localize(record))
        return manifests

    def localize(self, record: dict[str, Any]) -> dict[str, Any]:
        pmid = str(record.get("pmid", ""))
        doi = str(record.get("doi", ""))
        pmcid = str(record.get("pmcid", ""))
        paper_dir = self.output_dir / "papers" / (pmid or self._safe_id(doi) or "unknown")
        paper_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = paper_dir / "metadata.json"
        metadata_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        manifest = {
            "pmid": pmid,
            "doi": doi,
            "pmcid": pmcid,
            "title": record.get("title", ""),
            "fulltext_status": "not_attempted",
            "sources_tried": [],
            "local_files": {"metadata": str(metadata_path), "xml": "", "html": "", "pdf": "", "parsed_text": ""},
            "license": "",
            "accessed_at": date.today().isoformat(),
        }

        if not pmcid:
            pmcid = self._lookup_pmcid(pmid, doi, manifest)
            manifest["pmcid"] = pmcid

        if pmcid:
            self._try_europe_pmc_xml(pmcid, paper_dir, manifest)
            if manifest["fulltext_status"].endswith("downloaded"):
                return manifest
            self._try_europe_pmc_pdf(pmcid, paper_dir, manifest)
            if manifest["fulltext_status"].endswith("downloaded"):
                return manifest

        if doi:
            self._try_unpaywall_pdf(doi, paper_dir, manifest)
            if manifest["fulltext_status"].endswith("downloaded"):
                return manifest

        if record.get("abstract"):
            manifest["fulltext_status"] = "abstract_only"
            manifest["sources_tried"].append({"source": "pubmed_abstract", "status": "fallback", "reason": "No open full text located; abstract is available."})
        else:
            manifest["fulltext_status"] = "unavailable"
        return manifest

    def _lookup_pmcid(self, pmid: str, doi: str, manifest: dict[str, Any]) -> str:
        ids = pmid or doi
        if not ids:
            manifest["sources_tried"].append({"source": "pmc_id_converter", "status": "skipped", "reason": "No PMID or DOI."})
            return ""
        try:
            params = urllib.parse.urlencode({"ids": ids, "format": "json", "tool": "medlit-cli", "email": os.environ.get("MEDLIT_EMAIL", "noreply@example.com")})
            data = self.http.get_json(f"{PMC_IDCONV}?{params}")
            records = data.get("records", [])
            pmcid = records[0].get("pmcid", "") if records else ""
            manifest["sources_tried"].append({"source": "pmc_id_converter", "status": "ok" if pmcid else "miss", "reason": "" if pmcid else "No PMCID returned."})
            return pmcid
        except Exception as exc:
            manifest["sources_tried"].append({"source": "pmc_id_converter", "status": "failed", "reason": str(exc)})
            return ""

    def _try_europe_pmc_xml(self, pmcid: str, paper_dir: Path, manifest: dict[str, Any]) -> None:
        try:
            url = f"{EUROPE_PMC}/{pmcid}/fullTextXML"
            text = self.http.get_text(url)
            if "<" in text[:100] and len(text) > 500:
                path = paper_dir / "fulltext.xml"
                path.write_text(text, encoding="utf-8")
                manifest["local_files"]["xml"] = str(path)
                manifest["fulltext_status"] = "xml_downloaded"
                manifest["sources_tried"].append({"source": "europe_pmc_fulltext_xml", "status": "ok", "url": url})
                return
            manifest["sources_tried"].append({"source": "europe_pmc_fulltext_xml", "status": "failed", "reason": "Response was not usable XML.", "url": url})
        except Exception as exc:
            manifest["sources_tried"].append({"source": "europe_pmc_fulltext_xml", "status": "failed", "reason": str(exc)})

    def _try_europe_pmc_pdf(self, pmcid: str, paper_dir: Path, manifest: dict[str, Any]) -> None:
        try:
            url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={urllib.parse.quote(pmcid)}&blobtype=pdf"
            raw = self.http.get_bytes(url)
            if raw.startswith(b"%PDF-") and len(raw) > 10_000:
                path = paper_dir / "paper.pdf"
                path.write_bytes(raw)
                manifest["local_files"]["pdf"] = str(path)
                manifest["fulltext_status"] = "pdf_downloaded"
                manifest["sources_tried"].append({"source": "europe_pmc_pdf", "status": "ok", "url": url})
                return
            manifest["sources_tried"].append({"source": "europe_pmc_pdf", "status": "failed", "reason": "Response was not a valid PDF.", "url": url})
        except Exception as exc:
            manifest["sources_tried"].append({"source": "europe_pmc_pdf", "status": "failed", "reason": str(exc)})

    def _try_unpaywall_pdf(self, doi: str, paper_dir: Path, manifest: dict[str, Any]) -> None:
        email = os.environ.get("UNPAYWALL_EMAIL") or os.environ.get("MEDLIT_EMAIL")
        if not email:
            manifest["sources_tried"].append({"source": "unpaywall", "status": "skipped", "reason": "Set UNPAYWALL_EMAIL or MEDLIT_EMAIL to use Unpaywall."})
            return
        try:
            url = f"{UNPAYWALL}/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}"
            data = self.http.get_json(url)
            loc = data.get("best_oa_location") or {}
            pdf_url = loc.get("url_for_pdf") or ""
            manifest["license"] = loc.get("license") or data.get("license") or ""
            if not pdf_url:
                manifest["sources_tried"].append({"source": "unpaywall", "status": "miss", "reason": "No url_for_pdf.", "url": url})
                return
            raw = self.http.get_bytes(pdf_url, headers={"User-Agent": "medlit-cli/0.1"})
            if raw.startswith(b"%PDF-") and len(raw) > 10_000:
                path = paper_dir / "paper.pdf"
                path.write_bytes(raw)
                manifest["local_files"]["pdf"] = str(path)
                manifest["fulltext_status"] = "pdf_downloaded"
                manifest["sources_tried"].append({"source": "unpaywall_pdf", "status": "ok", "url": pdf_url})
                return
            manifest["sources_tried"].append({"source": "unpaywall_pdf", "status": "failed", "reason": "Downloaded bytes were not a valid PDF.", "url": pdf_url})
        except Exception as exc:
            manifest["sources_tried"].append({"source": "unpaywall", "status": "failed", "reason": str(exc)})

    def _safe_id(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "_", value)[:80]
