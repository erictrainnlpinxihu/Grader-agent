"""Reranker：相关性重排（在线 rerank API / 离线确定性来源权重）。

在线（默认，需有效 key）：POST {GRADER_LLM_BASE_URL}/rerank（SiliconFlow 等
OpenAI 兼容生态的 rerank 端点），模型取 GRADER_RERANK_MODEL（默认
BAAI/bge-reranker-v2-m3），对 query × 候选文本打 relevance_score；
rerank_score = relevance_score × 来源权重（DOMAIN_WEIGHT）。

离线（GRADER_OFFLINE_RAG=1）或在线任何异常（缺 key / 超时 / 非 200）：
确定性回落，rerank_score = rrf_score × 来源权重。两种模式都只影响排序，
不影响召回与缓存契约；离线路径字节级可复跑。
"""

from __future__ import annotations

import os
from typing import Any, Optional

import harness.config  # noqa: F401  # 首次 import 即加载 .env，须早于下面的环境变量读取

DOMAIN_WEIGHT = {
    "rubric_knowledge": 1.0,
    "exemplar_essays": 0.85,
    "textbook_chapters": 0.8,
    "grading_sop": 0.7,
    "academic_integrity_policy": 1.0,
}

# 占位串视为缺失 key（与 embedding / llm 的判定一致）
_PLACEHOLDER_KEYS = {"", "placeholder", "sk-xxx"}


def _online_rerank_scores(query: str, texts: list[str]) -> Optional[list[float]]:
    """调在线 rerank API，返回与 texts 等长的 relevance_score 列表；失败返回 None。"""
    import httpx

    api_key = os.environ.get("GRADER_LLM_API_KEY", "")
    if api_key in _PLACEHOLDER_KEYS:
        return None
    base = os.environ.get("GRADER_LLM_BASE_URL", "https://api.siliconflow.cn/v1")
    model = os.environ.get("GRADER_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    resp = httpx.post(
        f"{base}/rerank",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "query": query, "documents": texts, "top_n": len(texts)},
        timeout=10.0,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    scores = [0.0] * len(texts)
    for item in results:
        idx = item.get("index")
        if isinstance(idx, int) and 0 <= idx < len(texts):
            scores[idx] = float(item.get("relevance_score", 0.0))
    return scores


class Reranker:
    """相关性 × 来源权重重排；在线 rerank API，离线确定性。"""

    def rerank(
        self,
        results: list[dict[str, Any]],
        top_k: int = 5,
        query: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        relevance: Optional[list[float]] = None
        if query and os.environ.get("GRADER_OFFLINE_RAG", "") != "1":
            try:
                relevance = _online_rerank_scores(
                    query, [r.get("text", "") for r in results]
                )
            except Exception:  # noqa: BLE001
                relevance = None  # 在线失败回落确定性，检索链路不中断

        scored = []
        for i, r in enumerate(results):
            weight = DOMAIN_WEIGHT.get(r.get("domain", ""), 0.5)
            if relevance is not None:
                final = relevance[i] * weight
            else:
                final = float(r.get("score", 0.0)) * weight
            scored.append({**r, "rerank_score": round(final, 6)})
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]
