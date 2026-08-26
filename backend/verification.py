"""Ownership verification via natural language inference.

When two people claim the same black umbrella, CLIP cannot separate them — the
photos are identical. What separates them is a detail only the owner knows, which
they recorded when filing the report. This module asks a pretrained NLI model
whether that stored detail (the *premise*) entails what the claimant says (the
*hypothesis*).

No fine-tuning: `cross-encoder/nli-distilroberta-base` is trained on SNLI/MNLI and
used off the shelf, in keeping with the project's zero-shot premise.
"""

from __future__ import annotations

import logging
import os
import threading

import numpy as np
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("NLI_MODEL", "cross-encoder/nli-distilroberta-base")
ENTAILMENT_THRESHOLD = float(os.getenv("NLI_THRESHOLD", "0.7"))

_model = None
_entailment_index: int | None = None
_load_lock = threading.Lock()


def load_model() -> None:
    """Idempotently load the cross-encoder. Called once at app startup."""
    global _model, _entailment_index

    if _model is not None:
        return

    with _load_lock:
        if _model is not None:
            return

        from sentence_transformers import CrossEncoder

        logger.info("Loading NLI cross-encoder %s", MODEL_NAME)
        model = CrossEncoder(MODEL_NAME)

        # Read the label order off the checkpoint rather than hardcoding it —
        # NLI models disagree about which logit is which.
        id2label = getattr(model.config, "id2label", None) or {}
        index = next(
            (int(i) for i, label in id2label.items() if str(label).lower() == "entailment"),
            None,
        )
        if index is None:
            raise RuntimeError(
                f"{MODEL_NAME} exposes no 'entailment' label; got {id2label}. "
                "Set NLI_MODEL to a three-way NLI checkpoint."
            )

        _model, _entailment_index = model, index
        logger.info("NLI ready — entailment is logit %d of %s", index, id2label)


def is_loaded() -> bool:
    return _model is not None


def preload_if_cached() -> bool:
    """Load the model only if it is already on disk; never touch the network.

    Startup must not block on a download. HF's transfer layer can stall for
    minutes rather than raising, so a plain try/except around ``load_model()``
    is not enough protection — forcing offline mode makes a missing checkpoint
    fail instantly instead of hanging.

    Note this flips ``huggingface_hub.constants.HF_HUB_OFFLINE`` rather than the
    environment variable: the library snapshots that variable into a module
    constant at import time, so setting the env var here would be ignored.
    """
    from huggingface_hub import constants

    previous = constants.HF_HUB_OFFLINE
    constants.HF_HUB_OFFLINE = True
    try:
        load_model()
        return True
    except Exception:
        logger.warning(
            "NLI checkpoint not in the local cache; claim verification is offline. "
            "Fetch it with: HF_HUB_DISABLE_XET=1 huggingface-cli download %s",
            MODEL_NAME,
        )
        return False
    finally:
        constants.HF_HUB_OFFLINE = previous


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exponentiated = np.exp(shifted)
    return exponentiated / exponentiated.sum(axis=-1, keepdims=True)


def verify_claims(pairs: list[tuple[str, str]]) -> list[float]:
    """Entailment probability for each ``(premise, hypothesis)`` pair."""
    if not pairs:
        return []
    if _model is None:
        load_model()

    raw = np.asarray(_model.predict(pairs), dtype=np.float64)
    if raw.ndim == 1:  # a single pair can come back squeezed
        raw = raw.reshape(1, -1)
    return [float(p) for p in _softmax(raw)[:, _entailment_index]]


def verify_claim(private_descriptor: str, claimant_description: str) -> float:
    """Score how strongly the stored private detail entails the claimant's account.

    Returns a probability in [0, 1]; compare against ``ENTAILMENT_THRESHOLD``.

    Direction matters. The stored descriptor is the premise and the claimant's
    text is the hypothesis, so the question is "given what the owner recorded,
    does the claimant's statement follow?" Note the asymmetry this creates: a
    vague claim is entailed by a specific premise more easily than the reverse,
    so a claimant who says little is treated generously. `verify_claim_symmetric`
    is the stricter alternative.
    """
    if not private_descriptor or not private_descriptor.strip():
        # Nothing on file to check against — cannot vouch for this claimant.
        logger.warning("verify_claim called with an empty private descriptor")
        return 0.0
    if not claimant_description or not claimant_description.strip():
        return 0.0

    return verify_claims([(private_descriptor, claimant_description)])[0]


def verify_claim_symmetric(private_descriptor: str, claimant_description: str) -> float:
    """Minimum of both entailment directions — each text must imply the other.

    Harder to pass by being vague. Not wired into the claim flow by default;
    exposed so Phase 6 can compare the two scoring rules on the same data.
    """
    if not (private_descriptor or "").strip() or not (claimant_description or "").strip():
        return 0.0
    forward, backward = verify_claims(
        [
            (private_descriptor, claimant_description),
            (claimant_description, private_descriptor),
        ]
    )
    return min(forward, backward)


def passes(score: float) -> bool:
    return score >= ENTAILMENT_THRESHOLD
