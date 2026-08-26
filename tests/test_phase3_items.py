"""Phase 3 checkpoint: submit a found photo, report a matching lost item, and
confirm top-k retrieval surfaces the right one.

    uv run pytest tests/test_phase3_items.py -v -s
"""

from __future__ import annotations

from pathlib import Path

import pytest


from fastapi.testclient import TestClient  # noqa: E402

from backend import clip_encoder, faiss_store  # noqa: E402
from backend.auth import decrypt_text  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import LostItem  # noqa: E402

pytestmark = pytest.mark.slow

FIXTURES = Path(__file__).parent / "fixtures" / "images"
PASSWORD = "passw0rd123"

# The photo handed in, and the words a student would type having lost it.
CATALOGUE = {
    "backpack": "the backpack I left in the lecture hall",
    "bicycle": "my bicycle taken from the rack outside",
    "headphones": "a pair of headphones left on a library desk",
    "keys": "my keys on a keyring",
    "laptop": "the laptop computer I left in the study room",
    "umbrella": "an umbrella left by the entrance",
    "wallet": "my leather wallet",
    "water_bottle": "my reusable water bottle",
    "wristwatch": "the wristwatch I took off at the gym",
    "eyeglasses": "my glasses in a case",
}


@pytest.fixture(scope="module")
def slugs():
    available = sorted(s for s in CATALOGUE if (FIXTURES / f"{s}.jpg").exists())
    if len(available) < 5:
        pytest.skip("Run: uv run python tests/fixtures/download_fixtures.py")
    return available


@pytest.fixture(scope="module")
def client(fresh_state):
    # Build the CLIP model here, on the main thread. TestClient runs lifespan on
    # a portal thread, and constructing torch modules there while faiss is
    # loaded segfaults on macOS (see tests/conftest.py). load_model() is
    # idempotent, so the app's own startup call becomes a no-op.
    clip_encoder.load_model()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def actors(client):
    """One student, one security officer, one admin — returns auth headers."""
    headers = {}
    for role in ("student", "security", "admin"):
        response = client.post(
            "/auth/register",
            json={
                "full_name": f"{role.title()} One",
                "email": f"{role}@campus.edu",
                "password": PASSWORD,
                "role": role,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        headers[role] = {"Authorization": f"Bearer {body['access_token']}"}
        headers[f"{role}_id"] = body["user"]["id"]
    return headers


def _submit_found(client, headers, slug, location="Main Gate Security Post", **extra):
    with open(FIXTURES / f"{slug}.jpg", "rb") as handle:
        return client.post(
            "/items/found",
            headers=headers,
            files={"image": (f"{slug}.jpg", handle, "image/jpeg")},
            data={"location": location, **extra},
        )


def _report_lost(client, headers, description, **extra):
    return client.post(
        "/items/lost",
        headers=headers,
        data={
            "description": description,
            "location_last_seen": "Library",
            "private_descriptor": "there is a blue sticker on the underside",
            **extra,
        },
    )


# --------------------------------------------------------------------------- #
# The checkpoint
# --------------------------------------------------------------------------- #
def test_lost_report_retrieves_the_matching_found_photo(client, actors, slugs, capsys):
    """Hand in every photo, then report each item lost and check the top match."""
    found_ids = {}
    for slug in slugs:
        response = _submit_found(client, actors["student"], slug)
        assert response.status_code == 201, response.text
        found_ids[response.json()["item"]["id"]] = slug

    assert faiss_store.size(faiss_store.FOUND) == len(slugs)

    hits_at_1 = hits_at_3 = 0
    with capsys.disabled():
        print(f"\n  {'lost report':<48} {'score':>7} rank  top match")
        for slug in slugs:
            response = _report_lost(client, actors["student"], CATALOGUE[slug])
            assert response.status_code == 201, response.text
            matches = response.json()["matches"]
            assert matches, "no matches returned"

            ranked = [found_ids[m["item"]["id"]] for m in matches]
            rank = ranked.index(slug) + 1 if slug in ranked else 99
            hits_at_1 += rank == 1
            hits_at_3 += rank <= 3
            flag = "" if rank == 1 else "   <-- MISS"
            print(
                f"  {CATALOGUE[slug][:46]:<48} {matches[0]['score']:>7.4f} {rank:>4}  "
                f"{ranked[0]}{flag}"
            )

        n = len(slugs)
        print(f"\n  P@1 {hits_at_1}/{n}   P@3 {hits_at_3}/{n}")

    assert hits_at_1 >= 0.7 * len(slugs), "end-to-end top-1 retrieval below 70%"
    assert hits_at_3 >= 0.9 * len(slugs)


def test_matches_endpoint_agrees_with_submission_response(client, actors, slugs):
    response = _report_lost(client, actors["student"], CATALOGUE[slugs[0]])
    lost_id = response.json()["item"]["id"]
    inline = response.json()["matches"]

    later = client.get(f"/matches/{lost_id}", headers=actors["student"])
    assert later.status_code == 200, later.text
    fetched = later.json()

    # GET /matches reuses the stored vector; it must reproduce POST's ranking.
    assert [m["item"]["id"] for m in fetched] == [m["item"]["id"] for m in inline]
    assert fetched[0]["score"] == pytest.approx(inline[0]["score"], abs=1e-5)


def test_matches_for_found_item_returns_lost_reports(client, actors, slugs):
    response = _submit_found(client, actors["student"], slugs[0])
    found_id = response.json()["item"]["id"]

    result = client.get(f"/matches/found/{found_id}", headers=actors["security"])
    assert result.status_code == 200, result.text
    assert result.json(), "expected at least one open lost report to match"
    assert all("location_last_seen" in m["item"] for m in result.json())


def test_k_parameter_bounds_result_count(client, actors, slugs):
    response = _report_lost(client, actors["student"], CATALOGUE[slugs[0]] + " ", k=None)
    lost_id = response.json()["item"]["id"]

    assert len(client.get(f"/matches/{lost_id}?k=1", headers=actors["student"]).json()) == 1
    assert len(client.get(f"/matches/{lost_id}?k=3", headers=actors["student"]).json()) == 3
    assert client.get(f"/matches/{lost_id}?k=0", headers=actors["student"]).status_code == 422
    assert client.get(f"/matches/{lost_id}?k=99", headers=actors["student"]).status_code == 422


# --------------------------------------------------------------------------- #
# Storage, privacy, RBAC
# --------------------------------------------------------------------------- #
def test_upload_is_content_hashed_and_deduplicated(client, actors, slugs):
    first = _submit_found(client, actors["student"], slugs[0])
    second = _submit_found(client, actors["student"], slugs[0])

    path_one = Path(first.json()["item"]["image_path"])
    path_two = Path(second.json()["item"]["image_path"])

    assert path_one == path_two, "identical bytes should land on one file"
    assert path_one.exists()
    assert path_one.stem != slugs[0], "filename must not echo the client-supplied name"
    assert len(path_one.stem) == 32  # sha256 prefix
    # Two distinct rows, one file on disk.
    assert first.json()["item"]["id"] != second.json()["item"]["id"]


def test_private_descriptor_is_encrypted_and_never_returned(client, actors):
    secret = "engraved with the initials A.O. on the back"
    response = _report_lost(
        client, actors["student"], "a silver pen", private_descriptor=secret
    )
    assert response.status_code == 201
    lost_id = response.json()["item"]["id"]

    assert secret not in response.text
    assert "private_descriptor" not in response.json()["item"]

    listing = client.get("/items/lost", headers=actors["student"])
    assert secret not in listing.text

    with SessionLocal() as db:
        stored = db.get(LostItem, lost_id).private_descriptor
        assert stored != secret            # ciphertext at rest
        assert secret not in stored
        assert decrypt_text(stored) == secret  # but recoverable for NLI in Phase 4


def test_rejects_non_image_and_oversized_uploads(client, actors):
    bad = client.post(
        "/items/found",
        headers=actors["student"],
        files={"image": ("notes.txt", b"this is not an image", "text/plain")},
        data={"location": "Main Gate"},
    )
    assert bad.status_code == 415

    # Correct content-type header, but the bytes are not an image.
    liar = client.post(
        "/items/found",
        headers=actors["student"],
        files={"image": ("fake.jpg", b"GIF89a not really", "image/jpeg")},
        data={"location": "Main Gate"},
    )
    assert liar.status_code == 400


def test_found_listing_is_staff_only(client, actors):
    assert client.get("/items/found", headers=actors["student"]).status_code == 403
    assert client.get("/items/found", headers=actors["security"]).status_code == 200
    assert client.get("/items/found", headers=actors["admin"]).status_code == 200
    assert client.get("/items/found").status_code == 401


def test_student_cannot_read_another_students_matches(client, actors, slugs):
    other = client.post(
        "/auth/register",
        json={
            "full_name": "Other Student",
            "email": "other@campus.edu",
            "password": PASSWORD,
            "role": "student",
        },
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    lost_id = _report_lost(client, actors["student"], CATALOGUE[slugs[0]]).json()["item"]["id"]

    assert client.get(f"/matches/{lost_id}", headers=other_headers).status_code == 403
    assert client.get(f"/matches/{lost_id}", headers=actors["student"]).status_code == 200
    # Staff may review any report.
    assert client.get(f"/matches/{lost_id}", headers=actors["security"]).status_code == 200


def test_matches_for_found_item_is_staff_only(client, actors, slugs):
    found_id = _submit_found(client, actors["student"], slugs[0]).json()["item"]["id"]
    assert client.get(f"/matches/found/{found_id}", headers=actors["student"]).status_code == 403
    assert client.get(f"/matches/found/{found_id}", headers=actors["security"]).status_code == 200


def test_unknown_ids_are_404(client, actors):
    assert client.get("/matches/99999", headers=actors["student"]).status_code == 404
    assert client.get("/matches/found/99999", headers=actors["security"]).status_code == 404


def test_security_post_id_must_reference_a_security_officer(client, actors, slugs):
    ok = _submit_found(
        client, actors["student"], slugs[0], security_post_id=str(actors["security_id"])
    )
    assert ok.status_code == 201
    assert ok.json()["item"]["security_post_id"] == actors["security_id"]

    bad = _submit_found(
        client, actors["student"], slugs[0], security_post_id=str(actors["admin_id"])
    )
    assert bad.status_code == 400


def test_lost_report_accepts_an_optional_image(client, actors, slugs):
    with open(FIXTURES / f"{slugs[0]}.jpg", "rb") as handle:
        response = client.post(
            "/items/lost",
            headers=actors["student"],
            files={"image": (f"{slugs[0]}.jpg", handle, "image/jpeg")},
            data={
                "description": CATALOGUE[slugs[0]],
                "location_last_seen": "Cafeteria",
                "private_descriptor": "a dent on the left corner",
            },
        )
    assert response.status_code == 201, response.text
    assert response.json()["item"]["image_path"] is not None
    assert response.json()["matches"]


def test_db_and_faiss_stay_in_step(client, actors, slugs):
    """Every indexed row must have an embedding_id that resolves in FAISS."""
    with SessionLocal() as db:
        rows = db.query(LostItem).all()
        assert rows
        for row in rows:
            assert row.embedding_id is not None
            vector = faiss_store.get_embedding(faiss_store.LOST, row.embedding_id)
            assert vector is not None and vector.shape == (512,)
