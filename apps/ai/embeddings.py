"""Pluggable text embedding. Default 'fake' provider needs no API key so the
whole RAG path runs in dev/tests; set AI_EMBED_PROVIDER=openai for real ones."""
import hashlib
import json
import os
import urllib.request

from django.conf import settings


def _active_provider() -> str:
    """Embedding provider, gated on runtime mode.

    Explicit AI_EMBED_PROVIDER (non-default) always wins — e.g. force openai in
    dev. Otherwise prod uses the real provider, dev/test stays on the keyless
    fake so the RAG path runs with no API key.
    """
    if settings.AI_EMBED_PROVIDER != "fake":
        return settings.AI_EMBED_PROVIDER
    from apps.governance.models import is_prod

    # ponytail: prod uses openai only when a key is actually present; without one
    # we degrade to the keyless fake instead of 500ing keyless envs (dev/tests/CI).
    if is_prod() and os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "fake"


def embed(text: str) -> list[float]:
    if _active_provider() == "openai":
        return _openai_embed(text)
    return _fake_embed(text)


def _openai_embed(text: str) -> list[float]:
    import os

    key = os.environ["OPENAI_API_KEY"]  # KeyError = misconfig, fail loud
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps({"model": settings.AI_EMBED_MODEL, "input": text}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"][0]["embedding"]


def _fake_embed(text: str) -> list[float]:
    """Deterministic unit vector via bag-of-words feature hashing.

    ponytail: cheap stand-in for real embeddings — each token hashes to one
    bucket, so texts sharing words get high cosine and unrelated texts stay
    near-orthogonal. Enough for ranking + tests; AI_EMBED_PROVIDER=openai for
    actual semantics.
    """
    dim = settings.EMBED_DIM
    vals = [0.0] * dim
    for tok in text.lower().split():
        h = hashlib.sha256(tok.encode()).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] & 1 else -1.0  # signed hashing reduces collisions
        vals[idx] += sign
    norm = sum(v * v for v in vals) ** 0.5 or 1.0
    return [v / norm for v in vals]
