#!/usr/bin/env python
"""Score medlit-cli outputs against a BioASQ-style benchmark."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure the repository root is on path.
ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score medlit-cli outputs against a BioASQ benchmark."
    )
    parser.add_argument("--work-dir", default="evals/runs", help="Directory containing per-question state files.")
    parser.add_argument("--benchmark", default="evals/bioasq_benchmark.json", help="Path to benchmark JSON.")
    parser.add_argument("--output-dir", default="evals/results", help="Directory for scores.json and scores.csv.")
    return parser.parse_args(argv)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_id(raw_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(raw_id)).strip("-") or "q"


def pred_pmids_from_state(state: dict[str, Any]) -> list[str]:
    """Return ranked, de-duplicated predicted PMIDs from retrieval_runs."""
    seen: set[str] = set()
    out: list[str] = []
    for run in state.get("retrieval_runs", []):
        for pmid in run.get("pmids", []):
            s = str(pmid)
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def token_f1(pred: str, gold: str) -> dict[str, float]:
    p_tok = tokens(pred)
    g_tok = tokens(gold)
    tp = len(p_tok & g_tok)
    precision = tp / len(p_tok) if p_tok else 0.0
    recall = tp / len(g_tok) if g_tok else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def precision_at_k(pred: list[str], gold: list[str], k: int) -> float:
    pred_k = pred[:k]
    if not pred_k:
        return 0.0
    gold_set = set(gold)
    return len([p for p in pred_k if p in gold_set]) / len(pred_k)


def recall_at_k(pred: list[str], gold: list[str], k: int) -> float:
    pred_k = pred[:k]
    gold_set = set(gold)
    if not gold_set:
        return 0.0
    return len([p for p in pred_k if p in gold_set]) / len(gold_set)


def f1_at_k(pred: list[str], gold: list[str], k: int) -> float:
    p = precision_at_k(pred, gold, k)
    r = recall_at_k(pred, gold, k)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def retrieval_metrics(pred: list[str], gold: list[str]) -> dict[str, float]:
    return {
        "p@5": precision_at_k(pred, gold, 5),
        "p@10": precision_at_k(pred, gold, 10),
        "p@20": precision_at_k(pred, gold, 20),
        "r@10": recall_at_k(pred, gold, 10),
        "r@20": recall_at_k(pred, gold, 20),
        "f1@10": f1_at_k(pred, gold, 10),
        "f1@20": f1_at_k(pred, gold, 20),
    }


def extract_report_answer(report_md: str) -> str:
    """Extract the answer/conclusion portion of report.md."""
    if not report_md:
        return ""
    # Try to capture the first paragraph after an explicit answer/conclusion heading.
    for heading in ["## Conclusion", "## Answer", "## Evidence", "## Status"]:
        idx = report_md.find(heading)
        if idx != -1:
            start = idx + len(heading)
            end = report_md.find("\n##", start + 1)
            block = report_md[start:end if end != -1 else None].strip()
            block = re.sub(r"^\s*\n+", "", block)
            block = re.sub(r"\n+\s*$", "", block)
            if block:
                return block
    return report_md.strip()


def normalize_yes_no(text: str) -> str:
    t = text.lower().strip()
    if t.startswith("yes") or t.startswith("y ") or t == "y":
        return "yes"
    if t.startswith("no") or t == "n":
        return "no"
    return t


def score_yesno(pred_text: str, gold: str) -> dict[str, Any]:
    pred = normalize_yes_no(pred_text[:50])
    gold_norm = normalize_yes_no(gold)
    return {
        "predicted": pred,
        "gold": gold_norm,
        "accuracy": 1.0 if pred == gold_norm else 0.0,
    }


def flatten_gold(gold: Any) -> list[str]:
    """Flatten nested synonym groups to plain strings."""
    if not isinstance(gold, list):
        return [str(gold)] if gold is not None else []
    out: list[str] = []
    for item in gold:
        if isinstance(item, list):
            out.extend(str(s) for s in item if str(s).strip())
        else:
            out.append(str(item))
    return out


def score_factoid(pred_text: str, gold: Any) -> dict[str, Any]:
    synonyms = flatten_gold(gold)
    best = 0.0
    for syn in synonyms:
        best = max(best, token_f1(pred_text, syn)["f1"])
    pred_norm = re.sub(r"\s+", " ", pred_text.lower()).strip()
    strict = 1.0 if any(re.sub(r"\s+", " ", s.lower()).strip() == pred_norm for s in synonyms) else 0.0
    return {
        "predicted": pred_text[:500],
        "gold": synonyms,
        "token_f1": best,
        "strict_accuracy": strict,
    }


def score_list(pred_text: str, gold: Any) -> dict[str, Any]:
    groups = gold if isinstance(gold, list) else []
    if not groups:
        return {"predicted": pred_text[:500], "gold": [], "item_f1": 0.0}
    pred_tokens = tokens(pred_text)
    scores = []
    for item in groups:
        synonyms = item if isinstance(item, list) else [item]
        best = 0.0
        for syn in synonyms:
            item_tok = tokens(str(syn))
            if not item_tok:
                continue
            tp = len(pred_tokens & item_tok)
            p = tp / len(pred_tokens) if pred_tokens else 0.0
            r = tp / len(item_tok)
            f = 2 * p * r / (p + r) if (p + r) else 0.0
            best = max(best, f)
        scores.append(best)
    return {
        "predicted": pred_text[:500],
        "gold": groups,
        "item_f1": sum(scores) / len(scores) if scores else 0.0,
    }


def score_summary(pred_text: str, gold: str) -> dict[str, Any]:
    return {"predicted": pred_text[:1000], "gold": gold[:1000], **token_f1(pred_text, gold)}


def score_answer(pred_text: str, question: dict[str, Any]) -> dict[str, Any]:
    qtype = question.get("type", "summary")
    gold_answer = question.get("gold_answer")
    ideal_answer = question.get("ideal_answer", "")
    if qtype == "yesno":
        return {"type": "yesno", **score_yesno(pred_text, str(gold_answer) if gold_answer is not None else "")}
    if qtype == "factoid":
        return {"type": "factoid", **score_factoid(pred_text, gold_answer)}
    if qtype == "list":
        return {"type": "list", **score_list(pred_text, gold_answer)}
    return {"type": "summary", **score_summary(pred_text, ideal_answer)}


def score_question(question: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    qid = question.get("id", "")
    safe = safe_id(qid)
    state_path = work_dir / safe / "state.json"
    report_path = work_dir / safe / "report.md"

    result: dict[str, Any] = {
        "id": qid,
        "type": question.get("type"),
        "state_exists": state_path.exists(),
        "report_exists": report_path.exists(),
    }

    if not state_path.exists():
        result["error"] = "state file missing"
        result["retrieval"] = {k: 0.0 for k in ["p@5", "p@10", "p@20", "r@10", "r@20", "f1@10", "f1@20"]}
        result["answer"] = {"type": question.get("type"), "f1": 0.0}
        return result

    state = load_json(state_path)
    pred = pred_pmids_from_state(state)
    gold = [str(p) for p in question.get("gold_pmids", [])]
    result["retrieval"] = retrieval_metrics(pred, gold)

    if report_path.exists():
        report_text = report_path.read_text(encoding="utf-8")
        pred_answer = extract_report_answer(report_text)
    else:
        pred_answer = ""
    result["answer"] = score_answer(pred_answer, question)

    result["records_count"] = len(state.get("records", []))
    result["evidence_count"] = len(state.get("evidence", []))
    result["status"] = state.get("status", "unknown")
    return result


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    overall = {
        "mean_p@5": 0.0, "mean_p@10": 0.0, "mean_p@20": 0.0,
        "mean_r@10": 0.0, "mean_r@20": 0.0,
        "mean_f1@10": 0.0, "mean_f1@20": 0.0,
        "answer_score": 0.0,
        "count": len(results),
    }

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_type[r.get("type", "unknown")].append(r)

    if results:
        for key in ["p@5", "p@10", "p@20", "r@10", "r@20", "f1@10", "f1@20"]:
            overall[f"mean_{key}"] = sum(r["retrieval"][key] for r in results) / len(results)
        overall["answer_score"] = sum(_answer_scalar(r["answer"]) for r in results) / len(results)

    type_summary: dict[str, dict[str, Any]] = {}
    for qtype, items in by_type.items():
        type_summary[qtype] = {
            "count": len(items),
            "mean_retrieval": {key: sum(r["retrieval"][key] for r in items) / len(items) for key in items[0]["retrieval"]} if items else {},
            "mean_answer_score": sum(_answer_scalar(r["answer"]) for r in items) / len(items) if items else 0.0,
        }

    return {"overall": overall, "by_type": type_summary}


def _answer_scalar(answer: dict[str, Any]) -> float:
    if "accuracy" in answer:
        return float(answer["accuracy"])
    if "token_f1" in answer:
        return float(answer["token_f1"])
    if "item_f1" in answer:
        return float(answer["item_f1"])
    if "f1" in answer:
        return float(answer["f1"])
    return 0.0


def flatten_for_csv(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for r in results:
        row: dict[str, Any] = {
            "id": r["id"],
            "type": r["type"],
            "state_exists": r["state_exists"],
            "report_exists": r["report_exists"],
            "status": r.get("status", ""),
            "records_count": r.get("records_count", 0),
            "evidence_count": r.get("evidence_count", 0),
        }
        row.update({f"retrieval_{k}": v for k, v in r.get("retrieval", {}).items()})
        ans = r.get("answer", {})
        row["answer_score"] = _answer_scalar(ans)
        row["answer_type"] = ans.get("type", "")
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    work_dir = Path(args.work_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    benchmark = load_json(Path(args.benchmark))
    questions: list[dict[str, Any]] = benchmark.get("questions", [])

    results = [score_question(q, work_dir) for q in questions]
    summary = aggregate(results)

    full = {
        "benchmark": args.benchmark,
        "work_dir": str(work_dir),
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "questions": results,
    }

    scores_json = output_dir / "scores.json"
    scores_json.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")

    scores_csv = output_dir / "scores.csv"
    rows = flatten_for_csv(results)
    if rows:
        with scores_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        scores_csv.write_text("", encoding="utf-8")

    print(f"Scored {len(results)} questions -> {scores_json}, {scores_csv}")
    print(json.dumps(summary["overall"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
