"""HybridRetriever：向量召回 + 关键词召回 + RRF 融合 + intent 域路由。

academic_integrity_question 和 grade_appeal 不向量召回，只直挂 academic_integrity_policy。
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

from rag.build_index import Chunk, get_index_builder
from rag.embedding import get_embedding

# intent → 索引域路由表
RAG_ROUTE_MAP: dict[str, list[str]] = {
    "rubric_query": ["rubric_knowledge"],
    "syllabus_material_query": ["textbook_chapters", "grading_sop"],
    "grading_request": ["rubric_knowledge", "exemplar_essays", "grading_sop"],
    "deferred_exam_query": ["grading_sop"],
    "academic_integrity_question": [],  # 直挂政策，不向量召回
    "grade_appeal": [],                # 直挂政策，不向量召回
}

# 直挂域（预检索 append citation，不进向量索引）
PINNED_DOMAIN = "academic_integrity_policy"

RRF_K = 60


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def _keyword_score(query: str, text: str) -> float:
    """简单关键词匹配：query 分词命中数。"""
    q_tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) > 1]
    if not q_tokens:
        return 0.0
    t_low = text.lower()
    hits = sum(1 for tok in q_tokens if tok in t_low)
    return hits / len(q_tokens)


class HybridRetriever:
    """向量 + 关键词 hybrid 召回，RRF 融合。"""

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k
        self._index = get_index_builder().get_index()

    def retrieve(self, query: str, intent: str) -> list[dict[str, Any]]:
        """按 intent 路由域，返回召回结果列表。"""
        domains = RAG_ROUTE_MAP.get(intent, [])
        if not domains:
            # 直挂域：不向量召回，只返回 pinned citation
            return [
                {
                    "chunk_id": PINNED_DOMAIN,
                    "text": "",
                    "domain": PINNED_DOMAIN,
                    "score": 1.0,
                    "pinned": True,
                    "metadata": {"policy_id": "academic_integrity", "scene_key": "policy"},
                }
            ]

        # 收集目标域内所有 chunk
        candidates: list[Chunk] = []
        for d in domains:
            candidates.extend(self._index.get(d, []))
        if not candidates:
            return []

        # 向量召回
        q_vec = get_embedding(query)
        vector_ranked = sorted(
            candidates, key=lambda c: _cosine(q_vec, c.vector), reverse=True
        )[: self.top_k]

        # 关键词召回
        keyword_ranked = sorted(
            candidates, key=lambda c: _keyword_score(query, c.text), reverse=True
        )[: self.top_k]

        # RRF 融合
        rrf_scores: dict[str, float] = {}
        for rank, c in enumerate(vector_ranked):
            rrf_scores[c.chunk_id] = rrf_scores.get(c.chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, c in enumerate(keyword_ranked):
            rrf_scores[c.chunk_id] = rrf_scores.get(c.chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)

        chunk_by_id = {c.chunk_id: c for c in candidates}
        fused_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
        results: list[dict[str, Any]] = []
        for cid in fused_ids[: self.top_k]:
            c = chunk_by_id[cid]
            results.append(
                {
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "domain": c.domain,
                    "score": round(rrf_scores[cid], 6),
                    "pinned": False,
                    "metadata": c.metadata,
                }
            )
        return results
