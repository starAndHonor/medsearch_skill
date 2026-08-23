"""Deterministic fusion of ranked retrieval lanes."""

from __future__ import annotations

from typing import Any


def reciprocal_rank_fusion(
    runs: list[dict[str, Any]], *, k: int = 60, depth: int | None = None
) -> list[str]:
    """Fuse de-duplicated PMID rankings with reciprocal rank fusion.

    A repeated PMID within one lane contributes once. Ties are resolved by the
    best lane rank, then first lane occurrence, then PMID so reruns are stable.
    """
    if k < 0:
        raise ValueError("RRF k must be non-negative")

    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    first_seen: dict[str, tuple[int, int]] = {}
    for lane_index, run in enumerate(runs):
        seen_in_lane: set[str] = set()
        pmids = run.get("pmids", []) or []
        if depth is not None:
            pmids = pmids[:depth]
        for rank, raw_pmid in enumerate(pmids, start=1):
            pmid = str(raw_pmid).strip()
            if not pmid or pmid in seen_in_lane:
                continue
            seen_in_lane.add(pmid)
            scores[pmid] = scores.get(pmid, 0.0) + 1.0 / (k + rank)
            best_rank[pmid] = min(best_rank.get(pmid, rank), rank)
            first_seen.setdefault(pmid, (lane_index, rank))

    return sorted(
        scores,
        key=lambda pmid: (
            -scores[pmid],
            best_rank[pmid],
            first_seen[pmid],
            int(pmid) if pmid.isdigit() else pmid,
        ),
    )
