"""Phase 4 checkpoint: match found -> claim initiated -> NLI passes -> security
releases -> incentive credited.

    uv run pytest tests/test_phase4_claims.py -v -s
"""

from __future__ import annotations

from pathlib import Path

import pytest


from fastapi.testclient import TestClient  # noqa: E402

from backend import clip_encoder, verification  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import Claim, CustodyAction, CustodyLog, User  # noqa: E402

pytestmark = pytest.mark.slow

FIXTURES = Path(__file__).parent / "fixtures" / "images"
PASSWORD = "passw0rd123"
SLUG = "umbrella"

SECRET = "there is a deep scratch across the handle and a blue sticker under the canopy"
# Scores 0.973 entailment. See test_verbose_true_claims_are_false_negatives for a
# correct description that this model rejects — the phrasing matters more than
# the truth of the claim.
TRUE_CLAIM = "it's got a scratch on the handle and there's a blue sticker underneath"
FALSE_CLAIM = "it is plain black with no marks, stickers or scratches anywhere"


@pytest.fixture(scope="module")
def client(fresh_state):
    if not (FIXTURES / f"{SLUG}.jpg").exists():
        pytest.skip("Run: uv run python tests/fixtures/download_fixtures.py")
    # Build both models on the main thread — see tests/conftest.py.
    clip_encoder.load_model()
    verification.load_model()
    with TestClient(app) as c:
        yield c


def _register(client, role, email):
    body = client.post(
        "/auth/register",
        json={"full_name": email, "email": email, "password": PASSWORD, "role": role},
    ).json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


@pytest.fixture(scope="module")
def actors(client):
    finder, finder_id = _register(client, "student", "finder@campus.edu")
    owner, owner_id = _register(client, "student", "owner@campus.edu")
    thief, thief_id = _register(client, "student", "thief@campus.edu")
    officer, officer_id = _register(client, "security", "officer@campus.edu")
    return {
        "finder": finder, "finder_id": finder_id,
        "owner": owner, "owner_id": owner_id,
        "thief": thief, "thief_id": thief_id,
        "officer": officer, "officer_id": officer_id,
    }


def _hand_in(client, actors):
    with open(FIXTURES / f"{SLUG}.jpg", "rb") as handle:
        response = client.post(
            "/items/found",
            headers=actors["finder"],
            files={"image": (f"{SLUG}.jpg", handle, "image/jpeg")},
            data={"location": "Main Gate Security Post"},
        )
    assert response.status_code == 201, response.text
    return response.json()["item"]["id"]


def _report_lost(client, headers, secret=SECRET):
    response = client.post(
        "/items/lost",
        headers=headers,
        data={
            "description": "an umbrella left by the entrance",
            "location_last_seen": "Library entrance",
            "private_descriptor": secret,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _credits(user_id: int) -> int:
    with SessionLocal() as db:
        return db.get(User, user_id).incentive_credits


# --------------------------------------------------------------------------- #
# The end-to-end checkpoint
# --------------------------------------------------------------------------- #
def test_full_journey_match_claim_verify_release_credit(client, actors, capsys):
    found_id = _hand_in(client, actors)

    # The officer takes physical custody.
    custody = client.post(
        f"/items/found/{found_id}/confirm-custody", headers=actors["officer"]
    )
    assert custody.status_code == 200
    assert custody.json()["status"] == "verified"

    # The owner reports it lost and sees it in their matches.
    report = _report_lost(client, actors["owner"])
    lost_id = report["item"]["id"]
    assert found_id in [m["item"]["id"] for m in report["matches"]]

    credits_before = _credits(actors["finder_id"])

    # Claim, with a description only the real owner could give.
    claim = client.post(
        "/claims/",
        headers=actors["owner"],
        json={
            "lost_item_id": lost_id,
            "found_item_id": found_id,
            "claimant_description": TRUE_CLAIM,
        },
    )
    assert claim.status_code == 201, claim.text
    receipt = claim.json()
    assert receipt["status"] == "approved"
    assert "nli_score" not in receipt, "claimants must not see the raw score"

    with capsys.disabled():
        with SessionLocal() as db:
            score = db.get(Claim, receipt["id"]).nli_score
        print(f"\n  entailment score {score:.4f}  (threshold {verification.ENTAILMENT_THRESHOLD})")

    # Officer releases the item.
    released = client.post(f"/claims/{receipt['id']}/release", headers=actors["officer"])
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "released"

    # Everything downstream moved.
    assert client.get(f"/items/found/{found_id}", headers=actors["officer"]).json()["status"] == "claimed"
    assert client.get(f"/items/lost/{lost_id}", headers=actors["owner"]).json()["status"] == "claimed"
    assert _credits(actors["finder_id"]) == credits_before + 1

    with SessionLocal() as db:
        actions = [
            log.action
            for log in db.query(CustodyLog).filter(CustodyLog.found_item_id == found_id).all()
        ]
    assert CustodyAction.confirmed in actions and CustodyAction.released in actions

    # The released item stops surfacing as a match for anyone else.
    later = _report_lost(client, actors["thief"])
    assert found_id not in [m["item"]["id"] for m in later["matches"]]


# --------------------------------------------------------------------------- #
# Verification behaviour
# --------------------------------------------------------------------------- #
def test_wrong_description_is_rejected(client, actors):
    found_id = _hand_in(client, actors)
    lost_id = _report_lost(client, actors["thief"])["item"]["id"]

    claim = client.post(
        "/claims/",
        headers=actors["thief"],
        json={
            "lost_item_id": lost_id,
            "found_item_id": found_id,
            "claimant_description": FALSE_CLAIM,
        },
    )
    assert claim.status_code == 201
    assert claim.json()["status"] == "rejected"

    # A rejected claim cannot be released.
    blocked = client.post(f"/claims/{claim.json()['id']}/release", headers=actors["officer"])
    assert blocked.status_code == 409


def test_no_impostor_claim_is_ever_approved(client, capsys):
    """Calibration table. The assertion is one-sided on purpose.

    Approving an impostor means handing someone's property to the wrong person,
    so every false case must be refused. Rejecting a true owner is a bad
    experience but not a security failure, and this model does produce such
    false negatives — see the test below.
    """
    cases = [
        ("true owner, natural", TRUE_CLAIM, True),
        ("true owner, terse", "there's a blue sticker under the canopy", True),
        ("wrong colour", "it has a red sticker on the handle", False),
        ("wrong item", "it is a leather wallet with my ID inside", False),
        ("vague guess", "it is mine, I lost it yesterday", False),
        ("direct contradiction", FALSE_CLAIM, False),
    ]
    with capsys.disabled():
        print(f"\n  {'claim':<24} {'fwd':>6} {'sym':>6}  verdict   expected")
        rows = []
        for label, text, should_pass in cases:
            forward = verification.verify_claim(SECRET, text)
            symmetric = verification.verify_claim_symmetric(SECRET, text)
            verdict = verification.passes(forward)
            rows.append((label, forward, verdict, should_pass))
            mark = "ok" if verdict == should_pass else "MISMATCH"
            print(
                f"  {label:<24} {forward:>6.3f} {symmetric:>6.3f}  "
                f"{'APPROVE' if verdict else 'reject ':<9} {mark}"
            )

    # Every impostor case must be refused. False approvals are the failure that
    # matters here — handing someone else's property to the wrong person.
    for label, score, verdict, should_pass in rows:
        if not should_pass:
            assert not verdict, f"impostor claim {label!r} was approved at {score:.3f}"


def test_verbose_true_claims_are_false_negatives(capsys):
    """A documented weakness, not a bug in our code.

    NLI asks whether the premise *entails* the hypothesis. Any detail the
    claimant supplies that the stored record does not contain makes the pair
    neutral rather than entailed — even when the claimant is the real owner.
    Here "I stuck a blue sticker" asserts who placed it, which the record never
    says, and the model returns neutral 0.826 / entailment 0.167.

    This test pins the behaviour so a future scoring change shows up as a
    deliberate decision rather than a silent drift.
    """
    verbose_but_true = "the handle is scratched and I stuck a blue sticker under the canopy"
    score = verification.verify_claim(SECRET, verbose_but_true)
    with capsys.disabled():
        print(f"\n  verbose true claim scores {score:.3f} -> rejected at threshold 0.7")
    assert score < verification.ENTAILMENT_THRESHOLD


def test_partial_guesses_currently_pass(capsys):
    """The other side of the same coin: naming one recorded attribute is enough.

    A claimant who says only "the handle has a scratch" is entailed by the full
    record and clears the threshold, without knowing about the sticker. Tightening
    this needs a coverage-style rule over the recorded clauses; forward entailment
    alone cannot express "you must know *everything* we recorded".
    """
    score = verification.verify_claim(SECRET, "the handle has a scratch")
    with capsys.disabled():
        print(f"  partial guess scores {score:.3f} -> approved at threshold 0.7")
    assert score >= verification.ENTAILMENT_THRESHOLD


def test_empty_descriptor_scores_zero():
    assert verification.verify_claim("", "anything at all") == 0.0
    assert verification.verify_claim("a real secret", "") == 0.0


# --------------------------------------------------------------------------- #
# Abuse resistance
# --------------------------------------------------------------------------- #
def test_attempts_are_capped(client, actors):
    from backend.routers.claims import MAX_ATTEMPTS_PER_ITEM

    found_id = _hand_in(client, actors)
    lost_id = _report_lost(client, actors["thief"])["item"]["id"]

    body = {
        "lost_item_id": lost_id,
        "found_item_id": found_id,
        "claimant_description": FALSE_CLAIM,
    }
    for attempt in range(MAX_ATTEMPTS_PER_ITEM):
        response = client.post("/claims/", headers=actors["thief"], json=body)
        assert response.status_code == 201, response.text
        assert response.json()["attempts_remaining"] == MAX_ATTEMPTS_PER_ITEM - attempt - 1

    # Guessing budget exhausted.
    assert client.post("/claims/", headers=actors["thief"], json=body).status_code == 429


def test_cannot_claim_against_someone_elses_lost_report(client, actors):
    found_id = _hand_in(client, actors)
    owners_lost_id = _report_lost(client, actors["owner"])["item"]["id"]

    response = client.post(
        "/claims/",
        headers=actors["thief"],
        json={
            "lost_item_id": owners_lost_id,
            "found_item_id": found_id,
            "claimant_description": TRUE_CLAIM,
        },
    )
    assert response.status_code == 403


def test_claim_score_is_staff_only(client, actors):
    found_id = _hand_in(client, actors)
    lost_id = _report_lost(client, actors["owner"])["item"]["id"]
    claim_id = client.post(
        "/claims/",
        headers=actors["owner"],
        json={
            "lost_item_id": lost_id,
            "found_item_id": found_id,
            "claimant_description": TRUE_CLAIM,
        },
    ).json()["id"]

    assert client.get("/claims/", headers=actors["owner"]).status_code == 403
    staff_view = client.get("/claims/", headers=actors["officer"])
    assert staff_view.status_code == 200
    row = next(c for c in staff_view.json() if c["id"] == claim_id)
    assert row["nli_score"] is not None

    # The claimant's own listing still withholds the score.
    mine = client.get("/claims/mine", headers=actors["owner"])
    assert mine.status_code == 200
    assert all("nli_score" not in c for c in mine.json())


def test_release_is_staff_only_and_idempotent(client, actors):
    found_id = _hand_in(client, actors)
    lost_id = _report_lost(client, actors["owner"])["item"]["id"]
    claim_id = client.post(
        "/claims/",
        headers=actors["owner"],
        json={
            "lost_item_id": lost_id,
            "found_item_id": found_id,
            "claimant_description": TRUE_CLAIM,
        },
    ).json()["id"]

    assert client.post(f"/claims/{claim_id}/release", headers=actors["owner"]).status_code == 403
    assert client.post(f"/claims/{claim_id}/release", headers=actors["officer"]).status_code == 200
    # Releasing twice must not credit the finder twice.
    assert client.post(f"/claims/{claim_id}/release", headers=actors["officer"]).status_code == 409


def test_verify_endpoint_is_staff_only(client, actors):
    found_id = _hand_in(client, actors)
    lost_id = _report_lost(client, actors["owner"])["item"]["id"]
    claim_id = client.post(
        "/claims/",
        headers=actors["owner"],
        json={
            "lost_item_id": lost_id,
            "found_item_id": found_id,
            "claimant_description": TRUE_CLAIM,
        },
    ).json()["id"]

    assert client.post(f"/claims/{claim_id}/verify", headers=actors["owner"]).status_code == 403
    rescored = client.post(f"/claims/{claim_id}/verify", headers=actors["officer"])
    assert rescored.status_code == 200
    assert 0.0 <= rescored.json()["nli_score"] <= 1.0
    assert rescored.json()["threshold"] == verification.ENTAILMENT_THRESHOLD


def test_unknown_ids_are_404(client, actors):
    assert client.post("/claims/99999/release", headers=actors["officer"]).status_code == 404
    assert client.post("/claims/99999/verify", headers=actors["officer"]).status_code == 404
    bad = client.post(
        "/claims/",
        headers=actors["owner"],
        json={"lost_item_id": 99999, "found_item_id": 99999, "claimant_description": "x"},
    )
    assert bad.status_code == 404
