"""Grader 核心层领域 Pydantic 契约（Pydantic v2）。

本模块是核心层与 agent/api 层之间的稳定接口边界。所有跨模块传递的
结构化对象都必须在这里定义；guardrail（跨字段校验、状态机、权限矩阵）
尽量落在契约层或 harness 其他模块，而不是 prompt 里。
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# 12 intent（见 CLAUDE.md §6.3）
# ---------------------------------------------------------------------------
INTENTS = Literal[
    "assignment_status_query",
    "grading_request",
    "rubric_query",
    "grade_appeal",
    "academic_integrity_question",
    "deferred_exam_query",
    "syllabus_material_query",
    "batch_grading",
    "general_chat",
    "low_confidence_query",
    "degradation_request",
    "security_request",
]

ROUTE_KINDS = Literal[
    "tool_readonly",
    "rag",
    "workflow_human",
    "deterministic",
    "deterministic_fallback",
    "deterministic_block",
    "task_planner",
]


class RoutePlanCandidate(BaseModel):
    """plan 阶段由 LLM with_structured_output 直接绑定的路由候选。

    跨字段校验失败即走 deterministic_fallback，不把非法计划喂给执行层。
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    intent: INTENTS
    route_kind: ROUTE_KINDS
    confidence: float
    needs_business_tools: bool = False
    required_tools: list[str] = []
    needs_rag: bool = False
    knowledge_domains: list[str] = []
    requires_workflow: bool = False
    risk_level: Literal["low", "high"] = "low"
    fallback_policy: Optional[str] = None

    @model_validator(mode="after")
    def cross_field_check(self) -> "RoutePlanCandidate":
        if self.required_tools and not self.needs_business_tools:
            raise ValueError("required_tools non-empty requires needs_business_tools=True")
        if self.knowledge_domains and not self.needs_rag:
            raise ValueError("knowledge_domains non-empty requires needs_rag=True")
        if self.requires_workflow and not (
            self.risk_level == "high" and self.fallback_policy == "workflow_first"
        ):
            raise ValueError(
                "requires_workflow requires risk=high and fallback_policy=workflow_first"
            )
        return self


class QueryRewrite(BaseModel):
    """路由之前的结构化改写：指代消解 / 口语归一 / 子问题分解。"""

    rewritten_query: str
    submission_id: Optional[str] = None
    course_id: Optional[str] = None
    assignment_id: Optional[str] = None
    sub_questions: list[str] = []
    confidence: float = 1.0


class GradingDraftItem(BaseModel):
    """单个 rubric 条目的初批草稿。"""

    rubric_item_id: str
    score: float
    max_score: float
    reason: str
    cited_chunk_hash: Optional[str] = None


class GradingDraft(BaseModel):
    """模型产出的结构化批改草稿，终录前永远只是 draft。"""

    submission_id: str
    rubric_version: str
    items: list[GradingDraftItem]
    overall_score: float
    draft_feedback: str
    flagged: bool = False
    flagged_reasons: list[str] = []


HIGH_RISK_ACTIONS = Literal[
    "record_final_grade",
    "judge_academic_misconduct",
    "recommend_deferred_exam",
    "publish_feedback",
]


class HighRiskProposal(BaseModel):
    """4 个不可逆写动作的提案对象。模型只产出此对象，物理上不执行写。"""

    action: HIGH_RISK_ACTIONS
    submission_id: str
    proposed_payload: dict
    frozen_fields: dict
    pending_instructor_approval: bool = True


SUBMISSION_STATES = Literal[
    "received",
    "draft_graded",
    "flagged",
    "approved",
    "recorded",
    "rejected",
    "paused",
]


class GradeGraphState(TypedDict, total=False):
    """单份作业的 HITL 状态机快照（LangGraph StateGraph 用）。"""

    submission_id: str
    course_id: str
    assignment_id: str
    state: SUBMISSION_STATES
    draft: Optional[GradingDraft]
    draft_score: Optional[float]
    draft_feedback: Optional[str]
    flagged_reasons: list[str]
    frozen_fields: dict
    history: list


class ShardState(BaseModel):
    """批量批改的一个分片。"""

    shard_index: int
    submission_ids: list[str]
    status: Literal["pending", "running", "done", "failed"]
    processed: int = 0
    failed: int = 0


class BatchState(BaseModel):
    """批量批改整体状态（M1 单线程 / M2 分片并行共用）。"""

    batch_id: str
    course_id: str
    assignment_id: str
    rubric_version: str
    total: int
    processed: int = 0
    failed: int = 0
    shards: list[ShardState] = []
    next_resume_token: Optional[str] = None


class TraceEvent(BaseModel):
    """公开 trace 事件（schema_version=grader_trace_v1）。

    trace 里只允许出现脱敏后的公开信号；hidden_reasoning / system_prompt
    在写入前必须被 TraceStore 递归删除。
    """

    event: str
    timestamp: str
    session_id: str
    payload: dict = {}
    schema_version: str = "grader_trace_v1"


class RuntimeContext(BaseModel):
    """运行时身份上下文。role 以 LMS 快照为准，claimed_role 仅展示不授权。"""

    user_id: str
    role: Literal["student", "ta", "instructor"]
    course_id: str
    instructor_in_snapshot: bool = False
    current_page: str = "home"
    claimed_role: Optional[str] = None
    identity_conflicts: list[str] = []
