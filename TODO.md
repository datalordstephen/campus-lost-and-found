# TODO

All six SPEC.md phases are complete and 55 tests pass. These are the things
worth doing next, ordered by what I'd tackle first. Each says why it matters and
where the evidence for it is, so none of it needs re-deriving later.

---

## 1. Campus photo test set — the number that defends the thesis

**Status:** not started. Needs you; I can do everything except take the photos.

The Phase 6 result (CLIP R@1 0.625 vs TF-IDF 0.315) is measured on COCO
val2017 — well-lit, centred, product-style photographs. Real input is a phone
snap of a black umbrella on a desk under fluorescent light. **0.625 is an upper
bound**, and it is the first thing an examiner will push on.

What's needed:
- 30–50 photos taken on a phone, in situ, of the kind of objects that actually
  get handed in.
- Descriptions written by **someone other than you** — otherwise it measures how
  well you describe your own photos.
- Run through the existing harness; `eval/evaluate.py` needs only a manifest in
  the same shape as `eval/data/testset.json`.

I'd write the capture protocol, the ingest script, and the manifest builder.

---

## 2. Found items are indexed with a worse embedding than they could be

**Status:** confirmed defect, not fixed. ~20 minutes.

`backend/routers/items.py` calls `encode_combined(description, image_path)` for
every found item submitted with text. My own Phase 6 evaluation says that is the
wrong choice:

| indexed as | R@1 | R@3 | R@5 |
|---|---|---|---|
| photograph alone | 0.625 | **0.865** | **0.950** |
| photograph averaged with description | 0.630 | 0.815 | 0.885 |

A weak or generic finder description drags the vector away from the image, so
**adding a description currently makes an item harder to find** — the opposite
of what the UI promises ("Words sharpen the match").

Options, in order of appeal:
- Index the image alone, and keep the description for display and for a future
  keyword filter.
- Index both vectors separately and take the better score.
- Weight the average toward the image and re-measure.

Whichever, add a regression test to `tests/test_phase6_evaluation.py` asserting
the chosen strategy beats the alternatives on the test set.

---

## 3. Match notifications were specified but never built

**Status:** not started.

SPEC.md, found-item flow step 4: *"Matched students notified via in-app
dashboard."* There is no notification anywhere in the system. A student files a
report, and if a matching item is handed in an hour later, nothing tells them —
they have to remember to go back and open My reports.

Minimum useful version:
- On `POST /items/found`, record matches above a threshold against open lost
  reports.
- A `GET /notifications` endpoint, or a count on `GET /auth/me`.
- A badge on the sidebar's "My reports", and a line at the top of that section.

Worth deciding first whether a notification is a stored row (auditable, survives
restarts) or computed on read (no schema change, no state to keep in step). The
stored row is probably right given the existing `CustodyLog` precedent.

---

## 4. NLI ownership verification fails in both directions

**Status:** characterised and pinned by tests, not solved. Research-grade.

Measured on `cross-encoder/nli-distilroberta-base`, premise = stored private
descriptor, hypothesis = claimant's text:

| claim | entailment | verdict |
|---|---|---|
| true owner, natural phrasing | 0.973 | correct |
| **true owner, adds detail not in the record** | **0.167** | **wrongly rejected** |
| **guesses one recorded attribute only** | **0.962** | **wrongly approved** |
| every impostor case tested | ≤ 0.004 | correct |

The good news is there were **no false approvals** on any genuine impostor. The
two failures are: NLI calls anything the claimant adds "neutral" rather than
entailed, and forward entailment cannot express "you must know *everything* we
recorded".

Both behaviours are locked in by `test_verbose_true_claims_are_false_negatives`
and `test_partial_guesses_currently_pass`, so a scoring change shows up as a
deliberate decision rather than silent drift.

Directions: clause-level coverage over the recorded descriptor (my quick probe
scored no better than plain entailment — the naive sentence splitter was the
weak point, not the idea); a larger NLI checkpoint; requiring both entailment
and a contradiction floor. `verification.verify_claim_symmetric` already exists
for comparison and is not wired into the flow.

---

## 5. Registration lets anyone become an admin

**Status:** known, deliberate for the demo.

`POST /auth/register` honours the `role` field from the request body, which is
how all three account types get provisioned without a seeding script. Before
this is exposed to anyone, force `student` there and promote staff through
`PATCH /admin/users/{id}/role`, which already exists and is already admin-only.

---

## Smaller things

- **`eval/build_dataset.py` category balance.** The 200-pair set is 25 laptops,
  25 bowls, 25 teddy bears and only 1 fork. The per-category cap works but the
  tail is thin; a stratified sample would be more defensible.
- **Vite binds IPv6-only**, so `http://127.0.0.1:5173` refuses while
  `http://localhost:5173` works. Documented in the README; could be pinned with
  `server.host`.
- **`uploads/` and the database can drift apart.** Clearing one without the
  other leaves rows pointing at missing files. The UI now degrades gracefully to
  a "no file" placeholder, but a `scripts/doctor.py` that reports orphans in
  either direction would save time.
- **passlib pulls stdlib `crypt`**, removed in Python 3.13. `.python-version`
  pins 3.11, so this is fine until an upgrade.
