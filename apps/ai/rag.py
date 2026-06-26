"""Semantic search + RAG synthesis over indexed content (tenant-scoped)."""
import json
import os
import urllib.request

from django.conf import settings

from .embeddings import embed
from .models import ContentEmbedding

DISCLAIMER = "This information is educational only and not medical advice."

_SYSTEM = (
    "You are a health information assistant. Answer ONLY from the provided "
    "context. If the context is insufficient, say so. Never give a diagnosis or "
    "treatment instruction; this is educational information, not medical advice."
)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def semantic_search(query: str, k: int = 8):
    """Top-k nearest content embeddings for the current tenant.

    ponytail: cosine computed in Python over the tenant's rows (O(n) scan) so
    we stay DB-agnostic (mysql/sqlite, no pgvector). Push back into the DB with
    a vector index if a tenant's embedding count makes the scan too slow.
    """
    vec = embed(query)
    scored = [
        (_cosine(vec, r.embedding), r)
        for r in ContentEmbedding.objects.all()
    ]
    scored.sort(key=lambda s: s[0], reverse=True)
    return [
        {
            "content_type": r.content_type.model,
            "object_id": r.object_id,
            "text": r.text,
            "score": round(score, 4),  # cosine similarity
        }
        for score, r in scored[:k]
    ]


def rag_answer(query: str, k: int = 8):
    hits = semantic_search(query, k)
    # Only feed actually-relevant context to the model; near-zero cosine hits
    # are noise (esp. with the fake embedder) and provoke fabrication.
    contexts = [h["text"] for h in hits if h["score"] > 0]
    answer = _generate(query, contexts) if contexts else None
    return {
        "answer": answer,  # null when no API key -> retrieval-only
        "sources": hits,
        "disclaimer": DISCLAIMER,
    }


def _generate(query: str, contexts: list[str]) -> str | None:
    from apps.governance.models import is_prod

    # Synthesis runs in prod only; dev/test stays retrieval-only (no spend, no
    # external call). Toggle from admin: Governance -> Runtime config.
    if not is_prod():
        return None
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None  # retrieval-only mode
    context = "\n\n---\n\n".join(contexts)
    body = {
        "model": settings.AI_GEN_MODEL,
        "max_tokens": 1024,
        "system": _SYSTEM,
        "messages": [
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
        ],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        return data["content"][0]["text"]
    except Exception:
        # ponytail: API down/timeout/ratelimit/bad-response -> degrade to
        # retrieval-only (sources still returned) instead of 500ing the request.
        return None
