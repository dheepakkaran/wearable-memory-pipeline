"""Local embeddings (fastembed, bge-small, CPU). No text leaves the machine for embedding."""
from functools import lru_cache

from .config import CACHE, EMBED_MODEL


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(EMBED_MODEL, cache_dir=str(CACHE / "fastembed"))


def embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().embed(texts)]


def embed_query(q: str) -> list[float]:
    return list(_model().query_embed(q))[0].tolist()
