"""Ranking metrics shared by the CLIP evaluation and the TF-IDF baseline.

Each query has exactly one correct item, so precision and recall at k differ
only by a constant: R@k is 1 if the correct item is in the top k, and P@k is
that divided by k. Both are reported because the spec asks for both, but R@k
is the number that carries information.
"""

from __future__ import annotations

import numpy as np


def ranks_from_scores(scores: np.ndarray) -> np.ndarray:
    """1-based rank of the correct item for each query.

    ``scores`` is (n_queries, n_items) where item i is correct for query i.
    Ties are broken pessimistically — a method that returns all-equal scores
    scores like random guessing rather than perfectly.
    """
    n = scores.shape[0]
    correct = scores[np.arange(n), np.arange(n)][:, None]
    beaten_or_tied = (scores > correct).sum(axis=1) + (scores == correct).sum(axis=1) - 1
    return beaten_or_tied + 1


def summarise(ranks: np.ndarray, ks=(1, 3, 5)) -> dict:
    n = len(ranks)
    out = {"n": n, "mrr": float(np.mean(1.0 / ranks)), "median_rank": float(np.median(ranks))}
    for k in ks:
        hits = float(np.mean(ranks <= k))
        out[f"recall@{k}"] = hits
        out[f"precision@{k}"] = hits / k
    return out


def table(rows: dict[str, dict], ks=(1, 3, 5)) -> str:
    """Render {method: metrics} as a fixed-width table."""
    headers = ["method"] + [f"R@{k}" for k in ks] + [f"P@{k}" for k in ks] + ["MRR", "med"]
    width = max(len(name) for name in rows) + 2
    lines = [
        f"{headers[0]:<{width}}" + "".join(f"{h:>9}" for h in headers[1:]),
        "-" * (width + 9 * (len(headers) - 1)),
    ]
    for name, m in rows.items():
        cells = [f"{m[f'recall@{k}']:.3f}" for k in ks]
        cells += [f"{m[f'precision@{k}']:.3f}" for k in ks]
        cells += [f"{m['mrr']:.3f}", f"{m['median_rank']:.0f}"]
        lines.append(f"{name:<{width}}" + "".join(f"{c:>9}" for c in cells))
    return "\n".join(lines)
