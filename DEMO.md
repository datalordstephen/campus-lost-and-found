# Demoing to your supervisor

Written for you, to run from. The claim you are demonstrating is the project
title: **a lost item can be found by describing it, matched against photographs
nobody labelled, by a model that was never trained on campus data** — and that
when two people want the same umbrella, a second model decides which one owns it.

Everything below has been run end to end on this machine.

---

## 20 minutes before

Reset to a clean, known state. Stale data is the thing that makes a demo look
untrustworthy — a shelf full of duplicate umbrellas from testing invites exactly
the wrong question.

```bash
# 1. stop both servers (Ctrl-C in each terminal), then:
uv run python scripts/demo.py reset

# 2. start them again — two terminals, from the repo root
uv run uvicorn backend.main:app --reload
cd frontend && npm run dev

# 3. seed the demo shelf
uv run python scripts/seed_demo.py

# 4. prove it is ready
uv run python scripts/demo.py check
```

`check` must end on **"Ready."** It verifies both servers, that both model
checkpoints are loaded, that the app can reach the API, that data exists, and —
the important one — it **runs a real retrieval query** so the first search your
supervisor sees is not the one that pays for warming the caches. If it reports
the query took more than 3 seconds, run it again.

Open **http://localhost:5173** — `localhost`, not `127.0.0.1`. Vite binds
IPv6-only and the numeric address will refuse the connection.

Accounts (password `passw0rd123` for all four):

| | who | for |
|---|---|---|
| `sam@campus.edu` | student | filed the lost reports — **start here** |
| `priya@campus.edu` | student | handed the items in |
| `otto@campus.edu` | security | the property desk |
| `ada@campus.edu` | admin | statistics and accounts |

Have a second browser profile or a private window open, signed in as `otto@`.
Switching roles by signing in and out mid-demo wastes a minute each time and
breaks the thread.

---

## The demo, in order

### 1. Lead with the mechanism, not the login page

Sign in as **sam@**, go to **Report lost**, and type a description in your own
words — do not read one out. Something like:

> *a black umbrella with a wooden handle*
> last seen: *Library entrance*
> private detail: *a deep scratch across the handle and a blue sticker under the canopy*

Submit. The matches come back in the same response.

**What to say while it runs:** nobody tagged, categorised or labelled any of
those photographs. The only thing in the index is a 512-dimension vector per
image from OpenCLIP, and the description is turned into a vector in the same
space. The match is a dot product.

**What to point at:** the match seam on each result — the marker's position is
that candidate's strength relative to the others returned, and the raw cosine
is printed beside it. Say the number out loud: *0.29 is a strong match here, not
a weak one.* Raw CLIP cosine for a correct pair sits around 0.22–0.33 against a
bare photograph. That is exactly why the interface does not print it as a
percentage, and it is a good thing to be seen to have thought about.

### 2. The private detail — the part that is actually hard

Claim the top match. The modal asks for the detail recorded at report time.
Type a **true but reworded** version:

> *it's got a scratch on the handle and there's a blue sticker underneath*

It is approved.

**What to say:** CLIP cannot separate two identical black umbrellas, because the
photographs are identical. What separates them is something only the owner
knows. The stored detail is encrypted at rest and is never sent to any client;
it is decrypted only inside the verification call, as the premise of a natural
language inference check. Entailment above 0.7 approves.

Then **deliberately show the failure**. Sign out, sign in as **priya@**, and try
to claim the same umbrella with a plausible guess:

> *it's plain black, no marks on it*

Rejected, with tries remaining shown. Across every impostor case tested there
were **zero false approvals**.

### 3. The desk closes the loop

Sign in as **otto@** → **Claims**. The entailment score is here and only here —
the claimant never sees it, because handing someone the number turns
verification into a guessing game where you tweak the wording until it clears
the line. Note the 70% threshold marked on the bar.

Release the item. Then **Incoming** shows it as claimed, and priya's return
credit has gone up — the incentive for handing things in rather than walking
past them.

### 4. The numbers

Sign in as **ada@** for the overview, then go to the terminal — the evaluation
is the part a supervisor will actually weigh.

```bash
uv run python eval/evaluate.py
```

200 image/caption pairs from COCO val2017, filtered to losable object
categories. Each image carries two independent human captions: one plays the
lost report, the other the finder's description. So the TF-IDF baseline searches
*text against text* while CLIP searches *text against the photograph*.

| | R@1 | R@3 | R@5 | MRR |
|---|---|---|---|---|
| **CLIP, zero-shot** | **0.625** | **0.865** | **0.950** | **0.757** |
| TF-IDF keyword baseline | 0.315 | 0.455 | 0.605 | 0.439 |

**+31 points at R@1, roughly double the baseline, with no campus training data.**
Paired bootstrap, p < 0.0001.

---

## Questions you should expect, and honest answers

**"Isn't COCO much easier than real campus photos?"**
Yes, and say so before they do. COCO images are well-lit and centred; a real
submission is a phone snap on a cluttered desk. **0.625 is an upper bound.**
This is the single strongest thing you can say, because it shows you know what
your own number is worth — and the next step is already written down in
`TODO.md`: 30–50 photos taken in situ, with descriptions written by someone
other than you.

**"Why not just fine-tune on lost-and-found data?"**
There is no such labelled dataset, and a campus deployment starts with zero
examples. Zero-shot is what makes it deployable on day one. Fine-tuning is the
obvious follow-on once a deployment has produced its own matched pairs.

**"What if the model is wrong?"**
It is designed to be. Retrieval returns a top-5 shortlist, not a decision;
a human picks. Ownership is settled by the NLI check and a security officer,
neither of which trusts the retrieval score at all.

**"Does adding a description to a found item help?"**
No — and this is a real finding from my own evaluation, not a guess. Averaging
the photograph with the finder's description drops R@5 from 0.950 to 0.885. It
is a known defect in the current code, logged in `TODO.md` as item 2.

**"Where does it fail?"**
Two places, both measured and both pinned by tests so they cannot drift:
- Realistic phrasing costs accuracy. The same 10 photos score 10/10 top-1
  against clean prompts, 8/10 against sentences a stressed student would type
  (*"my bicycle taken from the rack outside"*). The circumstantial clause pulls
  the embedding away from the object.
- The NLI check fails in both directions: a truthful owner who adds detail the
  record does not contain gets rejected (0.167), and someone who guesses one
  recorded attribute passes (0.962). No impostor was ever approved, but these
  are real and `TODO.md` item 4 is the plan.

Volunteering these wins more credit than being caught by them.

---

## If something breaks

| symptom | cause | fix |
|---|---|---|
| Browser refuses to connect | used `127.0.0.1` | use `localhost:5173` |
| First search hangs ~10s | models loading | you skipped `demo.py check` |
| Claim returns 503 | NLI checkpoint missing | `HF_HUB_DISABLE_XET=1 uv run huggingface-cli download cross-encoder/nli-distilroberta-base` |
| Cards show "no file" | `uploads/` cleared, rows remain | `uv run python scripts/demo.py reset`, reseed |
| A live description misses | realistic phrasing | **do not apologise** — it is the finding in the table above |

If a search misses in front of your supervisor, the recovery line is: *that is
the phrasing effect I mentioned — the circumstantial clause pulls the embedding
away from the object, and it is measured in the evaluation.* A failure you
predicted is evidence you understand the system.
