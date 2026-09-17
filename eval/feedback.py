"""负反馈归因 + 回填回归 case。

归因维度：{Prompt, RAG, Tool, Context, Workflow}。
把教师负反馈转化为临时回归 case，追加到 BACKFILLED_CASES。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


BACKFILLED_CASES: list[dict[str, Any]] = []


@dataclass
class FeedbackRecord:
    feedback_id: str
    session_id: str
    case_id: Optional[str]
    feedback_text: str
    attributions: list[dict[str, Any]] = field(default_factory=list)
    trace_event_names: list[str] = field(default_factory=list)


class FailureAttributor:
    """根据负反馈文本与 trace 事件做粗粒度归因。"""

    _KEYWORDS: dict[str, str] = {
        "扣分": "RAG",
        "评分标准": "RAG",
        "rubric": "RAG",
        "引用": "RAG",
        "查重": "Tool",
        "分数不对": "Tool",
        "数据": "Tool",
        "权限": "Context",
        "身份": "Context",
        "越权": "Context",
        "审批": "Workflow",
        "录入": "Workflow",
        "申诉": "Workflow",
        "prompt": "Prompt",
        "话术": "Prompt",
        "回答": "Prompt",
    }

    def attribute(
        self,
        session_id: str,
        trace_events: list[dict[str, Any]],
        feedback_text: str,
    ) -> dict[str, Any]:
        event_names = [e.get("event") for e in trace_events if e.get("event")]
        # 关键词命中归因
        hit_dims: list[str] = []
        for kw, dim in self._KEYWORDS.items():
            if kw in feedback_text and dim not in hit_dims:
                hit_dims.append(dim)
        # trace 事件辅助归因
        if any("workflow" in n or "resume" in n for n in event_names):
            if "Workflow" not in hit_dims:
                hit_dims.append("Workflow")
        if any("rag" in n for n in event_names):
            if "RAG" not in hit_dims:
                hit_dims.append("RAG")
        if not hit_dims:
            hit_dims = ["Prompt"]

        attributions = [
            {"module": dim, "suggested_fix": f"检查 {dim} 相关路径，补充回归断言"}
            for dim in hit_dims
        ]
        return {
            "session_id": session_id,
            "dimensions": hit_dims,
            "attributions": attributions,
            "trace_event_names": event_names,
        }

    # ------------------------------------------------------------------
    def build_backfilled_case(
        self,
        feedback_request: dict[str, Any],
        attribution: dict[str, Any],
    ) -> dict[str, Any]:
        n = len(BACKFILLED_CASES) + 1
        case_id = f"feedback-{n:03d}"
        backfilled = {
            "case_id": case_id,
            "case_type": "feedback",
            "source_session": feedback_request.get("session_id"),
            "feedback_text": feedback_request.get("feedback_text"),
            "attribution": attribution["dimensions"],
            "expected": {
                "expected_trace_events": ["feedback_received", "failure_attributed", "backfilled_case_built"],
            },
        }
        BACKFILLED_CASES.append(backfilled)
        return backfilled
