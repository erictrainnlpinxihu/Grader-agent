"""HTTP 请求 / 响应 Pydantic 契约。

api 层只做收发与契约校验，不沾业务判断。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from harness.contracts import TraceEvent


class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    role: Literal["student", "ta", "instructor"] = "student"
    course_id: str
    assignment_id: Optional[str] = None
    submission_id: Optional[str] = None
    current_page: str = "home"
    text: str
    claimed_role: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    signals: list[str] = Field(default_factory=list)
    intent: str
    route_kind: str
    grading_draft: Optional[dict[str, Any]] = None
    pending_approval: Optional[dict[str, Any]] = None
    trace_events: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    next_action: str = "answer_user"
    needs_human_approval: bool = False
    session_state: dict[str, Any] = Field(default_factory=dict)
    cost_summary: dict[str, Any] = Field(default_factory=dict)


class ChatResumeRequest(BaseModel):
    session_id: str
    resume_token: str
    approved_action: dict[str, Any] = Field(default_factory=dict)
    # 兼容字段
    instructor_id: Optional[str] = None
    decision: Optional[Literal["approve", "reject", "needs_more_info"]] = None


class ApprovalRequest(BaseModel):
    session_id: Optional[str] = None
    submission_id: Optional[str] = None
    instructor_id: str
    decision: Literal["approve", "reject", "needs_more_info"]
    reason: Optional[str] = None
    resume_token: Optional[str] = None


class EvalRunRequest(BaseModel):
    case_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    session_id: str
    case_id: Optional[str] = None
    feedback_text: str
    attribution_hint: Optional[str] = None


class TraceEventResponse(BaseModel):
    """复用 harness.contracts.TraceEvent。"""

    events: list[dict[str, Any]] = Field(default_factory=list)


class ManifestResponse(BaseModel):
    """直接返回 grader_manifest.json 内容。"""

    manifest: dict[str, Any] = Field(default_factory=dict)
