#!/usr/bin/env python
"""Score medlit-cli ideal answers with the official Perl ROUGE-1.5.5.

Replicates the official BioASQ ideal-answer evaluation: ROUGE-2 and
ROUGE-SU4 (skip-bigram, max gap 4, with unigrams) computed by the Perl
ROUGE-1.5.5 scorer with the standard DUC configuration
(-a -n 2 -x -m -2 4 -u -c 95 -r 1000 -f A -p 0.5 -t 0).

Inputs are written in sentence-per-line (SPL) format, one EVAL per question:
system = answer section extracted from report.md (<=200 words, official cap);
models  = golden ideal_answer reference(s) from the official golden JSON.

Usage:
  python3 evals/rouge_score.py \
      --benchmark evals/bioasq_13b_test_benchmark.json \
      --work-dir evals/runs_13b \
      --golden data/bioasq_13b_test_merged.json \
      --output-dir evals/results
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ROUGE_HOME = Path(__file__).resolve().parent / "tools" / "ROUGE-1.5.5" / "RELEASE-1.5.5"
ROUGE_PL = ROUGE_HOME / "ROUGE-1.5.5.pl"
ROUGE_ARGS = ["-a", "-n", "2", "-x", "-m", "-2", "4", "-u", "-c", "95", "-r", "1000", "-f", "A", "-p", "0.5", "-t", "0"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official ROUGE-2/SU4 scoring for ideal answers.")
    parser.add_argument("--benchmark", required=True, help="Benchmark JSON (id/type/question).")
    parser.add_argument("--work-dir", required=True, help="Per-question run directory with report.md.")
    parser.add_argument("--golden", required=True, help="Official golden JSON (ideal_answer references).")
    parser.add_argument("--output-dir", default="evals/results", help="Where to write rouge_scores.json.")
    return parser.parse_args(argv)


def safe_id(raw_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(raw_id)).strip("-") or "q"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_report_answer(report_md: str) -> str:
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


def truncate_words(text: str, max_words: int = 200) -> str:
    words = text.split()
    return " ".join(words[:max_words])


def to_spl(text: str) -> str:
    """Convert text to sentence-per-line format for ROUGE."""
    # Markdown cleanup: headings, list markers, emphasis.
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", text, flags=re.M)
    text = re.sub(r"[*_`]+", "", text)
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    lines = [s.strip() for s in sentences if s.strip()]
    return "\n".join(lines) + ("\n" if lines else "")


def ideal_references(golden_q: dict[str, Any]) -> list[str]:
    ideal = golden_q.get("ideal_answer")
    if isinstance(ideal, list):
        return [str(x) for x in ideal if str(x).strip()]
    if ideal:
        return [str(ideal)]
    return []


def build_rouge_inputs(
    questions: list[dict[str, Any]],
    golden_by_id: dict[str, dict[str, Any]],
    work_dir: Path,
    rouge_dir: Path,
) -> tuple[Path, int]:
    """Write SPL files and config.xml; returns (config_path, n_evals)."""
    systems_dir = rouge_dir / "systems"
    models_dir = rouge_dir / "models"
    systems_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    evals: list[str] = []
    n = 0
    for q in questions:
        qid = q["id"]
        sid = safe_id(qid)
        report_path = work_dir / sid / "report.md"
        if not report_path.exists():
            continue
        answer = extract_report_answer(report_path.read_text(encoding="utf-8"))
        answer = truncate_words(answer)
        if not answer.strip():
            continue
        refs = ideal_references(golden_by_id.get(qid, {}))
        if not refs:
            continue

        (systems_dir / f"{sid}.txt").write_text(to_spl(answer), encoding="utf-8")
        models_xml = []
        for i, ref in enumerate(refs, 1):
            (models_dir / f"{sid}.{i}.txt").write_text(to_spl(ref), encoding="utf-8")
            models_xml.append(f'<M ID="{i}">{sid}.{i}.txt</M>')
        evals.append(
            f"""<EVAL ID="{n + 1}">
<MODEL-ROOT>{models_dir}</MODEL-ROOT>
<PEER-ROOT>{systems_dir}</PEER-ROOT>
<INPUT-FORMAT TYPE="SPL"></INPUT-FORMAT>
<PEERS><P ID="1">{sid}.txt</P></PEERS>
<MODELS>{"".join(models_xml)}</MODELS>
</EVAL>"""
        )
        n += 1

    config = rouge_dir / "config.xml"
    config.write_text(
        '<ROUGE_EVAL version="1.5.5">\n' + "\n".join(evals) + "\n</ROUGE_EVAL>\n",
        encoding="utf-8",
    )
    return config, n


def parse_rouge_output(text: str) -> dict[str, Any]:
    """Parse ROUGE-1.5.5 -f A output: ROUGE-2 and ROUGE-SU4 Average R/P/F."""
    out: dict[str, Any] = {}
    for m in re.finditer(
        r"ROUGE-(2|SU4)\s+Average_([RPF]):\s*([0-9.]+)\s*\(95%-conf\.int\.\s*([0-9.]+)\s*-\s*([0-9.]+)\)",
        text,
    ):
        metric = "rouge2" if m.group(1) == "2" else "rouge_su4"
        key = {"R": "recall", "P": "precision", "F": "f1"}[m.group(2)]
        out.setdefault(metric, {})[key] = float(m.group(3))
        out[metric][f"{key}_ci95"] = [float(m.group(4)), float(m.group(5))]
    return out


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    work_dir = Path(args.work_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    benchmark = load_json(Path(args.benchmark))
    questions: list[dict[str, Any]] = benchmark.get("questions", [])
    golden = load_json(Path(args.golden))
    golden_by_id = {q["id"]: q for q in golden.get("questions", [])}

    rouge_dir = output_dir / "rouge_work"
    if rouge_dir.exists():
        import shutil

        shutil.rmtree(rouge_dir)
    rouge_dir.mkdir(parents=True, exist_ok=True)

    config_path, n_evals = build_rouge_inputs(questions, golden_by_id, work_dir, rouge_dir)
    if n_evals == 0:
        print("No scored questions (no report.md with answer content).")
        return 1

    cmd = ["perl", str(ROUGE_PL), "-e", str(ROUGE_HOME / "data"), *ROUGE_ARGS, str(config_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(f"ROUGE failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}")

    scores = parse_rouge_output(proc.stdout)
    if not scores:
        raise RuntimeError(f"Could not parse ROUGE output:\n{proc.stdout[:1000]}")
    (output_dir / "rouge_output.txt").write_text(proc.stdout, encoding="utf-8")

    result: dict[str, Any] = {
        "evaluator": "Perl ROUGE-1.5.5 (official BioASQ ideal-answer scorer)",
        "rouge_args": ROUGE_ARGS,
        "golden": args.golden,
        "benchmark": args.benchmark,
        "work_dir": str(work_dir),
        "n_scored": n_evals,
        "n_total": len(questions),
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scores": scores,
    }
    out_path = output_dir / "rouge_scores.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"ROUGE scores ({n_evals}/{len(questions)} questions) -> {out_path}")
    print(json.dumps(scores, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
