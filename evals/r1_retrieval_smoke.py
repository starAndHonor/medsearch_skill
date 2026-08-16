"""Small retrieval-only audit for R1 convergence.

This is intentionally not a production pipeline. It compares the frozen R1
root query snapshot (loaded explicitly for historical diagnosis), the active
plugin behavior, and an untagged raw PubMed baseline on a fixed sample.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "medlit-cli"
sys.path.insert(0, str(ROOT))

from medlit.http import HttpClient, ncbi_identity  # noqa: E402
from medlit.pubmed.mesh import MeshValidator  # noqa: E402


EUTILS_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EVAL_QUERY_IDS = {
    "Q1_broad_conceptual",
    "Q1b_and_terms",
    "Q1c_drugclass_property",
    "Q2_focused_primary",
}

# Hand-written counterfactuals are restricted to diagnosis. They use no gold
# text or PMID and are never merged into a scored production result.
COUNTERFACTUALS = {
    "67d74cde18b1e36f2e00003c": {
        "entity_only": "RankMHC",
    },
    "67e6cf7218b1e36f2e0000d1": {
        "rare_anchor_only": "MR-PheWAS",
        "rare_anchor_tiab": "MR-PheWAS[Title/Abstract]",
    },
    "67e5530418b1e36f2e0000aa": {
        "drug_anchor_only": "Plozasiran",
        "drug_and_condition_tiab": "Plozasiran[Title/Abstract] AND pancreatitis[Title/Abstract]",
    },
    "67e6b93718b1e36f2e0000be": {
        "drug_anchor_only": "nipocalimab",
        "drug_anchor_tiab": "nipocalimab[Title/Abstract]",
    },
    "67e6cf2618b1e36f2e0000d0": {
        "drug_and_disease_tiab": "Zotiraciclib[Title/Abstract] AND glioblastoma[Title/Abstract]",
    },
    "67cc973e81b1027333000011": {
        "class_and_property": (
            '(PDE5[Title/Abstract] OR "phosphodiesterase type 5 inhibitor"[Title/Abstract]) '
            'AND ("half-life"[Title/Abstract] OR pharmacokinetic*[Title/Abstract])'
        ),
    },
}


def load_query_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load plugin query module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PoliteHttp:
    """Minimal global pacing wrapper around the repository HTTP client."""

    def __init__(self, cache_dir: Path, min_interval: float = 0.36):
        self.inner = HttpClient(cache_dir=cache_dir, retries=2)
        self.min_interval = min_interval
        self.last_call = 0.0

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        self._pace_if_uncached(url)
        return self.inner.get_json(url, headers=headers)

    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        self._pace_if_uncached(url)
        return self.inner.get_text(url, headers=headers)

    def _pace_if_uncached(self, url: str) -> None:
        cache_path = self.inner._cache_path(url)  # audit helper; avoid sleeping on cache hits
        if cache_path is None or not cache_path.exists():
            wait = self.min_interval - (time.monotonic() - self.last_call)
            if wait > 0:
                time.sleep(wait)
            self.last_call = time.monotonic()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--golden",
        default=str(ROOT / "data" / "bioasq_13b_test_merged.json"),
    )
    parser.add_argument("--output", default=str(ROOT / "evals" / "r1_smoke" / "results.json"))
    parser.add_argument("--cache-dir", default=str(ROOT / "evals" / "r1_smoke" / "cache"))
    parser.add_argument("--retmax", type=int, default=500)
    parser.add_argument("--max-date", default="2025/12/31")
    parser.add_argument("--ids", nargs="*", default=[])
    return parser.parse_args()


def normalize_pmids(documents: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for doc in documents or []:
        tail = str(doc).rstrip("/").rsplit("/", 1)[-1]
        if tail.isdigit() and tail not in seen:
            seen.add(tail)
            out.append(tail)
    return out


def diagnostic_sample(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """First question of every answer type in each of the four test batches."""
    selected = []
    for batch in ("13B1", "13B2", "13B3", "13B4"):
        for qtype in ("factoid", "list", "yesno", "summary"):
            selected.append(next(q for q in questions if q.get("batch") == batch and q.get("type") == qtype))
    return selected


def esearch(http: PoliteHttp, query: str, retmax: int, max_date: str = "") -> dict[str, Any]:
    term = query
    if max_date:
        term = (
            f'({query}) AND ("1900/01/01"[Date - Publication] : '
            f'"{max_date}"[Date - Publication])'
        )
    params: dict[str, Any] = {
        "db": "pubmed",
        "term": term,
        "retmax": retmax,
        "retmode": "json",
        "sort": "relevance",
    }
    params.update(ncbi_identity())
    url = f"{EUTILS_SEARCH}?{urllib.parse.urlencode(params)}"
    data = http.get_json(url).get("esearchresult", {})
    return {
        "entered_query": query,
        "effective_query": term,
        "count": int(data.get("count", 0)),
        "pmids": [str(x) for x in data.get("idlist", [])],
        "query_translation": data.get("querytranslation", ""),
        "translationset": data.get("translationset", []),
    }


def merged_in_order(runs: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for run in runs:
        for pmid in run["pmids"]:
            if pmid not in seen:
                seen.add(pmid)
                out.append(pmid)
    return out


def rrf(runs: list[dict[str, Any]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for run in runs:
        for rank, pmid in enumerate(run["pmids"], start=1):
            scores[pmid] = scores.get(pmid, 0.0) + 1.0 / (k + rank)
            best_rank[pmid] = min(best_rank.get(pmid, rank), rank)
    return sorted(scores, key=lambda p: (-scores[p], best_rank[p], int(p)))


def rank_of(pmids: list[str], target: str) -> int | None:
    try:
        return pmids.index(target) + 1
    except ValueError:
        return None


def metrics(pmids: list[str], gold: list[str]) -> dict[str, float | int | None]:
    gold_set = set(gold)
    result: dict[str, float | int | None] = {"gold_count": len(gold)}
    for depth in (10, 50, 100, 500):
        hits = sum(p in gold_set for p in pmids[:depth])
        result[f"hits_{depth}"] = hits
        result[f"recall_{depth}"] = hits / len(gold) if gold else 0.0
    ap_sum = 0.0
    hits = 0
    for rank, pmid in enumerate(pmids[:10], start=1):
        if pmid in gold_set:
            hits += 1
            ap_sum += hits / rank
    result["ap_10"] = ap_sum / len(gold) if gold else 0.0
    ranks = [rank_of(pmids, p) for p in gold]
    visible = [r for r in ranks if r is not None]
    result["first_gold_rank"] = min(visible) if visible else None
    return result


def aggregate(rows: list[dict[str, Any]], system: str) -> dict[str, float]:
    values = [row["systems"][system]["metrics"] for row in rows]
    return {
        "questions": len(values),
        "hit_at_10": sum(v["hits_10"] > 0 for v in values) / len(values),
        "macro_recall_10": sum(v["recall_10"] for v in values) / len(values),
        "macro_recall_50": sum(v["recall_50"] for v in values) / len(values),
        "macro_recall_100": sum(v["recall_100"] for v in values) / len(values),
        "macro_recall_500": sum(v["recall_500"] for v in values) / len(values),
        "map_10": sum(v["ap_10"] for v in values) / len(values),
    }


def plan_queries(planner: Any, builder: Any, pico: dict[str, Any], http: PoliteHttp) -> tuple[dict, list, list]:
    plan = planner.plan(pico)
    validation = MeshValidator(http).validate_term_plan(plan)
    ladder = builder.build(plan, validation)
    return plan, validation, ladder


def classify_gold(
    pmid: str,
    raw: list[str],
    raw_cutoff: list[str],
    legacy_runs: list[dict[str, Any]],
    legacy_concat: list[str],
    legacy_rrf: list[str],
    present: set[str],
) -> dict[str, Any]:
    variant_ranks = {run["query_id"]: rank_of(run["pmids"], pmid) for run in legacy_runs}
    visible = [r for r in variant_ranks.values() if r is not None]
    best_variant = min(visible) if visible else None
    raw_rank = rank_of(raw, pmid)
    cutoff_rank = rank_of(raw_cutoff, pmid)
    concat_rank = rank_of(legacy_concat, pmid)
    rrf_rank = rank_of(legacy_rrf, pmid)

    if concat_rank is not None and concat_rank <= 10:
        bucket = "legacy_top10"
    elif best_variant is not None and best_variant <= 10 and (concat_rank is None or concat_rank > 10):
        bucket = "concat_order_loss"
    elif rrf_rank is not None and rrf_rank <= 10 and (concat_rank is None or concat_rank > 10):
        bucket = "fusion_loss_rrf_recovers"
    elif raw_rank is not None and raw_rank <= 10 and (concat_rank is None or concat_rank > 10):
        bucket = "legacy_query_or_ranking_loss_raw_top10"
    elif best_variant is not None:
        bucket = "candidate_ranking_depth"
    elif raw_rank is not None:
        bucket = "legacy_query_formulation_loss"
    elif pmid not in present:
        bucket = "not_present_in_current_pubmed"
    else:
        bucket = "unreached_by_tested_queries"

    return {
        "pmid": pmid,
        "bucket": bucket,
        "raw_rank": raw_rank,
        "raw_cutoff_rank": cutoff_rank,
        "legacy_concat_rank": concat_rank,
        "legacy_rrf_rank": rrf_rank,
        "best_legacy_variant_rank": best_variant,
        "legacy_variant_ranks": variant_ranks,
        "date_cutoff_excluded_within_depth": raw_rank is not None and cutoff_rank is None,
    }


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    http = PoliteHttp(Path(args.cache_dir))
    legacy_query = load_query_module(
        ROOT / "medlit" / "pubmed" / "query.py", "medlit_r1_legacy_query_smoke"
    )
    plugin_query = load_query_module(
        PLUGIN_ROOT / "medlit" / "pubmed" / "query.py", "medlit_plugin_query_smoke"
    )

    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    questions = list(golden["questions"])
    if args.ids:
        by_id = {q["id"]: q for q in questions}
        sample = [by_id[qid] for qid in args.ids]
    else:
        sample = diagnostic_sample(questions)

    rows: list[dict[str, Any]] = []
    for index, question in enumerate(sample, start=1):
        qid = question["id"]
        body = question["body"]
        gold = normalize_pmids(question.get("documents", []))
        print(f"[{index}/{len(sample)}] {qid} {question['type']}: {body}", flush=True)

        raw_current = esearch(http, body, args.retmax)
        raw_cutoff = esearch(http, body, args.retmax, args.max_date)
        presence_query = " OR ".join(f"{pmid}[uid]" for pmid in gold)
        presence = esearch(http, presence_query, max(len(gold), 1))
        present = set(presence["pmids"])
        filtered_presence = esearch(
            http,
            f"({presence_query}) AND humans[MeSH Terms] AND english[Language]",
            max(len(gold), 1),
        )
        present_after_default_filters = set(filtered_presence["pmids"])
        human_presence = set(
            esearch(
                http,
                f"({presence_query}) AND humans[MeSH Terms]",
                max(len(gold), 1),
            )["pmids"]
        )
        english_presence = set(
            esearch(
                http,
                f"({presence_query}) AND english[Language]",
                max(len(gold), 1),
            )["pmids"]
        )

        pico = {
            "population": body,
            "intervention_or_exposure": "",
            "comparator": "",
            "outcome": "",
            "study_designs": ["randomized controlled trial", "systematic review", "meta-analysis"],
        }

        eval_plan, eval_validation, eval_ladder = plan_queries(
            legacy_query.TermPlanner(), legacy_query.QueryBuilder(), pico, http
        )
        eval_runs = []
        for query in eval_ladder:
            if query["query_id"] not in EVAL_QUERY_IDS:
                continue
            result = esearch(http, query["exact_query"], args.retmax, args.max_date)
            result["query_id"] = query["query_id"]
            result["purpose"] = query.get("purpose", "")
            eval_runs.append(result)

        eval_no_mesh_ladder = legacy_query.QueryBuilder().build(eval_plan, [])
        eval_no_mesh_runs = []
        for query in eval_no_mesh_ladder:
            if query["query_id"] not in EVAL_QUERY_IDS:
                continue
            result = esearch(http, query["exact_query"], args.retmax, args.max_date)
            result["query_id"] = query["query_id"]
            result["purpose"] = query.get("purpose", "")
            eval_no_mesh_runs.append(result)

        plugin_plan, plugin_validation, plugin_ladder = plan_queries(
            plugin_query.TermPlanner(), plugin_query.QueryBuilder(), pico, http
        )
        plugin_runs = []
        for query in plugin_ladder:
            result = esearch(http, query["exact_query"], args.retmax)
            result["query_id"] = query["query_id"]
            result["purpose"] = query.get("purpose", "")
            plugin_runs.append(result)

        counterfactual_runs = []
        for name, query in COUNTERFACTUALS.get(qid, {}).items():
            result = esearch(http, query, args.retmax, args.max_date)
            result["query_id"] = name
            result["metrics"] = metrics(result["pmids"], gold)
            counterfactual_runs.append(result)

        eval_concat = merged_in_order(eval_runs)
        eval_rrf = rrf(eval_runs)
        eval_no_mesh_concat = merged_in_order(eval_no_mesh_runs)
        plugin_concat = merged_in_order(plugin_runs)
        row = {
            "id": qid,
            "batch": question.get("batch"),
            "type": question.get("type"),
            "question": body,
            "gold_pmids": gold,
            "gold_present_in_current_pubmed": sorted(present, key=int),
            "gold_present_after_default_filters": sorted(present_after_default_filters, key=int),
            "gold_excluded_by_default_filters": sorted(
                present - present_after_default_filters, key=int
            ),
            "gold_excluded_by_humans_filter": sorted(present - human_presence, key=int),
            "gold_excluded_by_english_filter": sorted(present - english_presence, key=int),
            "diagnostic_counterfactuals": counterfactual_runs,
            "systems": {
                "raw_current": {**raw_current, "metrics": metrics(raw_current["pmids"], gold)},
                "raw_cutoff": {**raw_cutoff, "metrics": metrics(raw_cutoff["pmids"], gold)},
                "eval_legacy_concat": {
                    "pmids": eval_concat,
                    "metrics": metrics(eval_concat, gold),
                    "runs": eval_runs,
                    "term_plan": eval_plan,
                    "mesh_validation": eval_validation,
                },
                "eval_legacy_rrf_diagnostic": {
                    "pmids": eval_rrf,
                    "metrics": metrics(eval_rrf, gold),
                },
                "eval_legacy_no_mesh_concat": {
                    "pmids": eval_no_mesh_concat,
                    "metrics": metrics(eval_no_mesh_concat, gold),
                    "runs": eval_no_mesh_runs,
                },
                "plugin_legacy_concat": {
                    "pmids": plugin_concat,
                    "metrics": metrics(plugin_concat, gold),
                    "runs": plugin_runs,
                    "term_plan": plugin_plan,
                    "mesh_validation": plugin_validation,
                },
            },
        }
        row["gold_attribution"] = [
            classify_gold(
                pmid,
                raw_current["pmids"],
                raw_cutoff["pmids"],
                eval_runs,
                eval_concat,
                eval_rrf,
                present,
            )
            for pmid in gold
        ]
        rows.append(row)
        output.write_text(json.dumps({"questions": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    systems = [
        "raw_current",
        "raw_cutoff",
        "eval_legacy_concat",
        "eval_legacy_rrf_diagnostic",
        "eval_legacy_no_mesh_concat",
        "plugin_legacy_concat",
    ]
    result = {
        "metadata": {
            "purpose": "R1 diagnostic smoke, not a benchmark estimate",
            "sample_rule": "first question of each answer type in each 13B batch",
            "retmax": args.retmax,
            "derived_max_date": args.max_date,
            "golden": str(Path(args.golden).resolve()),
        },
        "aggregate": {system: aggregate(rows, system) for system in systems},
        "questions": rows,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["aggregate"], indent=2), flush=True)
    print(f"Wrote {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
