"""Test-wide setup. This module is imported before any test module, which is the
only place some of it can work.

Two problems are solved here.

**OpenMP.** faiss-cpu and torch each bundle an OpenMP runtime. On macOS both get
loaded into one process and, when a torch model is *constructed* off the main
thread — exactly what starlette's TestClient does, since it runs lifespan on a
portal thread — the duplicate runtimes segfault the interpreter. Allowing the
duplicate load and pinning to one thread makes the combination stable.
Production is unaffected: uvicorn runs lifespan on the main thread.

**Shared state.** `backend.database` builds its engine at import time, so a test
module setting DATABASE_URL in its own header has no effect once any other
module has imported it first — every module silently shares one database. That
matters because the FAISS index and the DB have to agree: `embedding_id` is
unique per table, so resetting the index without resetting the database makes
the next insert collide at position 0. The env is therefore set here, before any
import, and `fresh_state` clears both stores together.
"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_ROOT = Path(tempfile.mkdtemp(prefix="clf-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_ROOT / 'test.db'}"
os.environ["FAISS_INDEX_PATH"] = str(_ROOT / "index" / "index.bin")
os.environ["UPLOAD_DIR"] = str(_ROOT / "uploads")
os.environ["CLIP_DEVICE"] = "cpu"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("FERNET_KEY", "n_PKtQQN2tShgcWiCrKY-TphSwXctYvaB_0CCzUNh9M=")
# The auth suite never touches retrieval; skip the multi-second model load there.
os.environ.setdefault("PRELOAD_MODELS", "0")

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def fresh_state():
    """Empty the database and the vector index together.

    Never reset one without the other: `embedding_id` is unique per table, so an
    index that restarts at position 0 while old rows still hold 0 will fail the
    next insert with an IntegrityError.
    """
    from backend import faiss_store
    from backend.database import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    faiss_store.reset_index()
    yield
