"""OpenCLIP wrapper — the zero-shot half of the system.

One shared ViT-B-32 (LAION-2B) model produces 512-dim L2-normalised embeddings for
both photographs and free text into the same space, so a lost-item *description*
can be matched against a found-item *photo* with a plain dot product. No
domain-specific training data is involved anywhere.

The model is loaded once, at app startup (see ``backend.main.lifespan``). Never
call ``load_model()`` per request — it costs seconds and hundreds of MB.
"""

from __future__ import annotations

import logging
import os
import threading

import numpy as np
import torch
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("CLIP_MODEL", "ViT-B-32")
PRETRAINED = os.getenv("CLIP_PRETRAINED", "laion2b_s34b_b79k")
EMBED_DIM = 512

_model = None
_preprocess = None
_tokenizer = None
_device: torch.device | None = None
_load_lock = threading.Lock()


def _resolve_device() -> torch.device:
    """CPU by default.

    MPS is measurably faster but its reductions are not bit-reproducible, which
    would make the Phase 6 evaluation numbers wobble between runs. Opt in with
    ``CLIP_DEVICE=mps`` when you want throughput over reproducibility.
    """
    requested = os.getenv("CLIP_DEVICE", "cpu").lower()
    if requested == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    if requested == "mps" and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def load_model() -> None:
    """Idempotently load the model, preprocessing transform and tokenizer."""
    global _model, _preprocess, _tokenizer, _device

    if _model is not None:
        return

    with _load_lock:
        if _model is not None:  # another thread won the race
            return

        import open_clip  # imported lazily so `import backend.models` stays cheap

        device = _resolve_device()
        logger.info("Loading OpenCLIP %s (%s) on %s", MODEL_NAME, PRETRAINED, device)

        model, _, preprocess = open_clip.create_model_and_transforms(
            MODEL_NAME, pretrained=PRETRAINED
        )
        model.eval().to(device)
        for param in model.parameters():
            param.requires_grad_(False)

        _model, _preprocess, _tokenizer, _device = (
            model,
            preprocess,
            open_clip.get_tokenizer(MODEL_NAME),
            device,
        )
        logger.info("OpenCLIP ready")


def is_loaded() -> bool:
    return _model is not None


def _require_model():
    if _model is None:
        load_model()
    return _model, _preprocess, _tokenizer, _device


def _normalise(matrix: torch.Tensor) -> np.ndarray:
    """L2-normalise row-wise and return float32 — the layout FAISS IndexFlatIP wants."""
    matrix = matrix / matrix.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    return matrix.detach().cpu().numpy().astype(np.float32)


# --------------------------------------------------------------------------- #
# Batch encoders (used by the eval harness and by the single-item helpers)
# --------------------------------------------------------------------------- #
def encode_images(image_paths: list[str], batch_size: int = 32) -> np.ndarray:
    """Encode N images -> (N, 512) float32, L2-normalised."""
    model, preprocess, _, device = _require_model()
    if not image_paths:
        return np.empty((0, EMBED_DIM), dtype=np.float32)

    out: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(image_paths), batch_size):
            chunk = image_paths[start : start + batch_size]
            tensors = []
            for path in chunk:
                with Image.open(path) as img:
                    # RGBA/greyscale/EXIF-rotated phone photos all land here.
                    tensors.append(preprocess(img.convert("RGB")))
            batch = torch.stack(tensors).to(device)
            out.append(_normalise(model.encode_image(batch)))
    return np.concatenate(out, axis=0)


def encode_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:
    """Encode N strings -> (N, 512) float32, L2-normalised."""
    model, _, tokenizer, device = _require_model()
    if not texts:
        return np.empty((0, EMBED_DIM), dtype=np.float32)

    out: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            tokens = tokenizer(chunk).to(device)
            out.append(_normalise(model.encode_text(tokens)))
    return np.concatenate(out, axis=0)


# --------------------------------------------------------------------------- #
# Single-item encoders — the API the routers use
# --------------------------------------------------------------------------- #
def encode_image(image_path: str) -> np.ndarray:
    """(512,) float32 unit vector for one photograph."""
    return encode_images([image_path])[0]


def encode_text(text: str) -> np.ndarray:
    """(512,) float32 unit vector for one description."""
    return encode_texts([text])[0]


def encode_combined(text: str | None, image_path: str | None) -> np.ndarray:
    """Mean of the text and image vectors, re-normalised to unit length.

    A lost report may carry a description, a photo, or both. Averaging keeps the
    result in the same unit sphere as every other vector in the index, so one
    IndexFlatIP can score all three cases identically.
    """
    parts = []
    if text and text.strip():
        parts.append(encode_text(text))
    if image_path:
        parts.append(encode_image(image_path))
    if not parts:
        raise ValueError("encode_combined needs at least one of text or image_path")

    if len(parts) == 1:
        return parts[0]

    averaged = np.mean(parts, axis=0)
    norm = float(np.linalg.norm(averaged))
    return (averaged / max(norm, 1e-12)).astype(np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Dot product of two unit vectors. Defensive re-normalisation is cheap."""
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / max(denom, 1e-12))
