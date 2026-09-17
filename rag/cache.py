"""RetrievalCache + IndexCache。"""

from __future__ import annotations

import hashlib
from typing import Any, Optional


def _query_hash(query: str, intent: str) -> str:
    return hashlib.sha256(f"{intent}::{query}".encode("utf-8")).hexdigest()[:16]


class RetrievalCache:
    """dict[query_hash] -> list[result]。"""

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = {}

    def get(self, query: str, intent: str) -> Optional[list[dict[str, Any]]]:
        return self._store.get(_query_hash(query, intent))

    def set(self, query: str, intent: str, results: list[dict[str, Any]]) -> None:
        self._store[_query_hash(query, intent)] = results

    def invalidate(self, query: str, intent: str) -> None:
        self._store.pop(_query_hash(query, intent), None)

    def clear(self) -> None:
        self._store.clear()


class IndexCache:
    """索引构建结果缓存。"""

    def __init__(self) -> None:
        self._cached: Any = None

    def get(self) -> Any:
        return self._cached

    def set(self, index: Any) -> None:
        self._cached = index

    def invalidate(self) -> None:
        self._cached = None
