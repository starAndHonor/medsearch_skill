#!/usr/bin/env python
"""Convert raw BioASQ JSON into the medlit-cli benchmark format."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a raw BioASQ JSON file into the medlit-cli benchmark format."
    )
    parser.add_argument("--input", required=True, help="Path to raw BioASQ JSON file.")
    parser.add_argument(
        "--output", default="evals/bioasq_benchmark.json", help="Path for the converted benchmark."
    )
    parser.add_argument(
        "--source-name",
        default="",
        help="Source label for each question (e.g. BioASQ-2024-training). If empty, inferred from input file name.",
    )
    return parser.parse_args(argv)


def load_raw(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "questions" in data:
        return data
    if isinstance(data, list):
        return {"questions": data}
    raise ValueError("Expected BioASQ data to contain a 'questions' key or be a list of questions.")


def extract_pmids(documents: list[str]) -> list[str]:
    """Normalize document references to plain PMIDs."""
    pmids: list[str] = []
    for doc in documents or []:
        doc = str(doc).strip()
        if not doc:
            continue
        # Handle URLs like http://www.ncbi.nlm.nih.gov/pubmed/12345
        m = re.search(r"/pubmed/(\d+)", doc)
        if m:
            pmids.append(m.group(1))
            continue
        if doc.isdigit():
            pmids.append(doc)
    return pmids


def normalize_answer_type(raw_type: str) -> str:
    t = (raw_type or "").lower().strip()
    if t in {"yesno", "yes/no"}:
        return "yesno"
    if t in {"factoid"}:
        return "factoid"
    if t in {"list"}:
        return "list"
    if t in {"summary"}:
        return "summary"
    return t or "summary"


def extract_gold_answer(q: dict[str, Any], qtype: str) -> str | list[str] | None:
    exact = q.get("exact_answer")
    if qtype == "yesno":
        if isinstance(exact, list):
            exact = exact[0] if exact else None
        text = str(exact).lower().strip() if exact is not None else ""
        if text in {"yes", "true", "y"}:
            return "yes"
        if text in {"no", "false", "n"}:
            return "no"
        ideal = q.get("ideal_answer")
        if isinstance(ideal, list):
            ideal = ideal[0] if ideal else ""
        if ideal:
            first_sentence = str(ideal).lower()
            if first_sentence.startswith("yes"):
                return "yes"
            if first_sentence.startswith("no"):
                return "no"
        return None

    if qtype == "factoid":
        # Gold is a synonym group (list of acceptable surface forms).
        if isinstance(exact, list):
            if not exact:
                return []
            first = exact[0]
            if isinstance(first, list):
                return [str(s) for s in first if str(s).strip()]
            return [str(first)]
        if exact is not None:
            return [str(exact)]
        return []

    if qtype == "list":
        if isinstance(exact, list):
            # Preserve BioASQ nested structure: outer = answer items,
            # inner = synonym groups (official synonym-aware scoring).
            groups: list[list[str]] = []
            for item in exact:
                if isinstance(item, list):
                    groups.append([str(s) for s in item if str(s).strip()])
                else:
                    groups.append([str(item)])
            return groups
        if exact is not None:
            return [[str(exact)]]
        return []

    return None


def extract_ideal_answer(q: dict[str, Any]) -> str:
    ideal = q.get("ideal_answer")
    if isinstance(ideal, list):
        return " ".join(str(x) for x in ideal if x)
    return str(ideal) if ideal is not None else ""


def convert_question(q: dict[str, Any], source: str) -> dict[str, Any]:
    qtype = normalize_answer_type(q.get("type", ""))
    gold_answer = extract_gold_answer(q, qtype)
    ideal_answer = extract_ideal_answer(q)
    return {
        "id": str(q.get("id", "")),
        "question": str(q.get("body", q.get("question", ""))).strip(),
        "type": qtype,
        "gold_pmids": extract_pmids(q.get("documents", [])),
        "gold_answer": gold_answer,
        "ideal_answer": ideal_answer,
        "source": source,
    }


def infer_source_name(path: Path, provided: str) -> str:
    if provided:
        return provided
    stem = path.stem
    # Try to extract a task label like training10b, test10b, task10a from the filename.
    m = re.search(r"(?:training|test|task)?\s*(\d+[ab]?)", stem, re.IGNORECASE)
    if m:
        return f"BioASQ-{m.group(1).upper()}"
    return "BioASQ"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    in_path = Path(args.input)
    out_path = Path(args.output)
    source = infer_source_name(in_path, args.source_name)

    raw = load_raw(in_path)
    questions = [convert_question(q, source) for q in raw.get("questions", [])]

    benchmark = {
        "name": f"bioasq-{source.lower().replace(' ', '-')}",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "count": len(questions),
        "questions": questions,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Converted {len(questions)} questions -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
