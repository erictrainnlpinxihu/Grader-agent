"""Reranker：按相关性分数 + 来源权重重排。

来源权重：rubric > exemplar > textbook > sop。
离线模式用确定性规则。
"""

from __future__ import annotations

from typing import Any

DOMAIN_WEIGHT = {
    "rubric_knowledge": 1.0,
    "exemplar_essays": 0.85,
    "textbook_chapters": 0.8,
    "grading_sop": 0.7,
    "academic_integrity_policy": 1.0,
}


class Reranker:
    """简单确定性重排：score * domain_weight。"""

    def rerank(self, results: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
        scored = []
        for r in results:
            weight = DOMAIN_WEIGHT.get(r.get("domain", ""), 0.5)
            final = float(r.get("score", 0.0)) * weight
            scored.append({**r, "rerank_score": round(final, 6)})
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]
