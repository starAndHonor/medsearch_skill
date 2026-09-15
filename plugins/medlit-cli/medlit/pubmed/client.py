"""PubMed access through NCBI E-utilities REST APIs."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from typing import Any

from medlit.http import ApiError, HttpClient, NetworkBlockedError, ncbi_identity, urlencode


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class PubMedClient:
    http: HttpClient
    retmax: int = 20

    def search(self, query: str, retmax: int | None = None, maxdate: str = "") -> dict[str, Any]:
        term = query
        if maxdate:
            # Use an explicit publication-date clause. NCBI's maxdate parameter
            # does not consistently constrain ahead-of-print records.
            term = f'({query}) AND ("1900/01/01"[Date - Publication] : "{maxdate}"[Date - Publication])'
        requested_retmax = self.retmax if retmax is None else retmax
        params = {"db": "pubmed", "term": term, "retmax": requested_retmax, "retmode": "json", "sort": "relevance"}
        params.update(ncbi_identity())
        url = f"{EUTILS_BASE}/esearch.fcgi?{urlencode(params)}"
        data = self.http.get_json(url)
        if not isinstance(data, dict) or "esearchresult" not in data or data.get("error"):
            raise ApiError("Unexpected or unsuccessful PubMed ESearch response")
        result = data.get("esearchresult", {})
        return {
            "query": query,
            "effective_query": term,
            "count": int(result.get("count", "0")),
            "pmids": [str(pmid) for pmid in result.get("idlist", [])],
            "query_translation": result.get("querytranslation", ""),
            "translationset": result.get("translationset", []),
            "warninglist": result.get("warninglist", {}),
            "errorlist": result.get("errorlist", {}),
            "retmax": requested_retmax,
            "sort": "relevance",
            "raw_esearch": data,
        }

    def fetch_records(self, pmids: list[str]) -> list[dict[str, Any]]:
        if not pmids:
            return []
        params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml", "rettype": "xml"}
        params.update(ncbi_identity())
        url = f"{EUTILS_BASE}/efetch.fcgi?{urlencode(params)}"
        xml_text = self.http.get_text(url)
        self.last_fetch_xml = xml_text
        records = self.parse_records(xml_text)
        by_pmid = {record.get("pmid"): record for record in records}
        return [by_pmid[pmid] for pmid in pmids if pmid in by_pmid]

    def parse_records(self, xml_text: str) -> list[dict[str, Any]]:
        root = ET.fromstring(xml_text)
        out = []
        for article in root.findall(".//PubmedArticle"):
            pmid = self._text(article, ".//MedlineCitation/PMID")
            title_el = article.find(".//Article/ArticleTitle")
            title = " ".join("".join(title_el.itertext()).split()) if title_el is not None else ""
            abstract_parts = []
            for elem in article.findall(".//Abstract/AbstractText"):
                label = elem.attrib.get("Label", "")
                text = " ".join("".join(elem.itertext()).split())
                if text:
                    abstract_parts.append(f"{label}: {text}" if label else text)
            ids = {}
            for elem in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if elem.text:
                    ids[elem.attrib.get("IdType", "")] = elem.text.strip()
            pub_types = [self._clean_text(elem.text or "") for elem in article.findall(".//PublicationType")]
            out.append({
                "pmid": pmid,
                "pmcid": ids.get("pmc", ""),
                "doi": ids.get("doi", ""),
                "title": html.unescape(title),
                "abstract": "\n".join(abstract_parts),
                "journal": self._text(article, ".//Journal/Title"),
                "year": self._year(article),
                "authors": self._authors(article),
                "mesh_terms": [self._clean_text("".join(elem.itertext())) for elem in article.findall(".//MeshHeading/DescriptorName")],
                "publication_types": pub_types,
                "trial_ids": sorted(set(re.findall(r"\bNCT\d{8}\b", " ".join(abstract_parts)))),
                "source": "pubmed",
                "verified": bool(pmid),
                "verified_by": "pubmed",
                "verified_on": date.today().isoformat(),
            })
        return out

    def _text(self, root: ET.Element, path: str) -> str:
        elem = root.find(path)
        return self._clean_text(elem.text or "") if elem is not None else ""

    def _clean_text(self, text: str) -> str:
        return " ".join(text.split())

    def _year(self, article: ET.Element) -> str:
        year = self._text(article, ".//PubDate/Year")
        if year:
            return year[:4]
        medline = self._text(article, ".//PubDate/MedlineDate")
        match = re.search(r"\d{4}", medline)
        return match.group(0) if match else ""

    def _authors(self, article: ET.Element) -> list[str]:
        authors = []
        for author in article.findall(".//Author"):
            coll = self._text(author, "CollectiveName")
            if coll:
                authors.append(coll)
                continue
            last = self._text(author, "LastName")
            fore = self._text(author, "ForeName")
            if last and fore:
                authors.append(f"{last} {fore}")
            elif last:
                authors.append(last)
        return authors
