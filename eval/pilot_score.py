"""Score the ownership-verification pilot and report FAR / FRR.

Input: two CSV files exported from the pilot sheet.
  items.csv   item_id, private_detail_1, private_detail_2 (optional, may be blank)
  claims.csv  claim_id, item_id, claimant_code, kind (genuine | impostor), claim_text

Three scoring rules are compared on the same claims:
  forward     P(entailment | premise = stored detail, hypothesis = whole claim).
              This is the rule the system uses today.
  two_way     min(forward, P(entailment | premise = claim, hypothesis = detail)).
  sentence    The claim is split into sentences. For each stored detail, take the
              highest entailment over the claim's sentences; the claim's score is the
              lowest of those over the stored details (so with two details, both must
              be matched). If any sentence contradicts a stored detail with probability
              above --contradiction, the score is set to 0.
              This is the proposed fix for verbose genuine owners.

Outputs (in --out):
  pilot_scores.csv     one row per claim with all three scores
  pilot_far_frr.csv    FAR, FRR and catch rate for every rule at thresholds 0.05..0.95
  pilot_summary.txt    counts, results at tau = 0.7, the equal-error point per rule,
                       with Wilson 95% intervals

FAR = impostor claims approved / impostor claims.
FRR = genuine claims rejected / genuine claims.
Catch rate = 1 - FAR: the share of impostors who identified the item but were stopped.

Usage:
  uv run python eval/pilot_score.py --items items.csv --claims claims.csv --out eval/results/pilot
"""
import argparse
import csv
import math
import os
import re

MODEL = "cross-encoder/nli-distilroberta-base"


def load_nli(model_name=MODEL):
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(model_name, device="cpu")
    labels = [model.config.id2label[i].lower() for i in range(len(model.config.id2label))]
    ent, con = labels.index("entailment"), labels.index("contradiction")

    def nli(pairs):
        """pairs: list of (premise, hypothesis) -> list of (p_entail, p_contradict)."""
        if not pairs:
            return []
        probs = model.predict(pairs, apply_softmax=True, convert_to_numpy=True)
        return [(float(p[ent]), float(p[con])) for p in probs]

    return nli


def sentences(text):
    parts = [p.strip() for p in re.split(r"(?<=[.!?;])\s+|\n+", text.strip()) if p.strip()]
    return parts or [text.strip()]


def score_claim(nli, details, claim, contradiction_cut):
    fwd = min(nli([(d, claim)])[0][0] for d in details)
    back = min(nli([(claim, d)])[0][0] for d in details)
    sents = sentences(claim)
    per_detail = []
    contradicted = False
    for d in details:
        res = nli([(d, s) for s in sents])
        per_detail.append(max(r[0] for r in res))
        if any(r[1] > contradiction_cut for r in res):
            contradicted = True
    sent = 0.0 if contradicted else min(per_detail)
    return {"forward": fwd, "two_way": min(fwd, back), "sentence": sent}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


def rates(rows, rule, tau):
    gen = [r for r in rows if r["kind"] == "genuine"]
    imp = [r for r in rows if r["kind"] == "impostor"]
    fr = sum(r[rule] < tau for r in gen)
    fa = sum(r[rule] >= tau for r in imp)
    return fa, len(imp), fr, len(gen)


def main(argv=None, nli=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--claims", required=True)
    ap.add_argument("--out", default="eval/results/pilot")
    ap.add_argument("--tau", type=float, default=0.7)
    ap.add_argument("--contradiction", type=float, default=0.5)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)

    items = {}
    for r in csv.DictReader(open(a.items, newline="", encoding="utf-8-sig")):
        details = [r.get("private_detail_1", "").strip(), r.get("private_detail_2", "").strip()]
        details = [d for d in details if d]
        if details:
            items[r["item_id"].strip()] = details
    claims = [r for r in csv.DictReader(open(a.claims, newline="", encoding="utf-8-sig")) if r.get("claim_text", "").strip()]
    for c in claims:
        c["kind"] = c["kind"].strip().lower()
        assert c["kind"] in ("genuine", "impostor"), f"bad kind in claim {c.get('claim_id')}: {c['kind']}"
        assert c["item_id"].strip() in items, f"claim {c.get('claim_id')} refers to unknown item {c['item_id']}"

    nli = nli or load_nli()
    rows = []
    for c in claims:
        s = score_claim(nli, items[c["item_id"].strip()], c["claim_text"].strip(), a.contradiction)
        rows.append({"claim_id": c.get("claim_id", ""), "item_id": c["item_id"].strip(), "claimant_code": c.get("claimant_code", ""),
                     "kind": c["kind"], "n_details": len(items[c["item_id"].strip()]), **{k: round(v, 4) for k, v in s.items()},
                     "claim_text": c["claim_text"].strip()})

    rules = ["forward", "two_way", "sentence"]
    with open(os.path.join(a.out, "pilot_scores.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    taus = [round(0.05 * i, 2) for i in range(1, 20)]
    with open(os.path.join(a.out, "pilot_far_frr.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rule", "threshold", "FAR", "FRR", "catch_rate", "false_accepts", "impostor_claims", "false_rejects", "genuine_claims"])
        for rule in rules:
            for t in taus:
                fa, ni, fr, ng = rates(rows, rule, t)
                w.writerow([rule, t, round(fa / ni, 3) if ni else "", round(fr / ng, 3) if ng else "", round(1 - fa / ni, 3) if ni else "", fa, ni, fr, ng])

    gen = sum(r["kind"] == "genuine" for r in rows)
    imp = sum(r["kind"] == "impostor" for r in rows)
    lines = [f"Claims: {len(rows)} ({gen} genuine, {imp} impostor) on {len({r['item_id'] for r in rows})} items; "
             f"{len({r['claimant_code'] for r in rows if r['claimant_code']})} distinct claimants.", ""]
    lines.append(f"At tau = {a.tau}:")
    for rule in rules:
        fa, ni, fr, ng = rates(rows, rule, a.tau)
        lo1, hi1 = wilson(fa, ni)
        lo2, hi2 = wilson(fr, ng)
        lines.append(f"  {rule:<9} FAR {fa}/{ni} = {fa / ni:.3f} [95% CI {lo1:.2f}, {hi1:.2f}]   "
                     f"FRR {fr}/{ng} = {fr / ng:.3f} [95% CI {lo2:.2f}, {hi2:.2f}]   catch rate {1 - fa / ni:.3f}")
    lines += ["", "Equal-error point (threshold where FAR and FRR are closest):"]
    for rule in rules:
        best = min(taus, key=lambda t: abs(rates(rows, rule, t)[0] / imp - rates(rows, rule, t)[2] / gen))
        fa, ni, fr, ng = rates(rows, rule, best)
        lines.append(f"  {rule:<9} tau {best:.2f}: FAR {fa / ni:.3f}, FRR {fr / ng:.3f}")
    open(os.path.join(a.out, "pilot_summary.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return rows


if __name__ == "__main__":
    main()
