#!/usr/bin/env python
"""Run medlit-cli over a BioASQ benchmark and persist per-question states."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure the repository root is on path so we can import medlit if needed.
ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "medlit-cli"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medlit.state.store import StateStore
from medlit.terminal.ui import Console


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run medlit-cli over a BioASQ-style benchmark."
    )
    parser.add_argument("--benchmark", default="evals/bioasq_benchmark.json", help="Path to benchmark JSON.")
    parser.add_argument("--work-dir", default="evals/runs", help="Directory for per-question state files.")
    parser.add_argument("--cache-dir", default="evals/cache", help="HTTP cache directory.")
    parser.add_argument("--max-questions", type=int, default=0, help="Limit number of questions to run (0 = all).")
    parser.add_argument("--resume", action="store_true", help="Skip questions already in a terminal state.")
    parser.add_argument("--clear-cache", action="store_true", help="Clear HTTP cache before running.")
    parser.add_argument("--query-dir", required=True, help="Directory containing Agent-authored query JSON files named <question-id>.json.")
    parser.add_argument("--retmax", type=int, default=100, help="Retrieval depth for the accepted Agent query.")
    parser.add_argument(
        "--default-max-date",
        default="",
        help="Fallback max publication date (YYYY/MM/DD) for search-pubmed when a question has no question_date.",
    )
    return parser.parse_args(argv)


def safe_id(raw_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(raw_id)).strip("-") or "q"


def load_benchmark(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli_command(args: list[str], env: dict[str, str]) -> tuple[int, str]:
    """Run a medlit CLI command and return (exit_code, combined_output).

    medlit.cli expects global options BEFORE the subcommand: --state <path> <cmd> ...
    """
    try:
        # args format is [subcommand, ...]; we need to inject --state <path> before the subcommand.
        state_idx = args.index("--state")
        state_value = args[state_idx + 1]
        subcommand_args = args[:state_idx] + args[state_idx + 2:]
        result = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "medlit_cli.py"), "--state", state_value] + subcommand_args,
            cwd=str(ROOT),
            env={**env, "PYTHONPATH": str(PLUGIN_ROOT)},
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode, (result.stderr or "") + (result.stdout or "")
    except subprocess.TimeoutExpired:
        return 124, "Command timed out after 300 seconds."
    except Exception as exc:
        return 1, f"Subprocess error: {exc}"


def run_pipeline(
    question: dict[str, Any],
    work_dir: Path,
    query_dir: Path,
    retmax: int,
    max_date: str,
    env: dict[str, str],
    console: Console,
) -> dict[str, Any]:
    qid = question["id"]
    safe_qid = safe_id(qid)
    state_path = work_dir / safe_qid / "state.json"
    report_path = work_dir / safe_qid / "report.md"

    steps: list[tuple[list[str], bool]] = []

    # 1. init
    steps.append((["init", "--question", question["question"], "--state", str(state_path)], True))

    # Agent-authored queries are generated outside this deterministic runner.
    query_path = query_dir / f"{safe_qid}.json"
    if not query_path.exists():
        query_path = query_dir / f"{qid}.json"
    if not query_path.exists():
        return {
            "id": qid,
            "safe_id": safe_qid,
            "state_path": str(state_path),
            "report_path": "",
            "status": "missing_query_file",
            "records_count": 0,
            "evidence_count": 0,
            "report_exists": False,
            "stop_reason": f"missing_query_file:{query_path}",
            "steps": [],
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    query_payload = json.loads(query_path.read_text(encoding="utf-8"))
    attempt_id = str(query_payload.get("attempt_id", "")).strip() or "q001"

    # Execute and explicitly accept the single Agent-authored query.
    cutoff = str(question.get("question_date", "")).strip() or max_date
    search_cmd = [
        "search-pubmed",
        "--query-file",
        str(query_path),
        "--retmax",
        str(retmax),
        "--state",
        str(state_path),
    ]
    if cutoff:
        search_cmd += ["--max-date", cutoff]
    steps.append((search_cmd, True))
    steps.append((["accept-query", "--attempt-id", attempt_id, "--state", str(state_path)], True))
    steps.append((["fetch-records", "--state", str(state_path)], False))
    retrieval_step_names = {"search-pubmed", "fetch-records"}

    # 5. fulltext and evidence extraction
    steps.extend([
        (["localize-fulltext", "--state", str(state_path)], False),
        (["parse-fulltext", "--state", str(state_path)], False),
        (["extract-evidence", "--state", str(state_path)], False),
        (["diagnose", "--state", str(state_path)], False),
    ])

    # 6. report and verify
    steps.extend([
        (["report", "--state", str(state_path)], False),
        (["verify", "--state", str(state_path)], False),
    ])

    results: list[dict[str, Any]] = []
    stop_reason: str | None = None

    for cmd, critical in steps:
        console.step(f"[{qid}] {' '.join(cmd[:2])}")
        code, output = run_cli_command(cmd, env)
        results.append({"command": cmd, "exit_code": code, "output": output[-2000:]})
        if code != 0:
            try:
                state = StateStore(state_path).load()
                blocked = bool(state.get("blockers"))
            except Exception:
                blocked = False
            # Retrieval steps are non-critical: empty results are expected
            # for narrow AND queries, so don't let them abort the pipeline.
            if cmd[0] in retrieval_step_names:
                blocked = False
            if critical or blocked:
                stop_reason = f"step_failed:{cmd[0]}"
                console.blocked(f"[{qid}] stopped at {cmd[0]} (exit {code})")
                break

    # Re-read final state for status summary.
    final_status = "unknown"
    records_count = 0
    evidence_count = 0
    try:
        final_state = StateStore(state_path).load()
        final_status = final_state.get("status", "unknown")
        records_count = len(final_state.get("records", []))
        evidence_count = len(final_state.get("evidence", []))
        report_exists = report_path.exists()
    except Exception as exc:
        final_status = f"load_error: {exc}"
        report_exists = False

    return {
        "id": qid,
        "safe_id": safe_qid,
        "state_path": str(state_path),
        "report_path": str(report_path) if report_path.exists() else "",
        "status": final_status,
        "records_count": records_count,
        "evidence_count": evidence_count,
        "report_exists": report_exists,
        "stop_reason": stop_reason,
        "steps": results,
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def should_skip(question: dict[str, Any], work_dir: Path) -> bool:
    safe_qid = safe_id(question["id"])
    state_path = work_dir / safe_qid / "state.json"
    if not state_path.exists():
        return False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return state.get("status") in {"done", "blocked", "ready_to_stop"}
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    console = Console(quiet=False)
    benchmark_path = Path(args.benchmark)
    work_dir = Path(args.work_dir)
    cache_dir = Path(args.cache_dir)
    query_dir = Path(args.query_dir)

    if args.clear_cache and cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
        console.ok(f"cleared cache: {cache_dir}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    benchmark = load_benchmark(benchmark_path)
    questions: list[dict[str, Any]] = benchmark.get("questions", [])
    if args.max_questions:
        questions = questions[: args.max_questions]

    import os
    env = {
        **dict(os.environ),
        "MEDLIT_CACHE_DIR": str(cache_dir),
    }

    runs: list[dict[str, Any]] = []
    runs_path = work_dir / "runs.json"
    if runs_path.exists():
        runs = json.loads(runs_path.read_text(encoding="utf-8")).get("runs", [])

    processed_ids = {r["id"] for r in runs}

    for idx, question in enumerate(questions, start=1):
        qid = question.get("id", f"q{idx}")
        console.step(f"[{idx}/{len(questions)}] {qid}")

        if args.resume and should_skip(question, work_dir):
            console.ok(f"[{qid}] already terminal; skipping")
            continue

        result = run_pipeline(question, work_dir, query_dir, args.retmax, args.default_max_date, env, console)
        # Use the actual question id, not the last search query id.
        result["id"] = qid
        result["safe_id"] = safe_id(qid)
        runs.append(result)
        processed_ids.add(qid)

        # Save incremental progress.
        runs_path.write_text(
            json.dumps({"runs": runs, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    console.ok(f"Finished {len([r for r in runs if r.get('id') in processed_ids])} questions; metadata in {runs_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
