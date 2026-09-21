"""路由 / 执行层加固回归测试。

覆盖线上 500（模型自填 grade_submission 工具）的多层防御：
1. 契约层把 dict / JSON 字符串工具归一为纯工具名；
2. 在线路由只采信模型 intent，执行计划一律走确定性 intent 映射；
3. 执行层对非白名单工具只剥离 + 留痕，绝不裸抛；
4. student 不能发起初批（rule_veto 降级转交），ta / instructor 正常；
5. HTTP 层两种角色都返回 200，不再 500。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent.intent_router import IntentRouter
from agent.loop import GraderAgent
from agent.react_loop import ReActLoop
from harness.contracts import QueryRewrite, RoutePlanCandidate, RuntimeContext
from harness.tool_runtime import ToolRuntime


def _rewrite(text: str = "帮我批一下 S1001") -> QueryRewrite:
    return QueryRewrite(
        rewritten_query=text,
        submission_id=SUBMISSION,
        course_id=COURSE,
        assignment_id=ASSIGNMENT,
    )

COURSE = "CS101-2026spring"
ASSIGNMENT = "A3"
SUBMISSION = "S1001"

GRADING_TOOLS = {
    "get_submission",
    "get_rubric",
    "check_similarity",
    "get_student_history",
}


def _rt(user_id: str, role: str) -> RuntimeContext:
    return RuntimeContext(user_id=user_id, role=role, course_id=COURSE)


# ---------------------------------------------------------------------------
# 1. 契约层：工具字段形状规范化
# ---------------------------------------------------------------------------
def test_contract_normalizes_tool_shapes() -> None:
    plan = RoutePlanCandidate(
        intent="grading_request",
        route_kind="tool_readonly",
        confidence=0.9,
        needs_business_tools=True,
        required_tools=[
            {"name": "get_submission", "args": {"submission_id": SUBMISSION}},
            '{"name": "grade_submission", "args": {"submission_id": "S1001"}}',
            "get_rubric",
            123,  # 非法元素，丢弃
        ],
    )
    assert plan.required_tools == [
        "get_submission",
        "grade_submission",
        "get_rubric",
    ]
    assert all(isinstance(n, str) for n in plan.required_tools)


# ---------------------------------------------------------------------------
# 2. 在线路由：只采信 intent，模型自填工具 / 路由类型 / 风险一律忽略
# ---------------------------------------------------------------------------
def test_online_route_ignores_model_declared_tools() -> None:
    router = IntentRouter()
    malicious = RoutePlanCandidate(
        intent="grading_request",
        route_kind="tool_readonly",
        confidence=0.95,
        needs_business_tools=True,
        required_tools=[
            '{"name": "grade_submission", "args": {"submission_id": "S1001"}}',
            "get_submission",
        ],
    )
    router.llm = SimpleNamespace(structured=lambda *a, **k: malicious)

    plan, _rw = router.route(_rewrite(), _rt("ta-001", "ta"), history=[])

    assert plan.intent == "grading_request"
    assert plan.route_kind == "tool_readonly"
    assert "grade_submission" not in plan.required_tools
    assert set(plan.required_tools) == GRADING_TOOLS


def test_online_low_confidence_falls_back() -> None:
    router = IntentRouter()
    weak = RoutePlanCandidate(
        intent="grading_request",
        route_kind="tool_readonly",
        confidence=0.3,
        needs_business_tools=True,
        required_tools=["get_submission"],
    )
    router.llm = SimpleNamespace(structured=lambda *a, **k: weak)

    plan, _rw = router.route(_rewrite(), _rt("ta-001", "ta"), history=[])
    assert plan.intent == "low_confidence_query"
    assert plan.route_kind == "deterministic_fallback"


# ---------------------------------------------------------------------------
# 3. 执行层：非白名单工具剥离 + 留痕，不抛异常
# ---------------------------------------------------------------------------
def test_react_loop_strips_non_whitelisted_tool() -> None:
    rt = _rt("ta-001", "ta")
    plan = RoutePlanCandidate(
        intent="grading_request",
        route_kind="tool_readonly",
        confidence=1.0,
        needs_business_tools=True,
        required_tools=["get_submission"],
    )
    # 直接赋值绕过 validator，模拟任何上游漏网的畸形计划
    plan.required_tools = [
        "get_submission",
        {"name": "grade_submission", "args": {}},
        "record_final_grade",
    ]

    out = ReActLoop(ToolRuntime()).run(
        plan,
        rt,
        {"submission_id": SUBMISSION, "course_id": COURSE, "assignment_id": ASSIGNMENT},
    )

    assert "grade_submission" not in out["tool_names_called"]
    assert "record_final_grade" not in out["tool_names_called"]
    assert "get_submission" in out["tool_names_called"]
    blocked = [o for o in out["observations"] if o.get("status") == "blocked_not_whitelisted"]
    assert len(blocked) == 2


# ---------------------------------------------------------------------------
# 4. agent 级：student 被 veto 转交，ta 正常初批
# ---------------------------------------------------------------------------
def test_student_grading_is_forwarded_not_drafted() -> None:
    agent = GraderAgent()
    resp = agent.chat(
        {
            "session_id": "s-student",
            "user_id": "stu-001",
            "course_id": COURSE,
            "assignment_id": ASSIGNMENT,
            "submission_id": SUBMISSION,
            "text": "帮我批一下 S1001",
        }
    )
    assert resp["grading_draft"] is None
    assert resp["pending_approval"] is None
    assert resp["route_kind"] == "deterministic"
    assert "grading_request_forwarded" in resp["signals"]


def test_ta_grading_end_to_end_draft() -> None:
    agent = GraderAgent()
    resp = agent.chat(
        {
            "session_id": "s-ta",
            "user_id": "ta-001",
            "course_id": COURSE,
            "assignment_id": ASSIGNMENT,
            "submission_id": SUBMISSION,
            "text": "帮我批一下 S1001",
        }
    )
    assert resp["grading_draft"] is not None
    assert resp["grading_draft"]["overall_score"] is not None
    assert resp["pending_approval"] is not None
    assert resp["pending_approval"]["state"] == "draft_graded"
    assert resp["needs_human_approval"] is True


def test_online_malicious_tool_does_not_break_ta_grading(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = GraderAgent()
    malicious = RoutePlanCandidate(
        intent="grading_request",
        route_kind="tool_readonly",
        confidence=0.99,
        needs_business_tools=True,
        required_tools=['{"name": "grade_submission", "args": {"submission_id": "S1001"}}'],
    )
    monkeypatch.setattr(agent.intent_router.llm, "structured", lambda *a, **k: malicious)

    resp = agent.chat(
        {
            "session_id": "s-ta-online",
            "user_id": "ta-001",
            "course_id": COURSE,
            "assignment_id": ASSIGNMENT,
            "submission_id": SUBMISSION,
            "text": "帮我批一下 S1001",
        }
    )
    # 模型发明的写工具被忽略，权威只读计划照常产出草稿，且无降级 / 500
    assert resp["grading_draft"] is not None
    assert "act_degraded" not in resp["signals"]
    assert resp["next_action"] == "require_approval"


# ---------------------------------------------------------------------------
# 5. HTTP 层：两种角色都 200，不再 500
# ---------------------------------------------------------------------------
@pytest.fixture()
def client() -> TestClient:
    from api.routes import create_app

    return TestClient(create_app())


def _chat_body(session_id: str, user_id: str) -> dict:
    return {
        "session_id": session_id,
        "user_id": user_id,
        "course_id": COURSE,
        "assignment_id": ASSIGNMENT,
        "submission_id": SUBMISSION,
        "text": "帮我批一下 S1001",
    }


def test_api_ta_grading_returns_200_with_draft(client: TestClient) -> None:
    r = client.post("/chat", json=_chat_body("api-ta", "ta-001"))
    assert r.status_code == 200
    data = r.json()
    assert data["grading_draft"] is not None
    assert data["pending_approval"]["state"] == "draft_graded"


def test_api_student_grading_returns_200_forwarded(client: TestClient) -> None:
    r = client.post("/chat", json=_chat_body("api-stu", "stu-001"))
    assert r.status_code == 200
    data = r.json()
    assert data["grading_draft"] is None
    assert "grading_request_forwarded" in data["signals"]
