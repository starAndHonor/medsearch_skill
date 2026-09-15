"""Command-line interface for the MedLit skill toolbox."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from medlit.evolution.diagnostics import Diagnoser
from medlit.evolution.strategy import StrategyEvolver
from medlit.extraction.evidence import EvidenceExtractor
from medlit.agents.tasks import TaskQueue
from medlit.fulltext.localizer import FulltextLocalizer
from medlit.fulltext.parser import FulltextParser
from medlit.http import ApiError, HttpClient, NetworkBlockedError
from medlit.pubmed.client import PubMedClient
from medlit.pubmed.query import validate_query_submission
from medlit.retrieval.audit import feedback_coverage, export_retrieval
from medlit.report import ReportWriter, Verifier
from medlit.state.store import DEFAULT_STATE, StateOps, StateStore, utc_now
from medlit.terminal.ui import Console


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console(quiet=getattr(args, "quiet", False))
    try:
        return args.func(args, console)
    except FileNotFoundError as exc:
        console.fail(str(exc))
        return 3
    except KeyboardInterrupt:
        console.fail("Interrupted.")
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="medlit-cli", description="Biomedical literature CLI toolbox for Codex-driven research.")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="Path to research state JSON.")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages on stderr.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="Create a new research state.")
    p.add_argument("--question", required=True)
    p.add_argument("--mode", choices=["research", "retrieval"], default="research")
    p.set_defaults(func=cmd_init)

    for name, help_text, func in [
        ("fetch-records", "Fetch PubMed records for current PMIDs.", cmd_fetch_records),
        ("localize-fulltext", "Try open-access full-text localization.", cmd_localize_fulltext),
        ("parse-fulltext", "Parse localized full text or abstract fallback.", cmd_parse_fulltext),
        ("extract-evidence", "Extract grounded evidence from parsed text.", cmd_extract_evidence),
        ("diagnose", "Print state diagnostics and termination advice.", cmd_diagnose),
        ("evolve", "Append strategy evolution suggestions.", cmd_evolve),
        ("report", "Write report.md from current state.", cmd_report),
        ("verify", "Verify state/report references.", cmd_verify),
        ("status", "Print concise status.", cmd_status),
        ("spawn-tasks", "Create file-based tasks for optional subagents.", cmd_spawn_tasks),
    ]:
        sp = sub.add_parser(name, help=help_text)
        sp.set_defaults(func=func)

    sp = sub.add_parser("search-pubmed", help="Execute one Agent-authored PubMed query.")
    sp.add_argument("--query-file", required=True, help="JSON file containing exact_query and optional audit metadata.")
    sp.add_argument("--retmax", type=int, default=100, help="Number of ranked PMIDs to return.")
    sp.add_argument("--max-date", default="", help="Optional publication cutoff (YYYY/MM/DD).")
    sp.add_argument("--feedback-records", type=int, default=10, help="Top records returned for Agent review.")
    sp.set_defaults(func=cmd_search_pubmed)

    sp = sub.add_parser("accept-query", help="Select one query attempt for downstream processing.")
    sp.add_argument("--attempt-id", required=True, help="Attempt id returned by search-pubmed.")
    sp.set_defaults(func=cmd_accept_query)

    sp = sub.add_parser("recover-feedback", help="Refetch only missing feedback records without changing ranking.")
    sp.add_argument("--attempt-id", required=True)
    sp.set_defaults(func=cmd_recover_feedback)

    sp = sub.add_parser("export-retrieval", help="Export accepted ranking and seal a fresh audit directory.")
    sp.add_argument("--output-dir", required=True)
    sp.set_defaults(func=cmd_export_retrieval)

    sp = sub.add_parser("merge-task-output", help="Merge a subagent task output JSON into state.")
    sp.add_argument("--file", required=True)
    sp.set_defaults(func=cmd_merge_task_output)

    return parser


def cmd_init(args: argparse.Namespace, console: Console) -> int:
    console.step("initializing state")
    state = StateStore(args.state).init(args.question)
    state["task_mode"] = getattr(args, "mode", "research")
    StateStore(args.state).save(state)
    console.ok(f"state created: {args.state}")
    console.json({"state": args.state, "question": state["question"], "next": "search-pubmed --query-file <query.json>"})
    return 0


def cmd_search_pubmed(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    try:
        raw_submission = json.loads(Path(args.query_file).read_text(encoding="utf-8"))
        submission = validate_query_submission(raw_submission)
    except (json.JSONDecodeError, ValueError) as exc:
        console.fail(f"invalid query file: {exc}")
        return 4

    attempts = state.setdefault("query_attempts", [])
    attempt_id = submission["attempt_id"] or f"q{len(attempts) + 1:03d}"
    if any(item.get("attempt_id") == attempt_id for item in attempts):
        console.fail(f"query attempt already exists: {attempt_id}")
        return 4
    if args.retmax < 1 or args.feedback_records < 0:
        console.fail("retmax must be positive and feedback-records cannot be negative")
        return 4

    query = submission["exact_query"]
    started = time.monotonic()
    pending = {"attempt_id": attempt_id, "exact_query": query,
               "reasoning": submission["reasoning"], "added_terms": submission["added_terms"],
               "status": "running", "started_at": utc_now(), "pmids": [],
               "retmax": args.retmax, "max_date": args.max_date, "sort": "relevance"}
    attempts.append(pending)
    state.setdefault("counters", {})["pubmed_queries"] = int(state.get("counters", {}).get("pubmed_queries", 0)) + 1
    store.save(state)
    console.step(f"searching PubMed with {attempt_id}")
    try:
        client = PubMedClient(HttpClient(), retmax=args.retmax)
        result = client.search(query, retmax=args.retmax, maxdate=args.max_date)
    except NetworkBlockedError as exc:
        pending.update(status="network_failed", finished_at=utc_now(), elapsed_seconds=round(time.monotonic()-started, 3))
        StateOps.add_blocker(state, "network_unavailable", str(exc), stage="search-pubmed", advice="Check network/proxy or run with cached records.")
        store.save(state)
        console.blocked("network unavailable during PubMed search")
        return 7
    except ApiError as exc:
        pending.update(status="api_failed", finished_at=utc_now(), elapsed_seconds=round(time.monotonic()-started, 3))
        StateOps.add_error(state, "search-pubmed", str(exc), recoverable=True)
        store.save(state)
        console.fail("PubMed API error")
        return 6

    feedback_records: list[dict[str, Any]] = []
    feedback_error = ""
    feedback_pmids = result["pmids"][:args.feedback_records]
    if feedback_pmids:
        try:
            feedback_records = client.fetch_records(feedback_pmids)
        except (NetworkBlockedError, ApiError) as exc:
            feedback_error = str(exc)

    attempt = {
        "attempt_id": attempt_id,
        "exact_query": query,
        "reasoning": submission["reasoning"],
        "added_terms": submission["added_terms"],
        "lint_warnings": submission["lint"]["warnings"],
        "effective_query": result.get("effective_query", query),
        "query_translation": result.get("query_translation", ""),
        "translationset": result.get("translationset", []),
        "warninglist": result.get("warninglist", {}),
        "errorlist": result.get("errorlist", {}),
        "count": result["count"],
        "retmax": result.get("retmax", args.retmax),
        "sort": result.get("sort", "relevance"),
        "max_date": args.max_date,
        "pmids": result["pmids"],
        "feedback_records": feedback_records,
        "feedback_error": feedback_error,
        "executed_at": utc_now(),
        "started_at": pending["started_at"],
        "finished_at": utc_now(),
        "elapsed_seconds": round(time.monotonic()-started, 3),
        "status": "success",
        "feedback_coverage": feedback_coverage(feedback_pmids, feedback_records),
        "raw_esearch": result.get("raw_esearch", {}),
        "raw_feedback_xml": getattr(client, "last_fetch_xml", "") if isinstance(getattr(client, "last_fetch_xml", ""), str) else "",
    }
    if attempt["feedback_coverage"]["missing_pmids"] and not feedback_error:
        attempt["feedback_error"] = "Some requested feedback records were not returned; use recover-feedback."
    pending.clear()
    pending.update(attempt)
    state["last_pmids"] = result["pmids"]
    state["diagnostics"] = {}
    store.save(state)
    console.ok(f"{result['count']} total hits; {len(result['pmids'])} PMIDs returned")
    console.json(attempt)
    return 0


def cmd_recover_feedback(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    attempt = next((a for a in state.get("query_attempts", []) if a["attempt_id"] == args.attempt_id), None)
    if not attempt or attempt.get("status", "success") != "success":
        console.fail("No successful attempt to recover")
        return 4
    coverage = attempt.get("feedback_coverage")
    if coverage is None:
        console.fail("This legacy attempt does not record the requested feedback IDs")
        return 4
    missing = coverage["missing_pmids"]
    if not missing:
        console.json(coverage)
        return 0
    recovery = {"requested_pmids": missing[:], "started_at": utc_now(), "status": "running"}
    attempt.setdefault("feedback_recoveries", []).append(recovery)
    store.save(state)
    try:
        fetched = PubMedClient(HttpClient()).fetch_records(missing)
    except (ApiError, NetworkBlockedError):
        recovery.update(status="failed", finished_at=utc_now())
        store.save(state)
        console.fail("Feedback recovery failed; original search ranking preserved")
        return 6
    by_id = {r["pmid"]: r for r in attempt["feedback_records"] + fetched}
    attempt["feedback_records"] = [by_id[p] for p in coverage["requested_pmids"] if p in by_id]
    attempt["feedback_coverage"] = feedback_coverage(coverage["requested_pmids"], attempt["feedback_records"])
    attempt["feedback_error"] = "" if attempt["feedback_coverage"]["complete"] else "Feedback records still missing"
    recovery.update(status="success", finished_at=utc_now(), returned_pmids=[r["pmid"] for r in fetched])
    store.save(state)
    console.json(attempt["feedback_coverage"])
    return 0


def cmd_export_retrieval(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    try:
        result = export_retrieval(state, Path(args.output_dir).resolve())
    except ValueError as exc:
        console.fail(str(exc))
        return 4
    state["retrieval_export"] = result
    if state.get("task_mode") == "retrieval":
        state["status"] = "complete"
    store.save(state)
    console.json(result)
    return 0


def cmd_accept_query(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    attempt = next(
        (
            item
            for item in state.get("query_attempts", [])
            if item.get("attempt_id") == args.attempt_id
        ),
        None,
    )
    if attempt is None:
        console.fail(f"query attempt not found: {args.attempt_id}")
        return 4
    if not attempt.get("pmids"):
        console.blocked("cannot accept a query attempt with no PMIDs")
        return 5

    pmids = list(dict.fromkeys(str(pmid) for pmid in attempt["pmids"] if str(pmid)))
    if (
        state.get("accepted_query_attempt_id") == args.attempt_id
        and state.get("final_ranked_pmids") == pmids
    ):
        console.ok(f"query already accepted: {args.attempt_id}")
        console.json({"attempt_id": args.attempt_id, "pmids": len(pmids)})
        return 0

    StateOps.clear_downstream(state)
    state["accepted_query_attempt_id"] = args.attempt_id
    state["final_ranked_pmids"] = pmids
    state["last_pmids"] = pmids
    store.save(state)
    console.ok(f"accepted {args.attempt_id} with {len(pmids)} ranked PMIDs")
    console.json({
        "attempt_id": args.attempt_id,
        "exact_query": attempt.get("exact_query", ""),
        "pmids": len(pmids),
        "next": "fetch-records",
    })
    return 0


def cmd_fetch_records(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    pmids = list(dict.fromkeys(state.get("final_ranked_pmids", [])))
    if not pmids:
        console.blocked("no PMIDs available to fetch")
        StateOps.add_blocker(
            state,
            "missing_pmids",
            "No accepted PubMed query is available.",
            stage="fetch-records",
            advice="Inspect query attempts and run accept-query first.",
        )
        store.save(state)
        return 5
    console.step(f"fetching {len(pmids)} PubMed records")
    try:
        records = PubMedClient(HttpClient()).fetch_records(pmids)
    except NetworkBlockedError as exc:
        StateOps.add_blocker(state, "network_unavailable", str(exc), stage="fetch-records", advice="Check network/proxy or use cached records.")
        store.save(state)
        console.blocked("network unavailable during record fetch")
        return 7
    except ApiError as exc:
        StateOps.add_error(state, "fetch-records", str(exc), recoverable=True)
        store.save(state)
        console.fail("PubMed fetch API error")
        return 6
    state["records"] = records
    store.save(state)
    console.ok(f"{len(records)} records fetched")
    console.json(records)
    return 0


def cmd_localize_fulltext(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    records = state.get("records", [])
    if not records:
        console.blocked("no records available for full-text localization")
        StateOps.add_blocker(state, "missing_records", "No PubMed records in state.", stage="localize-fulltext", advice="Run fetch-records first.")
        store.save(state)
        return 5
    console.step(f"localizing open full text for {len(records)} records")
    localizer = FulltextLocalizer(HttpClient(retries=1), output_dir=Path(args.state).parent)
    manifests = localizer.localize_records(records, limit=state.get("budgets", {}).get("max_records", 50))
    state["fulltexts"] = StateOps.replace_by_key(state.get("fulltexts", []), manifests, "pmid")
    state.setdefault("counters", {})["fulltext_attempts"] = int(state.get("counters", {}).get("fulltext_attempts", 0)) + len(records)
    store.save(state)
    downloaded = sum(1 for item in manifests if str(item.get("fulltext_status", "")).endswith("downloaded"))
    console.ok(f"{downloaded}/{len(manifests)} full texts downloaded; fallbacks recorded")
    console.json(manifests)
    return 0


def cmd_parse_fulltext(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    console.step("parsing localized sources")
    parsed = FulltextParser().parse_manifests(state.get("fulltexts", []), state.get("records", []))
    state["parsed_sources"] = StateOps.replace_by_key(state.get("parsed_sources", []), parsed, "pmid")
    store.save(state)
    console.ok(f"{sum(1 for p in parsed if p.get('status') == 'parsed')}/{len(parsed)} sources parsed")
    console.json(parsed)
    return 0


def cmd_extract_evidence(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    console.step("extracting grounded evidence")
    evidence = EvidenceExtractor().extract(state.get("parsed_sources", []), state.get("records", []))
    state["evidence"] = StateOps.replace_by_key(state.get("evidence", []), evidence, "paper_ref")
    store.save(state)
    console.ok(f"{sum(1 for e in evidence if e.get('extraction_status') == 'ok')}/{len(evidence)} evidence items extracted")
    console.json(evidence)
    return 0


def cmd_diagnose(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    diagnostics = Diagnoser().diagnose(state)
    state["diagnostics"] = diagnostics
    if diagnostics.get("blocked"):
        state["status"] = "blocked"
    elif diagnostics.get("termination_ready"):
        state["status"] = "ready_to_stop" if not state.get("report_path") else "done"
    else:
        state["status"] = "running"
    store.save(state)
    if diagnostics.get("blocked"):
        console.blocked(diagnostics.get("reason") or diagnostics["status"])
    elif diagnostics.get("termination_ready"):
        console.ok(f"termination ready: {diagnostics['status']}")
    else:
        console.step(f"continue: {diagnostics['status']}")
    console.json(diagnostics)
    return 8 if diagnostics.get("blocked") else 0


def cmd_evolve(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    diagnostics = state.get("diagnostics") or Diagnoser().diagnose(state)
    console.step("evolving strategy suggestions")
    strategy = StrategyEvolver().evolve(state, diagnostics)
    store.save(state)
    console.ok("strategy suggestion appended")
    console.json(strategy)
    return 0


def cmd_report(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    console.step("writing Markdown report")
    path = ReportWriter(Path(args.state).parent).write(state)
    state["report_path"] = path
    store.save(state)
    console.ok(f"report written: {path}")
    console.json({"report_path": path})
    return 0


def cmd_verify(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    console.step("verifying state references")
    result = Verifier().verify(state)
    state["verification"] = result
    store.save(state)
    if result["ok"]:
        console.ok("verification passed")
    else:
        console.warn("verification found issues")
    console.json(result)
    return 0 if result["ok"] else 9


def cmd_status(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    if not store.exists():
        console.json({
            "status": "no_state",
            "next": ["init"],
            "message": "No research state exists yet. Start with a question or run init.",
            "state": args.state,
        })
        return 0
    state = store.load()
    # Status is a live view. Persisted diagnostics are an audit snapshot and
    # must not override transitions completed after the last diagnose command.
    diag = Diagnoser().diagnose(state)
    workflow = diag.get("workflow", {})
    console.json({
        "status": state.get("status"),
        "diagnostic_status": diag.get("status"),
        "next": diag.get("recommended_next_actions", []),
        "records": len(state.get("records", [])),
        "evidence": len(state.get("evidence", [])),
        "blockers": len(state.get("blockers", [])),
        "report_path": state.get("report_path", ""),
        "query_attempts": workflow.get("query_attempts", 0),
        "accepted_query_attempt_id": workflow.get(
            "accepted_query_attempt_id", ""
        ),
    })
    return 0


def cmd_spawn_tasks(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    console.step("spawning file-based subagent tasks")
    tasks = TaskQueue(Path(args.state).parent).spawn_tasks(state)
    store.save(state)
    console.ok(f"{len(tasks)} task files created")
    console.json(tasks)
    return 0


def cmd_merge_task_output(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    console.step("merging subagent task output")
    result = TaskQueue(Path(args.state).parent).merge_output(state, args.file)
    store.save(state)
    console.ok("task output merged")
    console.json(result)
    return 0
