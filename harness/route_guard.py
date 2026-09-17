"""route_guard：plan → act 之间的一票否决闸。

rule_guard(intent, runtime_context) -> (blocked, reason)
    安全 / 权限 / 高风险边界一票否决。
rule_veto(route_plan, runtime_context) -> (blocked, reason)
    route_kind 与角色不匹配时 veto。
"""

from __future__ import annotations

from typing import Any

from harness.contracts import RoutePlanCandidate, RuntimeContext

_HIGH_RISK_INTENTS = {"grade_appeal", "academic_integrity_question"}


def rule_guard(intent: str, runtime_context: RuntimeContext) -> tuple[bool, str]:
    """返回 (blocked, reason)。blocked=True 时 reason 形如 ``rule_guard_<intent>``。"""
    role = runtime_context.role

    # 1. 安全 / 注入请求 → 直接 block
    if intent == "security_request":
        return True, "rule_guard_security_request"

    # 2. student 越权请求高风险动作
    if role == "student":
        if intent == "batch_grading":
            return True, "rule_guard_batch_grading"
        if intent in {"grade_appeal", "academic_integrity_question"}:
            # student 申诉本身允许，但必须走 workflow_human；不 block，交给 rule_veto
            pass

    # 3. ta 不能直接 record_final_grade / judge_misconduct（这两个是 instructor 专属写动作）
    #    这里 intent 不直接写动作名，由 route_kind 承载；rule_veto 负责。

    # 4. 高风险 intent 强制 workflow_human（由调用方据此改写 route_kind）
    #    返回 (False, reason) 表示"不 block 但要求改写"
    if intent in _HIGH_RISK_INTENTS:
        return False, f"rule_guard_high_risk_{intent}"

    return False, ""


def rule_veto(route_plan: RoutePlanCandidate, runtime_context: RuntimeContext) -> tuple[bool, str]:
    """route_kind 与角色 / 权限不匹配时 veto。"""
    role = runtime_context.role
    intent = route_plan.intent
    kind = route_plan.route_kind

    # student 不能走 task_planner（批量批改）
    if kind == "task_planner" and role != "ta":
        return True, f"rule_veto_{intent}"

    # student / ta 不能走 workflow_human 触发 instructor-only 写动作
    # （record_final_grade / judge_academic_misconduct 必须 instructor）
    if kind == "workflow_human" and route_plan.risk_level == "high":
        if role in {"student", "ta"}:
            return True, f"rule_veto_{intent}"

    # 高风险 intent 必须 workflow_human
    if intent in _HIGH_RISK_INTENTS and kind != "workflow_human":
        return True, f"rule_veto_{intent}"

    return False, ""
