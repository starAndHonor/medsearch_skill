#!/usr/bin/env python
"""Score medlit-cli runs with the OFFICIAL BioASQ evaluation jar.

Builds BioASQ-format submission files from medlit-cli run states and invokes
the official evaluator (BioASQ/Evaluation-Measures, evaluation.EvaluatorTask1b)
so that reported numbers are exactly the official metrics:

- Phase A: document MAP/P/R/F1 (system limited to 10 documents per question).
- Phase B: YesNo accuracy + macro F1 (+ F1_yes/F1_no), factoid strict/lenient
  accuracy + MRR, list synonym-aware precision/recall/F1.

Usage:
  python3 evals/official_score.py \
      --benchmark evals/bioasq_13b_test_benchmark.json \
      --work-dir evals/runs_13b \
      --golden data/bioasq_13b_test_merged.json \
      --phase both --output-dir evals/results
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOOLS_DIR = Path(__file__).resolve().parent / "tools"
CLASSPATH = ":".join(
    str(TOOLS_DIR / name)
    for name in [
        "BioASQEvaluation.jar",
        "commons-cli-1.2.jar",
        "gson-2.2.4.jar",
        "SnowBallStemmer.jar",
    ]
)

PHASE_B_METRICS = [
    "yesno_accuracy",
    "factoid_strict_accuracy",
    "factoid_lenient_accuracy",
    "factoid_mrr",
    "list_precision",
    "list_recall",
    "list_f1",
    "yesno_macro_f1",
    "yesno_f1_yes",
    "yesno_f1_no",
]

PHASE_A_GROUPS = ["concepts", "documents", "snippets", "triples"]
PHASE_A_MEASURES = ["mean_precision", "mean_recall", "mean_f1", "map", "gmap"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score medlit-cli runs with the official BioASQ evaluator."
    )
    parser.add_argument("--benchmark", required=True, help="Benchmark JSON (id/type/question).")
    parser.add_argument("--work-dir", required=True, help="Per-question run directory.")
    parser.add_argument("--golden", required=True, help="Official golden JSON file.")
    parser.add_argument("--phase", choices=["A", "B", "both"], default="both")
    parser.add_argument("--version", type=int, default=9, help="Challenge version for the evaluator (-e).")
    parser.add_argument("--max-docs", type=int, default=10, help="Max documents per question (official limit).")
    parser.add_argument("--output-dir", default="evals/results", help="Where to write official_scores.json.")
    return parser.parse_args(argv)


def safe_id(raw_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(raw_id)).strip("-") or "q"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pred_pmids_from_state(state: dict[str, Any]) -> list[str]:
    """Use the plugin's final fused ranking, with v0.1 state fallback."""
    fused = [str(pmid).strip() for pmid in state.get("final_ranked_pmids", [])]
    fused = [pmid for pmid in fused if pmid and pmid.isdigit()]
    if fused:
        return list(dict.fromkeys(fused))
    out: list[str] = []
    seen: set[str] = set()
    for run in state.get("retrieval_runs", []) or []:
        for pmid in run.get("pmids", []) or []:
            p = str(pmid).strip()
            if p and p.isdigit() and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def extract_report_answer(report_md: str) -> str:
    """Extract the answer/conclusion portion of report.md."""
    if not report_md:
        return ""
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
    return ""


def split_candidates(pred_text: str, max_items: int) -> list[str]:
    """Split an answer block into candidate items (one per line)."""
    items: list[str] = []
    seen: set[str] = set()
    for raw in pred_text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", raw).strip().strip('"').strip()
        if not line:
            continue
        key = re.sub(r"\s+", " ", line.lower())
        if key in seen:
            continue
        seen.add(key)
        items.append(line[:100])  # official limit: 100 chars per entry
        if len(items) >= max_items:
            break
    return items


def truncate_words(text: str, max_words: int = 200) -> str:
    """Official limit: ideal answers are at most 200 words."""
    words = text.split()
    return " ".join(words[:max_words])


def build_submissions(
    questions: list[dict[str, Any]], work_dir: Path, max_docs: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build Phase A and Phase B submission JSON objects."""
    phase_a: list[dict[str, Any]] = []
    phase_b: list[dict[str, Any]] = []
    for q in questions:
        qid = q["id"]
        qtype = q.get("type", "summary")
        qdir = work_dir / safe_id(qid)
        state_path = qdir / "state.json"
        report_path = qdir / "report.md"

        pmids: list[str] = []
        if state_path.exists():
            try:
                state = load_json(state_path)
                pmids = pred_pmids_from_state(state)
            except Exception:
                pmids = []
        phase_a.append(
            {
                "id": qid,
                "type": qtype,
                "body": q.get("question", ""),
                "documents": [f"http://www.ncbi.nlm.nih.gov/pubmed/{p}" for p in pmids[:max_docs]],
                "snippets": [],
            }
        )

        answer_block = ""
        if report_path.exists():
            answer_block = extract_report_answer(report_path.read_text(encoding="utf-8"))

        entry: dict[str, Any] = {
            "id": qid,
            "type": qtype,
            "body": q.get("question", ""),
            "ideal_answer": truncate_words(answer_block) if answer_block else "",
        }
        if qtype == "yesno":
            entry["exact_answer"] = normalize_yes_no(answer_block[:50])
        elif qtype == "factoid":
            cands = split_candidates(answer_block, 5)
            entry["exact_answer"] = [[c] for c in cands] if cands else []
        elif qtype == "list":
            items = split_candidates(answer_block, 100)
            entry["exact_answer"] = [[c] for c in items] if items else []
        phase_b.append(entry)
    return {"questions": phase_a}, {"questions": phase_b}


def run_evaluator(golden: Path, system: Path, phase: str, version: int) -> tuple[dict[str, float], str]:
    cmd = [
        "java",
        "-cp",
        CLASSPATH,
        "evaluation.EvaluatorTask1b",
        f"-phase{phase}",
        "-e",
        str(version),
        str(golden),
        str(system),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"Official evaluator failed (exit {proc.returncode}): {proc.stderr.strip()}")
    values = [float(x) for x in proc.stdout.split()]
    if phase == "A":
        if len(values) != len(PHASE_A_GROUPS) * len(PHASE_A_MEASURES):
            raise RuntimeError(f"Unexpected Phase A output: {proc.stdout!r}")
        out: dict[str, float] = {}
        idx = 0
        for group in PHASE_A_GROUPS:
            for measure in PHASE_A_MEASURES:
                out[f"{group}_{measure}"] = values[idx]
                idx += 1
        return out, proc.stdout
    if len(values) != len(PHASE_B_METRICS):
        raise RuntimeError(f"Unexpected Phase B output: {proc.stdout!r}")
    return dict(zip(PHASE_B_METRICS, values)), proc.stdout


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    work_dir = Path(args.work_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    benchmark = load_json(Path(args.benchmark))
    questions: list[dict[str, Any]] = benchmark.get("questions", [])

    sub_a, sub_b = build_submissions(questions, work_dir, args.max_docs)
    sub_a_path = output_dir / "official_submission_phaseA.json"
    sub_b_path = output_dir / "official_submission_phaseB.json"
    sub_a_path.write_text(json.dumps(sub_a, ensure_ascii=False, indent=1), encoding="utf-8")
    sub_b_path.write_text(json.dumps(sub_b, ensure_ascii=False, indent=1), encoding="utf-8")

    golden = Path(args.golden)
    result: dict[str, Any] = {
        "evaluator": "BioASQ/Evaluation-Measures (official jar)",
        "challenge_version": args.version,
        "golden": str(golden),
        "benchmark": args.benchmark,
        "work_dir": str(work_dir),
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if args.phase in {"A", "both"}:
        result["phase_a"], raw_a = run_evaluator(golden, sub_a_path, "A", args.version)
        (output_dir / "official_output_phaseA.txt").write_text(raw_a, encoding="utf-8")
    if args.phase in {"B", "both"}:
        result["phase_b"], raw_b = run_evaluator(golden, sub_b_path, "B", args.version)
        (output_dir / "official_output_phaseB.txt").write_text(raw_b, encoding="utf-8")
        pb = result["phase_b"]
        result["combined_exact"] = (
            pb["yesno_macro_f1"] + pb["factoid_mrr"] + pb["list_f1"]
        ) / 3.0

    out_path = output_dir / "official_scores.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Official scores -> {out_path}")
    if "phase_b" in result:
        print(json.dumps(result["phase_b"], indent=2))
        print(f"combined_exact = {result['combined_exact']:.4f}")
    if "phase_a" in result:
        print(json.dumps({k: v for k, v in result["phase_a"].items() if k.startswith("documents_")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
