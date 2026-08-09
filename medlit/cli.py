"""Command-line interface for the MedLit skill toolbox."""

from __future__ import annotations

import argparse
import json
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
from medlit.pubmed.mesh import MeshValidator
from medlit.pubmed.query import QueryBuilder, TermPlanner
from medlit.report import ReportWriter, Verifier
from medlit.state.store import DEFAULT_STATE, StateOps, StateStore
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
    p.set_defaults(func=cmd_init)

    for name, help_text, func in [
        ("decompose", "Set PICO from a Codex/user-provided JSON file; no local heuristic.", cmd_decompose),
        ("plan-terms", "Create initial term plan from PICO.", cmd_plan_terms),
        ("validate-mesh", "Validate MeSH candidates against NCBI MeSH.", cmd_validate_mesh),
        ("build-query", "Build PubMed query ladder.", cmd_build_query),
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

    # Add an optional argument to the decompose subparser after creation.
    for action in sub.choices.values():
        if action.prog.endswith(" decompose"):
            action.add_argument("--pico-file", default="", help="JSON file containing Codex/user-generated PICO.")

    sp = sub.add_parser("search-pubmed", help="Execute one query from the query ladder.")
    sp.add_argument("--query-id", default="", help="Query id to execute; default first unexecuted query.")
    sp.add_argument("--retmax", type=int, default=20)
    sp.add_argument("--max-date", default="", help="Only include papers published on or before this date (YYYY/MM/DD).")
    sp.set_defaults(func=cmd_search_pubmed)

    sp = sub.add_parser("merge-task-output", help="Merge a subagent task output JSON into state.")
    sp.add_argument("--file", required=True)
    sp.set_defaults(func=cmd_merge_task_output)

    return parser


def cmd_init(args: argparse.Namespace, console: Console) -> int:
    console.step("initializing state")
    state = StateStore(args.state).init(args.question)
    console.ok(f"state created: {args.state}")
    console.json({"state": args.state, "question": state["question"], "next": "decompose"})
    return 0


def cmd_decompose(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    if not getattr(args, "pico_file", ""):
        console.blocked("PICO decomposition requires Codex or an explicit --pico-file")
        StateOps.add_blocker(
            state,
            "codex_required",
            "No local heuristic PICO decomposition is available.",
            stage="decompose",
            advice="Use project main.py with external-codex login, or provide --pico-file from a trusted agent.",
        )
        store.save(state)
        console.json({"blocked": True, "reason": "codex_required", "next": "Use external Codex or --pico-file."})
        return 8
    console.step("setting PICO from external JSON")
    pico = json.loads(Path(args.pico_file).read_text(encoding="utf-8"))
    state["pico"] = pico
    store.save(state)
    console.ok("PICO updated")
    console.json(pico)
    return 0


def cmd_plan_terms(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    console.step("planning MeSH and Title/Abstract terms")
    state["term_plan"] = TermPlanner().plan(state.get("pico", {}))
    store.save(state)
    console.ok(f"{len(state['term_plan']['concepts'])} concepts planned")
    console.json(state["term_plan"])
    return 0


def cmd_validate_mesh(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    console.step("validating MeSH candidates")
    validator = MeshValidator(HttpClient())
    validations = validator.validate_term_plan(state.get("term_plan", {}))
    state["mesh_validation"] = validations
    store.save(state)
    console.ok(f"{len(validations)} MeSH candidates checked")
    console.json(validations)
    return 0


def cmd_build_query(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    console.step("building PubMed query ladder")
    state["query_ladder"] = QueryBuilder().build(state.get("term_plan", {}), state.get("mesh_validation", []))
    store.save(state)
    console.ok(f"{len(state['query_ladder'])} query versions available")
    console.json(state["query_ladder"])
    return 0


def cmd_search_pubmed(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    query = _select_query(state, args.query_id)
    if not query:
        console.blocked("no query available")
        StateOps.add_blocker(state, "missing_query", "No query in query_ladder.", stage="search-pubmed", advice="Run build-query first.")
        store.save(state)
        return 5
    console.step(f"searching PubMed with {query['query_id']}")
    try:
        result = PubMedClient(HttpClient(), retmax=args.retmax).search(query["exact_query"], retmax=args.retmax, maxdate=args.max_date)
    except NetworkBlockedError as exc:
        StateOps.add_blocker(state, "network_unavailable", str(exc), stage="search-pubmed", advice="Check network/proxy or run with cached records.")
        store.save(state)
        console.blocked("network unavailable during PubMed search")
        return 7
    except ApiError as exc:
        StateOps.add_error(state, "search-pubmed", str(exc), recoverable=True)
        store.save(state)
        console.fail("PubMed API error")
        return 6
    query["executed"] = True
    state.setdefault("retrieval_runs", []).append({"query_id": query["query_id"], "query": query["exact_query"], "count": result["count"], "pmids": result["pmids"]})
    state.setdefault("counters", {})["pubmed_queries"] = int(state.get("counters", {}).get("pubmed_queries", 0)) + 1
    state["last_pmids"] = result["pmids"]
    store.save(state)
    console.ok(f"{result['count']} total hits; {len(result['pmids'])} PMIDs returned")
    console.json(result)
    return 0 if result["pmids"] else 5


def cmd_fetch_records(args: argparse.Namespace, console: Console) -> int:
    store = StateStore(args.state)
    state = store.load()
    # Merge PMIDs from all executed retrieval runs so multi-query ladders
    # contribute every hit, not just the last search.
    pmids = []
    for run in state.get("retrieval_runs", []):
        pmids.extend(run.get("pmids", []))
    pmids = list(dict.fromkeys(pmids))
    if not pmids:
        pmids = list(dict.fromkeys(state.get("last_pmids", [])))
    if not pmids:
        console.blocked("no PMIDs available to fetch")
        StateOps.add_blocker(state, "missing_pmids", "No PMIDs in state.", stage="fetch-records", advice="Run search-pubmed first.")
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
    state["records"] = StateOps.replace_by_key(state.get("records", []), records, "pmid")
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
    diag = state.get("diagnostics") or Diagnoser().diagnose(state)
    console.json({
        "status": state.get("status"),
        "diagnostic_status": diag.get("status"),
        "next": diag.get("recommended_next_actions", []),
        "records": len(state.get("records", [])),
        "evidence": len(state.get("evidence", [])),
        "blockers": len(state.get("blockers", [])),
        "report_path": state.get("report_path", ""),
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


def _select_query(state: dict[str, Any], query_id: str) -> dict[str, Any] | None:
    ladder = state.get("query_ladder", [])
    if query_id:
        for query in ladder:
            if query.get("query_id") == query_id:
                return query
        return None
    for query in ladder:
        if not query.get("executed"):
            return query
    return ladder[0] if ladder else None
