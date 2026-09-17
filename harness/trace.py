"""TraceStore：grader_trace_v1 公开 trace + 递归 PII 脱敏。

- 公开 trace 与 hidden CoT 从 schema 层隔离：hidden_reasoning / system_prompt 递归删除。
- 学生 PII 递归脱敏：姓名 → "***"、学号 → "stu***"、邮箱 → "***@***"。
- 攻击原文绝不写进 trace（source_guard 已只记 sha256 / 长度 / 正则名）。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from harness.contracts import TraceEvent

TRACE_SCHEMA_VERSION = "grader_trace_v1"

# PII 正则
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_STUDENT_ID_RE = re.compile(r"\b2024\d{3}\b")
# 中文姓名：2-4 个汉字（保守起见不单独匹配单字，避免误伤"张三说"这类正文）
_CHINESE_NAME_RE = re.compile(r"[\u4e00-\u9fa5]{2,4}(?=同学|老师|助教|教授|同学你好|的)")

# 禁止字段（递归删除）
_FORBIDDEN_KEYS = {"system_prompt", "hidden_reasoning", "hidden_cot", "raw_llm_output"}


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _sanitize_value(v)
            for k, v in value.items()
            if k not in _FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(v) for v in value)
    if isinstance(value, str):
        text = _EMAIL_RE.sub("***@***", value)
        text = _STUDENT_ID_RE.sub("stu***", text)
        text = _CHINESE_NAME_RE.sub("***", text)
        return text
    return value


def sanitize_event(event: TraceEvent) -> TraceEvent:
    """递归脱敏 TraceEvent：PII 掩码 + 删 hidden 字段。"""
    safe_payload = _sanitize_value(dict(event.payload))
    return TraceEvent(
        event=event.event,
        timestamp=event.timestamp,
        session_id=event.session_id,
        payload=safe_payload,
        schema_version=TRACE_SCHEMA_VERSION,
    )


class TraceStore:
    """内存 trace 存储：dict[session_id] -> list[TraceEvent]。"""

    def __init__(self) -> None:
        self._events: dict[str, list[TraceEvent]] = {}

    def add(self, event: TraceEvent) -> TraceEvent:
        """追加事件，写入前自动 sanitize。"""
        safe = sanitize_event(event)
        self._events.setdefault(safe.session_id, []).append(safe)
        return safe

    def list(self, session_id: str) -> list[TraceEvent]:
        return list(self._events.get(session_id, []))

    def clear(self, session_id: Optional[str] = None) -> None:
        if session_id is None:
            self._events.clear()
        else:
            self._events.pop(session_id, None)


def make_event(
    event: str,
    session_id: str,
    payload: Optional[dict[str, Any]] = None,
) -> TraceEvent:
    """构造一个带 UTC 时间戳的 TraceEvent。"""
    return TraceEvent(
        event=event,
        timestamp=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
        payload=payload or {},
        schema_version=TRACE_SCHEMA_VERSION,
    )
