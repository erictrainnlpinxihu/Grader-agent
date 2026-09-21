"""Embedding 双轨：离线本地 token 确定性替身 / 在线 OpenAI 兼容 API。

离线替身：基于文本 SHA-256 哈希生成 256 维确定性向量。同一文本永远返回同一向量。
"""

from __future__ import annotations

import hashlib
import math
import os

import harness.config  # noqa: F401  # 首次 import 即加载 .env，须早于下面的环境变量读取

EMBED_DIM = 256


def _offline_embedding(text: str) -> list[float]:
    """基于 SHA-256 哈希的确定性替身向量。"""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # 扩展到 EMBED_DIM 维：反复哈希
    vec: list[float] = []
    counter = 0
    while len(vec) < EMBED_DIM:
        block = hashlib.sha256(digest + counter.to_bytes(4, "big")).digest()
        for b in block:
            vec.append((b / 255.0) * 2.0 - 1.0)
        counter += 1
    vec = vec[:EMBED_DIM]
    # L2 归一化
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _online_embedding(text: str) -> list[float]:
    """OpenAI 兼容 embedding API（延迟导入 httpx，避免离线时强依赖）。"""
    import httpx

    base = os.environ.get("GRADER_LLM_BASE_URL", "https://api.siliconflow.cn/v1")
    model = os.environ.get("GRADER_EMBEDDING_MODEL", "BAAI/bge-m3")
    api_key = os.environ.get("GRADER_LLM_API_KEY", "")
    if not api_key or api_key in {"placeholder", "sk-xxx"}:
        raise RuntimeError("GRADER_LLM_API_KEY missing; falling back to offline embedding is disabled here")
    resp = httpx.post(
        f"{base}/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "input": text},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def get_embedding(text: str) -> list[float]:
    """根据 GRADER_OFFLINE_RAG 开关选择在线 / 离线 embedding。"""
    if os.environ.get("GRADER_OFFLINE_RAG", "") == "1":
        return _offline_embedding(text)
    try:
        return _online_embedding(text)
    except Exception:
        # 在线失败时回退离线，保证核心层可跑
        return _offline_embedding(text)
