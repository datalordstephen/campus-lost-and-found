"""Phase 1 checkpoint: register student / security / admin, confirm JWT + role.

Runs against a throwaway SQLite file so it never touches campus_lost_found.db.
    uv run pytest tests/test_phase1_auth.py -v
"""

import os
import tempfile

import pytest

# Point the app at a temp DB before backend.database is imported anywhere.
_TMP_DB = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-phase-1")
os.environ.setdefault("FERNET_KEY", "n_PKtQQN2tShgcWiCrKY-TphSwXctYvaB_0CCzUNh9M=")

from fastapi import Depends  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.auth import decode_access_token, role_required  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import User, UserRole  # noqa: E402


@app.get("/_rbac_probe")
def _rbac_probe(user: User = Depends(role_required(UserRole.admin))):
    """Throwaway admin-only route, mounted so the RBAC factory can be exercised."""
    return {"ok": True}

ACCOUNTS = [
    ("student", "Ada Student", "ada@campus.edu"),
    ("security", "Ben Guard", "ben@campus.edu"),
    ("admin", "Cleo Admin", "cleo@campus.edu"),
]
PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("role,name,email", ACCOUNTS)
def test_register_returns_jwt_with_correct_role(client, role, name, email):
    r = client.post(
        "/auth/register",
        json={"full_name": name, "email": email, "password": PASSWORD, "role": role},
    )
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == role
    assert body["user"]["incentive_credits"] == 0
    assert "hashed_password" not in body["user"]

    claims = decode_access_token(body["access_token"])
    assert claims["role"] == role
    assert claims["sub"] == str(body["user"]["id"])


def test_duplicate_email_rejected(client):
    r = client.post(
        "/auth/register",
        json={"full_name": "Imposter", "email": "ada@campus.edu", "password": PASSWORD},
    )
    assert r.status_code == 409


def test_login_and_me_roundtrip(client):
    r = client.post("/auth/login", json={"email": "ben@campus.edu", "password": PASSWORD})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "ben@campus.edu"
    assert me.json()["role"] == "security"


def test_wrong_password_and_missing_token_rejected(client):
    assert (
        client.post(
            "/auth/login", json={"email": "ben@campus.edu", "password": "wrong-password"}
        ).status_code
        == 401
    )
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_role_required_blocks_wrong_role(client):
    def token_for(email):
        return client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()[
            "access_token"
        ]

    student = {"Authorization": f"Bearer {token_for('ada@campus.edu')}"}
    admin = {"Authorization": f"Bearer {token_for('cleo@campus.edu')}"}

    assert client.get("/_rbac_probe", headers=student).status_code == 403
    assert client.get("/_rbac_probe", headers=admin).status_code == 200


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
