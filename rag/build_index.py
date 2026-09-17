"""IndexBuilder：从 rag/knowledge/ 加载 4 个索引域 md，切块 + 向量化。

academic_integrity_policy.md 是预检索直挂域，不进向量索引。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from rag.embedding import get_embedding

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"

# 4 个索引域（academic_integrity_policy 直挂不进索引）
INDEX_DOMAINS = {
    "textbook_chapters": "textbook_chapters.md",
    "rubric_knowledge": "rubric_knowledge.md",
    "exemplar_essays": "exemplar_essays.md",
    "grading_sop": "grading_sop.md",
}

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


@dataclass
class Chunk:
    chunk_id: str
    text: str
    domain: str
    metadata: dict[str, Any]
    vector: list[float]


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """解析 md frontmatter（---...---）。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_lines = parts[1].strip().splitlines()
    body = parts[2].strip()
    meta: dict[str, Any] = {}
    for line in fm_lines:
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按段落切块，简单按长度滑动窗口。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) <= size:
            buf = (buf + "\n\n" + para).strip()
        else:
            if buf:
                chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    # 重叠：相邻 chunk 末尾 overlap 字符
    out = []
    for i, c in enumerate(chunks):
        if i > 0 and overlap:
            tail = chunks[i - 1][-overlap:]
            c = tail + c
        out.append(c)
    return out


class IndexBuilder:
    """构建内存向量索引：dict[domain] -> list[Chunk]。"""

    def __init__(self, knowledge_dir: Path = KNOWLEDGE_DIR) -> None:
        self.knowledge_dir = knowledge_dir
        self._index: dict[str, list[Chunk]] = {}

    def build(self) -> dict[str, list[Chunk]]:
        """从 knowledge/ 加载 4 个索引域，切块 + 向量化。"""
        if self._index:
            return self._index
        for domain, filename in INDEX_DOMAINS.items():
            path = self.knowledge_dir / filename
            if not path.exists():
                continue
            raw = path.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(raw)
            chunks_text = _chunk_text(body)
            chunks: list[Chunk] = []
            for i, ct in enumerate(chunks_text):
                cid = hashlib.sha256(f"{domain}::{i}::{ct[:64]}".encode()).hexdigest()[:16]
                chunks.append(
                    Chunk(
                        chunk_id=cid,
                        text=ct,
                        domain=domain,
                        metadata={**meta, "chunk_index": i},
                        vector=get_embedding(ct),
                    )
                )
            self._index[domain] = chunks
        return self._index

    def get_index(self) -> dict[str, list[Chunk]]:
        return self._index or self.build()


# 全局单例索引（进程内缓存）
_index_singleton: Optional[IndexBuilder] = None


def get_index_builder() -> IndexBuilder:
    global _index_singleton
    if _index_singleton is None:
        _index_singleton = IndexBuilder()
        _index_singleton.build()
    return _index_singleton
