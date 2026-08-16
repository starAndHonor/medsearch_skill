"""Parse localized XML/HTML/PDF/abstract content into text files."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FulltextParser:
    def parse_manifests(self, manifests: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_pmid = {str(r.get("pmid", "")): r for r in records}
        parsed = []
        for manifest in manifests:
            parsed.append(self.parse_one(manifest, by_pmid.get(str(manifest.get("pmid", "")), {})))
        return parsed

    def parse_one(self, manifest: dict[str, Any], record: dict[str, Any] | None = None) -> dict[str, Any]:
        files = manifest.get("local_files", {})
        text = ""
        method = ""
        if files.get("xml") and Path(files["xml"]).exists():
            text = self._parse_xml(Path(files["xml"]))
            method = "xml"
        elif files.get("html") and Path(files["html"]).exists():
            text = self._parse_html(Path(files["html"]))
            method = "html"
        elif files.get("pdf") and Path(files["pdf"]).exists():
            text = self._parse_pdf_placeholder(Path(files["pdf"]))
            method = "pdf_placeholder"
        elif record and record.get("abstract"):
            text = f"# {record.get('title', '')}\n\n## Abstract\n\n{record.get('abstract', '')}\n"
            method = "abstract"
        else:
            method = "unavailable"

        parsed_path = ""
        if text:
            base = Path(files.get("metadata", ".")).parent
            path = base / "parsed_text.md"
            path.write_text(text, encoding="utf-8")
            parsed_path = str(path)
            manifest.setdefault("local_files", {})["parsed_text"] = parsed_path
        return {
            "pmid": manifest.get("pmid", ""),
            "doi": manifest.get("doi", ""),
            "source_granularity": "fulltext" if method in {"xml", "html", "pdf_placeholder"} else "abstract",
            "parse_method": method,
            "parsed_text": parsed_path,
            "status": "parsed" if text else "unavailable",
        }

    def _parse_xml(self, path: Path) -> str:
        raw = path.read_text(encoding="utf-8", errors="replace")
        root = ET.fromstring(raw)
        title = self._text_any(root, [".//article-title", ".//title"])
        chunks = [f"# {title}\n" if title else "# Full Text\n"]
        for sec in root.findall(".//sec"):
            sec_title = self._text_any(sec, ["title"])
            if sec_title:
                chunks.append(f"\n## {sec_title}\n")
            paragraphs = [" ".join("".join(p.itertext()).split()) for p in sec.findall(".//p")]
            for paragraph in paragraphs:
                if paragraph:
                    chunks.append(paragraph + "\n")
        if len(chunks) <= 1:
            text = re.sub(r"<[^>]+>", " ", raw)
            chunks.append(" ".join(text.split()))
        return "\n".join(chunks)

    def _parse_html(self, path: Path) -> str:
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return "# Full Text\n\n" + " ".join(text.split()) + "\n"

    def _parse_pdf_placeholder(self, path: Path) -> str:
        # Keep MVP stdlib-only. If PyMuPDF/pdfplumber is installed, users can
        # add an optional parser later without changing the state contract.
        return (
            "# PDF Localized\n\n"
            f"PDF saved locally at `{path}`. Text extraction dependency is not installed in the stdlib MVP. "
            "Use abstract fallback or add an optional PDF parser backend.\n"
        )

    def _text_any(self, root: ET.Element, paths: list[str]) -> str:
        for path in paths:
            elem = root.find(path)
            if elem is not None:
                text = " ".join("".join(elem.itertext()).split())
                if text:
                    return text
        return ""
