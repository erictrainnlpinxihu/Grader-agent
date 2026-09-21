"""高风险 workflow 的"发起权 vs 审批权"回归测试。

权限模型：
- student 可以申诉成绩、咨询 / 举报学术不端、申请缓考（发起立案，只产提案、暂停等审批）；
- ta 可以立案复核与初批；
- 终录成绩 / 学术不端终判 / 缓考推荐是 instructor 专属，student / ta 即便拿到
  resume_token 审批也会被 blocked/approver_not_authorized。

另覆盖：在线模型把"算不算学术不端"误判为 grading 时，受保护关键词安全网强制纠偏。
"""

from __future__ import annotations

from types import SimpleNamespace

from agent.intent_router import IntentRouter
from agent.loop import GraderAgent
from harness.approval_gate import ApprovalGate
from harness.contracts import (
    HighRiskProposal,
    QueryRewrite,
    RoutePlanCandidate,
    RuntimeContext,
)

COURSE = "CS101-2026spring"
ASSIGNMENT = "A3"
SUBMISSION = "S1001"


def _chat(agent: GraderAgent, user_id: str, text: str, session_id: str) -> dict:
    return agent.chat(
        {
            "session_id": session_id,
            "user_id": user_id,
            "course_id": COURSE,
            "assignment_id": ASSIGNMENT,
            "submission_id": SUBMISSION,
            "text": text,
        }
    )


def _resume(agent: GraderAgent, session_id: str, token: str, approver_id: str) -> dict:
    return agent.resume(
        {
            "session_id": session_id,
            "resume_token": token,
            "course_id": COURSE,
            "approved_action": {"decision": "approve", "instructor_id": approver_id},
        }
    )


# ---------------------------------------------------------------------------
# 1. 发起权：student / ta 都可对学术不端疑问立案，系统不自动处分
# ---------------------------------------------------------------------------
def test_student_academic_integrity_enters_workflow() -> None:
    agent = GraderAgent()
    resp = _chat(agent, "stu-001", "这份作业算不算学术不端", "hr-stu")
    assert resp["intent"] == "academic_integrity_question"
    assert resp["route_kind"] == "workflow_human"
    assert resp["needs_human_approval"] is True
    assert resp["pending_approval"] is not None
    assert resp["pending_approval"]["state"] == "flagged"
    assert resp["pending_approval"]["action"] == "judge_academic_misconduct"
    sources = [c["source"] for c in resp.get("citations", [])]
    assert "academic_integrity_policy" in sources
    assert "不自动处分" in resp["answer"]


def test_ta_academic_integrity_enters_workflow() -> None:
    agent = GraderAgent()
    resp = _chat(agent, "ta-001", "这份作业算不算学术不端", "hr-ta")
    assert resp["intent"] == "academic_integrity_question"
    assert resp["route_kind"] == "workflow_human"
    assert resp["pending_approval"]["state"] == "flagged"


def test_student_appeal_enters_workflow_with_record_action() -> None:
    agent = GraderAgent()
    resp = _chat(agent, "stu-001", "我要申诉这个成绩，我不服", "hr-appeal")
    assert resp["intent"] == "grade_appeal"
    assert resp["route_kind"] == "workflow_human"
    assert resp["needs_human_approval"] is True
    assert resp["pending_approval"]["action"] == "record_final_grade"
    sources = [c["source"] for c in resp.get("citations", [])]
    assert "academic_integrity_policy" in sources


# ---------------------------------------------------------------------------
# 2. 审批权：仅 instructor 可终判；student / ta 审批被 blocked 且不改状态
# ---------------------------------------------------------------------------
def test_student_and_ta_cannot_approve_only_instructor_can() -> None:
    agent = GraderAgent()
    resp = _chat(agent, "stu-001", "我第三次作业查重率35%，这算学术不端吗？", "hr-approve")
    token = resp["pending_approval"]["resume_token"]

    student_res = _resume(agent, "hr-approve", token, "stu-001")
    assert student_res["status"] == "blocked"
    assert student_res["reason"] == "approver_not_authorized"
    assert student_res["recorded_actions"] == []

    ta_res = _resume(agent, "hr-approve", token, "ta-001")
    assert ta_res["status"] == "blocked"
    assert ta_res["reason"] == "approver_not_authorized"
    assert ta_res["recorded_actions"] == []

    instructor_res = _resume(agent, "hr-approve", token, "ins-001")
    assert instructor_res["status"] == "recorded"
    assert instructor_res["recorded_actions"] == ["judge_academic_misconduct"]


def test_gate_resume_enforces_approver_role() -> None:
    gate = ApprovalGate()
    proposal = HighRiskProposal(
        action="judge_academic_misconduct",
        submission_id=SUBMISSION,
        proposed_payload={"intent": "academic_integrity_question"},
        frozen_fields={},
    )
    cp = gate.create_checkpoint(SUBMISSION, "flagged", {}, proposal)
    common = dict(
        current_frozen=cp["frozen_fields"],
        timestamp_bucket="2026-09-21",
    )

    ta_res = gate.resume(
        cp["resume_token"], "approved",
        approved_instructor_id="ta-001", approver_role="ta", **common,
    )
    assert ta_res["status"] == "blocked"
    assert ta_res["reason"] == "approver_not_authorized"

    ins_res = gate.resume(
        cp["resume_token"], "approved",
        approved_instructor_id="ins-001", approver_role="instructor", **common,
    )
    assert ins_res["status"] == "recorded"


# ---------------------------------------------------------------------------
# 3. 在线误分类纠偏：受保护意图模型不可降级
# ---------------------------------------------------------------------------
def test_online_misclassification_of_integrity_is_corrected() -> None:
    router = IntentRouter()
    wrong = RoutePlanCandidate(
        intent="grading_request",
        route_kind="tool_readonly",
        confidence=0.95,
        needs_business_tools=True,
        required_tools=["get_submission"],
    )
    router.llm = SimpleNamespace(structured=lambda *a, **k: wrong)

    rw = QueryRewrite(
        rewritten_query="这份作业算不算学术不端",
        submission_id=SUBMISSION,
        course_id=COURSE,
        assignment_id=ASSIGNMENT,
    )
    rt = RuntimeContext(user_id="stu-001", role="student", course_id=COURSE)
    plan, meta = router.route(rw, rt, history=[])

    assert plan.intent == "academic_integrity_question"
    assert plan.route_kind == "workflow_human"
    assert meta["guard_override"] is True
    assert meta["guard_reason"] == "keyword_guardrail_academic_integrity_question"


def test_online_misclassification_of_appeal_is_corrected() -> None:
    router = IntentRouter()
    wrong = RoutePlanCandidate(
        intent="general_chat",
        route_kind="deterministic",
        confidence=0.9,
    )
    router.llm = SimpleNamespace(structured=lambda *a, **k: wrong)

    rw = QueryRewrite(
        rewritten_query="我要申诉这个成绩",
        submission_id=SUBMISSION,
        course_id=COURSE,
        assignment_id=ASSIGNMENT,
    )
    rt = RuntimeContext(user_id="stu-001", role="student", course_id=COURSE)
    plan, meta = router.route(rw, rt, history=[])

    assert plan.intent == "grade_appeal"
    assert plan.route_kind == "workflow_human"
    assert meta["guard_reason"] == "keyword_guardrail_grade_appeal"
