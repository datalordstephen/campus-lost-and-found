"""Campus test set: zero-shot CLIP vs the keyword baseline on real campus photos.

The COCO run (eval/evaluate.py) shows the method works on clean, captioned
stock photos. This run asks the question the thesis actually has to answer:
does it still work on phone photos of the items students really lose, taken
where they really get lost, described the way owners and finders really write?

Inputs (see eval/campus/README.md):
  eval/campus/campus_testset.csv   one row per photographed item
  eval/data/campus/<filename>      the photos themselves (gitignored)

Every query has exactly one correct item, so this is a 56-way retrieval test.

Methods compared
  clip  A -> photo          owner's lost report vs the found photo (the system)
  clip  "a photo of" A      same, with the standard zero-shot prompt template
  clip  A -> photo+B        photo averaged with the finder's note (what
                            backend/routers/items.py stores today)
  clip  A -> B (text only)  CLIP's text encoder alone, no image: separates
                            "the photo helps" from "CLIP is a better text matcher"
  tfidf A -> B              keyword search over the finder's note: the logbook
                            baseline, i.e. what lost-and-found does without this system
  ... and the same five with the deliberately vague query ("a black watch")

Plus the reverse direction (found photo -> lost reports), which is the
found-item flow of the system, and a threshold analysis that treats every
(lost report, found item) pair as a match / non-match decision.

    uv run python eval/evaluate_campus.py
    uv run python eval/evaluate_campus.py --out eval/results/campus
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.baseline import score_matrix  # noqa: E402
from eval.metrics import ranks_from_scores, summarise, table  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "campus" / "campus_testset.csv"
DEFAULT_IMAGES = HERE / "data" / "campus"
DEFAULT_OUT = HERE / "results" / "campus"
KS = (1, 3, 5)


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
def bootstrap_ci(ranks: np.ndarray, k: int, rounds: int = 5000, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(ranks)
    draws = [np.mean(ranks[rng.integers(0, n, n)] <= k) for _ in range(rounds)]
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def paired_bootstrap(a: np.ndarray, b: np.ndarray, k: int, rounds: int = 5000, seed: int = 0) -> float:
    """One-sided p-value that A beats B at R@k, resampling queries jointly."""
    rng = np.random.default_rng(seed)
    n = len(a)
    if np.mean(a <= k) - np.mean(b <= k) <= 0:
        return 1.0
    losses = 0
    for _ in range(rounds):
        idx = rng.integers(0, n, n)
        if np.mean(a[idx] <= k) - np.mean(b[idx] <= k) <= 0:
            losses += 1
    return losses / rounds


def threshold_analysis(scores: np.ndarray, n_points: int = 41) -> dict:
    """Treat every (query, item) cell as a binary match decision.

    The diagonal holds the n true matches; the other n*(n-1) cells are
    non-matches. Sweeping a similarity threshold gives precision, recall and
    false-positive rate in the classification sense — the numbers that say
    how many wrong items a student would be shown for each right one.
    """
    n = scores.shape[0]
    truth = np.eye(n, dtype=bool)
    pos, neg = scores[truth], scores[~truth]
    lo, hi = float(scores.min()), float(scores.max())
    sweep = []
    for t in np.linspace(lo, hi, n_points):
        tp = int((pos >= t).sum())
        fp = int((neg >= t).sum())
        recall = tp / n
        precision = tp / (tp + fp) if tp + fp else 1.0
        fpr = fp / neg.size
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        sweep.append({
            "threshold": round(float(t), 4), "recall": round(recall, 4),
            "precision": round(precision, 4), "fpr": round(fpr, 5), "f1": round(f1, 4),
            "false_matches_per_query": round(fp / n, 3),
        })
    # ROC-AUC via the rank-sum identity: P(random positive > random negative).
    order = np.concatenate([pos, neg]).argsort().argsort() + 1
    auc = (order[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
    best = max(sweep, key=lambda s: s["f1"])
    return {
        "roc_auc": round(float(auc), 4),
        "mean_true_score": round(float(pos.mean()), 4),
        "mean_false_score": round(float(neg.mean()), 4),
        "best_f1": best,
        "sweep": sweep,
    }


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def load_records(csv_path: Path, image_dir: Path) -> list[dict]:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    records, missing = [], []
    # Drive downloads sometimes change extension case; match case-insensitively.
    on_disk = {p.name.lower(): p for p in image_dir.iterdir()} if image_dir.exists() else {}
    for r in rows:
        path = on_disk.get(r["filename"].lower())
        if path is None:
            missing.append(r["filename"])
            continue
        for field in ("description_A_lost_report", "description_B_finder_note"):
            if not r.get(field, "").strip():
                sys.exit(f"{r['filename']}: empty {field}")
        r["image_path"] = str(path)
        r["hand_held"] = "hand-held" in (r.get("notes", "") + r.get("setting", ""))
        records.append(r)
    if missing:
        sys.exit(
            f"{len(missing)} photo(s) listed in {csv_path.name} not found in {image_dir}:\n  "
            + "\n  ".join(missing)
        )
    return records


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    records = load_records(args.csv, args.images)
    n = len(records)
    A = [r["description_A_lost_report"].strip() for r in records]
    B = [r["description_B_finder_note"].strip() for r in records]
    V = [r.get("description_vague", "").strip() or r["category"] for r in records]
    print(f"{n} items, {len({r['category'] for r in records})} categories, "
          f"{sum(1 for r in records if r['lookalike_pair'])} in look-alike pairs\n")

    from backend import clip_encoder

    t0 = time.time()
    clip_encoder.load_model()
    print(f"model loaded in {time.time() - t0:.1f}s; encoding...")
    t0 = time.time()
    img = clip_encoder.encode_images([r["image_path"] for r in records])
    enc = clip_encoder.encode_texts
    a_vec, a_tpl, b_vec = enc(A), enc([f"a photo of {q}" for q in A]), enc(B)
    v_vec, v_tpl = enc(V), enc([f"a photo of {q}" for q in V])
    print(f"encoded {n} images + {5 * n} texts in {time.time() - t0:.1f}s\n")

    combined = img + b_vec
    combined /= np.linalg.norm(combined, axis=1, keepdims=True)

    def z(s: np.ndarray) -> np.ndarray:
        """Standardise each query's row so CLIP and TF-IDF scores are comparable."""
        return (s - s.mean(axis=1, keepdims=True)) / (s.std(axis=1, keepdims=True) + 1e-9)

    tfidf_a, tfidf_v = score_matrix(A, B), score_matrix(V, B)
    runs = {
        "clip  A -> photo": a_vec @ img.T,
        'clip  "a photo of" A -> photo': a_tpl @ img.T,
        "clip  A -> photo+B": a_vec @ combined.T,
        "clip  A -> B (text only)": a_vec @ b_vec.T,
        "tfidf A -> B (baseline)": tfidf_a,
        "hybrid clip photo + tfidf": z(a_vec @ img.T) + z(tfidf_a),
        "clip  vague -> photo": v_vec @ img.T,
        'clip  "a photo of" vague -> photo': v_tpl @ img.T,
        "clip  vague -> photo+B": v_vec @ combined.T,
        "clip  vague -> B (text only)": v_vec @ b_vec.T,
        "tfidf vague -> B (baseline)": tfidf_v,
        "hybrid vague: clip photo + tfidf": z(v_vec @ img.T) + z(tfidf_v),
    }
    # Reverse direction: a found photo arrives, which lost reports does it surface?
    reverse = {
        "clip  photo -> A": (a_vec @ img.T).T,
        "tfidf B -> A (baseline)": score_matrix(A, B).T,
    }

    ranks = {name: ranks_from_scores(s) for name, s in runs.items()}
    rranks = {name: ranks_from_scores(s) for name, s in reverse.items()}
    results = {name: summarise(r, KS) for name, r in ranks.items()}
    rresults = {name: summarise(r, KS) for name, r in rranks.items()}

    print("LOST REPORT -> FOUND ITEM  (text -> image; 56-way)")
    print(table({k: v for k, v in results.items() if "vague" not in k}, KS))
    print("\nVAGUE QUERIES  (e.g. 'a black watch')")
    print(table({k: v for k, v in results.items() if "vague" in k}, KS))
    print("\nFOUND ITEM -> LOST REPORT  (image -> text; the found-item flow)")
    print(table(rresults, KS))

    main_run, base_run = "clip  A -> photo", "tfidf A -> B (baseline)"
    print("\n95% CI (bootstrap over queries)")
    cis = {}
    for name in (main_run, base_run, "clip  A -> photo+B", "hybrid clip photo + tfidf",
                 "clip  vague -> photo", "tfidf vague -> B (baseline)"):
        cis[name] = {}
        for k in (1, 5):
            lo, hi = bootstrap_ci(ranks[name], k)
            cis[name][f"recall@{k}"] = [lo, hi]
            print(f"  {name:<34} R@{k} {np.mean(ranks[name] <= k):.3f}  [{lo:.3f}, {hi:.3f}]")

    print("\nPaired comparisons (one-sided bootstrap)")
    comparisons = {}
    pairs = [
        (main_run, base_run),
        (main_run, "clip  A -> photo+B"),
        (main_run, "clip  A -> B (text only)"),
        ("hybrid clip photo + tfidf", base_run),
        ("clip  vague -> photo", "tfidf vague -> B (baseline)"),
        ("hybrid vague: clip photo + tfidf", "tfidf vague -> B (baseline)"),
    ]
    for a, b in pairs:
        for k in (1, 3, 5):
            for x, y in ((a, b), (b, a)):
                p = paired_bootstrap(ranks[x], ranks[y], k)
                if p < 1.0:
                    d = float(np.mean(ranks[x] <= k) - np.mean(ranks[y] <= k))
                    comparisons[f"{x} > {y} @R{k}"] = {"delta": d, "p": p}
                    print(f"  {x} beats {y}  R@{k} {d:+.3f}  p={p:.4f}  "
                          f"{'significant' if p < 0.05 else 'not significant'}")

    # Threshold analysis: how many wrong candidates per right one?
    print("\nMATCH / NON-MATCH AT A SIMILARITY THRESHOLD")
    thresholds = {}
    for name in (main_run, base_run, "clip  A -> photo+B", "hybrid clip photo + tfidf"):
        th = threshold_analysis(runs[name])
        thresholds[name] = th
        b = th["best_f1"]
        print(f"  {name:<28} ROC-AUC {th['roc_auc']:.3f}  mean sim true {th['mean_true_score']:.3f} "
              f"vs false {th['mean_false_score']:.3f}  | best F1 {b['f1']:.3f} at t={b['threshold']:.3f} "
              f"(P {b['precision']:.3f}, R {b['recall']:.3f}, {b['false_matches_per_query']} false/query)")

    # Breakdowns that explain *why* numbers come out as they do.
    def breakdown(key) -> dict:
        groups = defaultdict(list)
        for i, r in enumerate(records):
            groups[key(r)].append(i)
        out = {}
        for g, idx in sorted(groups.items(), key=lambda kv: str(kv[0])):
            idx = np.array(idx)
            out[str(g)] = {
                "n": len(idx),
                **{f"{m}_R@1": float(np.mean(ranks[m][idx] <= 1)) for m in (main_run, base_run)},
                **{f"{m}_R@5": float(np.mean(ranks[m][idx] <= 5)) for m in (main_run, base_run)},
                **{f"{m}_MRR": float(np.mean(1 / ranks[m][idx])) for m in (main_run, base_run)},
            }
        return out

    breakdowns = {
        "lighting": breakdown(lambda r: r["lighting"]),
        "hand_held": breakdown(lambda r: "hand-held" if r["hand_held"] else "placed"),
        "lookalike": breakdown(lambda r: "in look-alike pair" if r["lookalike_pair"] else "no look-alike"),
        "category": breakdown(lambda r: r["category"]),
    }
    print("\nBREAKDOWNS  (CLIP vs TF-IDF, R@1 / R@5)")
    for title, groups in breakdowns.items():
        if title == "category":
            continue
        print(f"  by {title}")
        for g, m in groups.items():
            print(f"    {g:<22} n={m['n']:>2}  CLIP {m[main_run + '_R@1']:.2f}/{m[main_run + '_R@5']:.2f}"
                  f"   TF-IDF {m[base_run + '_R@1']:.2f}/{m[base_run + '_R@5']:.2f}")

    # Per-item table: the raw material for the failure-case write-up.
    names = [r["filename"] for r in records]
    per_item = []
    pair_of = {}
    for r in records:
        if r["lookalike_pair"]:
            pair_of.setdefault(r["lookalike_pair"], []).append(r["filename"])
    for i, r in enumerate(records):
        row = {
            "filename": r["filename"], "category": r["category"], "lookalike_pair": r["lookalike_pair"],
            "lighting": r["lighting"], "setting": r["setting"], "hand_held": r["hand_held"],
            "description_A": A[i], "description_B": B[i], "description_vague": V[i],
        }
        for label, name in (("clip", main_run), ("clip_combined", "clip  A -> photo+B"),
                            ("clip_textonly", "clip  A -> B (text only)"), ("tfidf", base_run),
                            ("hybrid", "hybrid clip photo + tfidf"),
                            ("clip_vague", "clip  vague -> photo"), ("tfidf_vague", "tfidf vague -> B (baseline)")):
            s = runs[name][i]
            order = np.argsort(-s)
            row[f"{label}_rank"] = int(ranks[name][i])
            row[f"{label}_top1"] = names[order[0]]
            row[f"{label}_top3"] = "|".join(names[j] for j in order[:3])
            row[f"{label}_score_correct"] = round(float(s[i]), 4)
            row[f"{label}_score_top1"] = round(float(s[order[0]]), 4)
        partner = [f for f in pair_of.get(r["lookalike_pair"], []) if f != r["filename"]]
        row["clip_top1_is_lookalike_partner"] = bool(partner) and row["clip_top1"] == partner[0]
        row["clip_photo_reverse_rank"] = int(rranks["clip  photo -> A"][i])
        per_item.append(row)

    print("\nCLIP FAILURES (A -> photo, correct item not ranked 1st)")
    for row in sorted(per_item, key=lambda r: -r["clip_rank"]):
        if row["clip_rank"] == 1:
            continue
        flag = "  <- confused with its look-alike" if row["clip_top1_is_lookalike_partner"] else ""
        print(f"  rank {row['clip_rank']:>2}  {row['filename']:<20} top-1 was {row['clip_top1']:<20} "
              f"TF-IDF rank {row['tfidf_rank']:>2}{flag}")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps({
        "n": n,
        "text_to_image": results,
        "image_to_text": rresults,
        "confidence_intervals": cis,
        "comparisons": comparisons,
        "thresholds": thresholds,
        "breakdowns": breakdowns,
    }, indent=2))
    with (args.out / "per_item.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per_item[0].keys()))
        w.writeheader()
        w.writerows(per_item)
    np.savez_compressed(args.out / "scores.npz", filenames=np.array(names),
                        **{k.replace(" ", "_").replace('"', ""): v for k, v in runs.items()})
    print(f"\nwrote {args.out}/summary.json, per_item.csv, scores.npz")
    return 0


if __name__ == "__main__":
    sys.exit(main())
