"""source_guard：三级信任标 + 作业正文注入检测。

信任标：
- Trusted      ：RAG 文档 / 系统 prompt 片段 / 直挂政策
- Semi-trusted ：LMS 工具返回（已对账，可能过期）
- Untrusted     ：学生作业正文 / 申诉文本 / 聊天输入（永远不可信）

命中注入正则时，内容替换为 "[tainted-source-redacted]"，**攻击原文绝不写进 trace**，
只记位置 / 长度 / sha256 / 命中正则名。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

TRUSTED = "trusted"
SEMI_TRUSTED = "semi_trusted"
UNTRUSTED = "untrusted"

# Grader 化注入正则（至少 6 条）
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "override_rubric_or_prompt",
        re.compile(r"忽略(?:评分|rubric|上面|之前|所有).{0,10}(?:标准|指令|prompt|系统)", re.IGNORECASE),
    ),
    (
        "role_hijack",
        re.compile(r"你现在是.{0,10}(?:助教|老师|宽容|宽松|管理员|另一个角色)", re.IGNORECASE),
    ),
    (
        "grade_begging",
        re.compile(r"(?:给我|给我打).{0,5}(?:满分|100|A\+|及格)", re.IGNORECASE),
    ),
    (
        "authority_assertion",
        re.compile(r"作为(?:老师|教师|助教|管理员).{0,10}(?:应该|必须|直接)", re.IGNORECASE),
    ),
    (
        "system_message_leak",
        re.compile(r"(?:system|developer)\s*(?:message|prompt|指令)", re.IGNORECASE),
    ),
    (
        "hidden_cot_extract",
        re.compile(r"输出(?:隐藏|内部|完整).{0,8}(?:推理|提示词|策略)", re.IGNORECASE),
    ),
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def inspect_source(source: str, content: str, trust_level: str) -> dict[str, Any]:
    """检查一段内容是否命中注入正则。

    返回 dict（公开安全摘要，可进 trace）：
    - tainted: bool
    - categories: list[str]
    - redacted_content: str（命中时为占位串，否则原文）
    - sha256: 原文哈希
    - length: 原文长度
    - matched_pattern: 命中的正则名（None 表示未命中）
    """
    matched: list[str] = []
    for name, pattern in _INJECTION_PATTERNS:
        if pattern.search(content or ""):
            matched.append(name)

    tainted = bool(matched)
    return {
        "source": source,
        "trust_level": trust_level,
        "tainted": tainted,
        "categories": ["instruction_override"] if tainted else [],
        "redacted_content": "[tainted-source-redacted]" if tainted else content,
        "sha256": _sha256(content or ""),
        "length": len(content or ""),
        "matched_pattern": matched[0] if matched else None,
    }


def inspect_sources(items: list[tuple[str, str, str]]) -> tuple[list[str], list[dict[str, Any]]]:
    """批量检查 (source, content, trust_level)，返回 (清洗后内容列表, 报告列表)。"""
    reports = [inspect_source(s, c, t) for (s, c, t) in items]
    return [str(r["redacted_content"]) for r in reports], reports
