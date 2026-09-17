"""QueryRewriter：结构化改写（指代消解 / 口语归一 / 子问题分解）。

在线模式：``llm.with_structured_output(QueryRewrite)``。
离线模式（GRADER_DISABLE_LLM=1）：确定性规则——
- 正则提取 S1001/S1002 submission_id、CS101 课程 id、A3 assignment_id；
- 指代消解："上次那个作业"→ runtime_context / memory 中的当前 submission_id；
- 子问题分解：批量请求拆为多个子问题。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from agent.llm import get_llm_client
from harness.contracts import QueryRewrite, RuntimeContext

_SUBMISSION_RE = re.compile(r"\b(S\d{3,4})\b")
_COURSE_RE = re.compile(r"\b(CS\d{3}[A-Za-z0-9-]*)\b")
_ASSIGNMENT_RE = re.compile(r"\b(A\d{1,3})\b")

_BAREF_ASSIGNMENT = re.compile(r"第?\s*(\d+)\s*(?:次|作业|题)")


class QueryRewriter:
    """把口语查询归一为结构化 QueryRewrite。"""

    def __init__(self) -> None:
        self.llm = get_llm_client()

    # ------------------------------------------------------------------
    def rewrite(
        self,
        text: str,
        runtime_context: RuntimeContext,
        memory: Optional[dict[str, Any]] = None,
    ) -> QueryRewrite:
        memory = memory or {}
        online = self.llm.structured(QueryRewrite, self._system_prompt(text))
        if online is not None and isinstance(online, QueryRewrite):
            return self._apply_coreference(online, runtime_context, memory)

        # 离线确定性规则
        return self._offline_rewrite(text, runtime_context, memory)

    # ------------------------------------------------------------------
    def _offline_rewrite(
        self,
        text: str,
        runtime_context: RuntimeContext,
        memory: dict[str, Any],
    ) -> QueryRewrite:
        rewritten = text.strip()

        submission_id = None
        m = _SUBMISSION_RE.search(rewritten)
        if m:
            submission_id = m.group(1)
        elif any(k in rewritten for k in ("上次", "那个作业", "这份", "刚才")):
            # 指代消解：用 runtime_context / memory 中的当前 submission
            submission_id = memory.get("current_submission_id")

        course_id = runtime_context.course_id
        m = _COURSE_RE.search(rewritten)
        if m:
            course_id = m.group(1)

        assignment_id = memory.get("current_assignment_id")
        m = _ASSIGNMENT_RE.search(rewritten)
        if m:
            assignment_id = m.group(1)
        else:
            am = _BAREF_ASSIGNMENT.search(rewritten)
            if am:
                assignment_id = f"A{am.group(1)}"

        sub_questions: list[str] = []
        if any(k in rewritten for k in ("批量", "全部", "所有", "200份")):
            sub_questions = [rewritten]

        return QueryRewrite(
            rewritten_query=rewritten,
            submission_id=submission_id,
            course_id=course_id,
            assignment_id=assignment_id,
            sub_questions=sub_questions,
            confidence=1.0,
        )

    # ------------------------------------------------------------------
    def _apply_coreference(
        self,
        rw: QueryRewrite,
        runtime_context: RuntimeContext,
        memory: dict[str, Any],
    ) -> QueryRewrite:
        if not rw.submission_id and memory.get("current_submission_id"):
            rw.submission_id = memory["current_submission_id"]
        if not rw.course_id:
            rw.course_id = runtime_context.course_id
        if not rw.assignment_id and memory.get("current_assignment_id"):
            rw.assignment_id = memory["current_assignment_id"]
        return rw

    @staticmethod
    def _system_prompt(text: str) -> str:
        return (
            "你是 Grader 的查询改写器。把学生/助教的口语查询归一为结构化字段："
            "提取 submission_id（形如 S1001）、course_id（形如 CS101）、assignment_id（形如 A3），"
            "必要时拆分子问题。原始查询：" + text
        )
