#!/usr/bin/env python
"""Frozen R2-Minimal retrieval validation and component ablation.

The runner reuses the saved R1 legacy runs as the before condition and only
requests the plugin's fixed query lanes. Candidate-depth curves are computed
offline by truncating each saved lane before fusion.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "medlit-cli"
sys.path.insert(0, str(PLUGIN_ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from medlit.pubmed.query import QueryBuilder, TermPlanner
from medlit.retrieval.fusion import reciprocal_rank_fusion
from r1_retrieval_smoke import PoliteHttp, esearch, merged_in_order, metrics


DEPTHS = (20, 50, 100, 200, 500)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", default=str(ROOT / "evals" / "r2_validation" / "before.json"))
    parser.add_argument("--selection", default=str(ROOT / "evals" / "r2_validation" / "validation_set.json"))
    parser.add_argument("--output", default=str(ROOT / "evals" / "r2_validation" / "after_ablation.json"))
    parser.add_argument("--cache-dir", default=str(ROOT / "evals" / "r2_validation" / "cache"))
    parser.add_argument("--max-date", default="2025/12/31")
    parser.add_argument("--retmax", type=int, default=500)
    return parser.parse_args()


def truncate_runs(runs: list[dict[str, Any]], depth: int) -> list[dict[str, Any]]:
    return [{**run, "pmids": list(run.get("pmids", []))[:depth]} for run in runs]


def score(pmids: list[str], gold: list[str]) -> dict[str, Any]:
    return metrics(pmids, gold)


def aggregate(rows: list[dict[str, Any]], system: str) -> dict[str, Any]:
    values = [row["systems"][system]["metrics"] for row in rows]
    total_gold = sum(int(value["gold_count"]) for value in values)
    result: dict[str, Any] = {
        "questions": len(values),
        "gold_pmids": total_gold,
        "hit_at_10": sum(value["hits_10"] > 0 for value in values) / len(values),
        "map_10": sum(value["ap_10"] for value in values) / len(values),
    }
    for depth in (10, 50, 100, 500):
        result[f"macro_recall_{depth}"] = sum(value[f"recall_{depth}"] for value in values) / len(values)
        result[f"micro_recall_{depth}"] = (
            sum(int(value[f"hits_{depth}"]) for value in values) / total_gold if total_gold else 0.0
        )
    return result


def run_queries(
    http: PoliteHttp,
    ladder: list[dict[str, Any]],
    retmax: int,
    max_date: str,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for lane in ladder:
        result = esearch(http, lane["exact_query"], retmax, max_date)
        result["query_id"] = lane["query_id"]
        result["purpose"] = lane.get("purpose", "")
        runs.append(result)
    return runs


def main() -> int:
    args = parse_args()
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    selected = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    selected_ids = [item["id"] for item in selected["questions"]]
    before_by_id = {row["id"]: row for row in before["questions"]}
    if set(selected_ids) != set(before_by_id):
        raise ValueError("Frozen selection and before.json question IDs differ")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    http = PoliteHttp(Path(args.cache_dir))
    rows: list[dict[str, Any]] = []

    for index, qid in enumerate(selected_ids, start=1):
        old = before_by_id[qid]
        question = old["question"]
        gold = [str(pmid) for pmid in old["gold_pmids"]]
        print(f"[{index}/{len(selected_ids)}] {qid}: {question}", flush=True)

        pico = {
            "question": question,
            "population": question,
            "intervention_or_exposure": "",
            "comparator": "",
            "outcome": "",
        }
        fixed_plan = TermPlanner().plan(pico)
        fixed_ladder = QueryBuilder().build(fixed_plan, [])
        fixed_runs = run_queries(http, fixed_ladder, args.retmax, args.max_date)

        forced_filter_plan = copy.deepcopy(fixed_plan)
        forced_filter_plan["filters"] = {"humans": True, "language": "english"}
        forced_filter_ladder = QueryBuilder().build(forced_filter_plan, [])
        fixed_ids = {lane["query_id"] for lane in fixed_ladder}
        extra_filter_lanes = [lane for lane in forced_filter_ladder if lane["query_id"] not in fixed_ids]
        forced_filter_runs = fixed_runs + run_queries(
            http, extra_filter_lanes, args.retmax, args.max_date
        )

        legacy_runs = old["systems"]["eval_legacy_concat"]["runs"]
        systems: dict[str, dict[str, Any]] = {}
        for depth in DEPTHS:
            legacy_at_depth = truncate_runs(legacy_runs, depth)
            fixed_at_depth = truncate_runs(fixed_runs, depth)
            forced_at_depth = truncate_runs(forced_filter_runs, depth)
            rankings = {
                f"legacy_concat_d{depth}": merged_in_order(legacy_at_depth),
                f"legacy_rrf_d{depth}": reciprocal_rank_fusion(legacy_at_depth),
                f"fixed_concat_d{depth}": merged_in_order(fixed_at_depth),
                f"fixed_rrf_d{depth}": reciprocal_rank_fusion(fixed_at_depth),
                f"fixed_rrf_forced_filters_d{depth}": reciprocal_rank_fusion(forced_at_depth),
            }
            for name, pmids in rankings.items():
                systems[name] = {"pmids": pmids, "metrics": score(pmids, gold)}

        row = {
            "id": qid,
            "batch": old.get("batch"),
            "type": old.get("type"),
            "question": question,
            "gold_pmids": gold,
            "term_plan": fixed_plan,
            "fixed_ladder": fixed_ladder,
            "fixed_runs": fixed_runs,
            "forced_filter_extra_lanes": extra_filter_lanes,
            "forced_filter_runs": forced_filter_runs,
            "systems": systems,
        }
        rows.append(row)
        output.write_text(json.dumps({"questions": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    system_names = list(rows[0]["systems"])
    result = {
        "metadata": {
            "schema": "medlit-r2-minimal-validation/v1",
            "selection": str(Path(args.selection).resolve()),
            "before": str(Path(args.before).resolve()),
            "retmax_requested_once_per_lane": args.retmax,
            "depths_offline_truncated_per_lane": list(DEPTHS),
            "max_date": args.max_date,
            "mesh": "disabled; retained as an experimental product switch",
            "interpretation": {
                "legacy_rrf_minus_legacy_concat": "fusion-only",
                "fixed_concat_minus_legacy_concat": "term-construction-only",
                "fixed_rrf_minus_legacy_concat": "combined term construction and fusion",
                "fixed_rrf_minus_fixed_rrf_forced_filters": "removing unconditional humans/English lane",
            },
        },
        "aggregate": {name: aggregate(rows, name) for name in system_names},
        "questions": rows,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["aggregate"], indent=2), flush=True)
    print(f"Wrote {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
