"""route_guard：plan → act 之间的一票否决闸。

权限模型区分两件事：
- **发起权**（chat 阶段）：学生可以申诉成绩、咨询 / 反映学术不端、申请缓考，
  ta 可以提请复核与初批——这些都只产 ``HighRiskProposal`` 并暂停等审批，本身无副作用，
  因此 student / ta 发起高风险 ``workflow_human`` 不在此处被否决。
- **审批 / 执行权**（resume 阶段）：终录成绩、学术不端最终认定、缓考推荐是 instructor 专属，
  由 ``ApprovalGate.resume(approver_role=...)`` 在审批端强制（见 loop.resume 的名单仲裁）。

rule_guard(intent, runtime_context) -> (blocked, reason)
    安全 / 权限 / 高风险边界一票否决。
rule_veto(route_plan, runtime_context) -> (blocked, reason)
    route_kind 与角色不匹配时 veto（只拦"无权发起的动作"，不拦"提交给讲师审批的转交"）。
"""

from __future__ import annotations

from typing import Any, Optional

from harness.contracts import RoutePlanCandidate, RuntimeContext

_HIGH_RISK_INTENTS = {"grade_appeal", "academic_integrity_question"}

# 意图逆向否决：消息的显式信号与当前意图矛盾时采纳显式信号。
# 只覆盖高置信的显式矛盾（否定词 + 明确指向同时命中），拿不准不纠——
# 宁可下一轮澄清，不做投机纠偏。
_EXPLICIT_DENIAL = ("不是批", "别批", "不用批", "先不批", "不是让你批", "不是让你改")
_RUBRIC_SIGNALS = ("rubric", "评分", "怎么评", "怎么给分", "给分标准", "评分标准")
_STATUS_SIGNALS = ("状态", "交了吗", "多少分", "成绩", "批完了吗")


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


def veto_intent(user_message: str, intent: str) -> Optional[str]:
    """逆向否决：消息显式语义与当前意图矛盾时，返回纠正后的意图。

    用户的显式信号 > 模型的猜测：如"只是问 rubric 怎么评，不是让你批"，
    模型给了 grading_request，消息显式否定批改并指向评分标准查询。
    规则刻意保守：仅当否定信号与明确指向同时命中才纠正，否则返回 None。
    """
    if intent != "grading_request":
        return None
    if any(d in user_message for d in _EXPLICIT_DENIAL):
        if any(s in user_message for s in _RUBRIC_SIGNALS):
            return "rubric_query"
        if any(s in user_message for s in _STATUS_SIGNALS):
            return "assignment_status_query"
    return None


def rule_veto(route_plan: RoutePlanCandidate, runtime_context: RuntimeContext) -> tuple[bool, str]:
    """route_kind 与角色 / 权限不匹配时 veto。"""
    role = runtime_context.role
    intent = route_plan.intent
    kind = route_plan.route_kind

    # student 不能走 task_planner（批量批改）；ta / instructor 允许
    if kind == "task_planner" and role not in {"ta", "instructor"}:
        return True, f"rule_veto_{intent}"

    # student 不能发起初批草稿（can_draft_grade 仅 ta / instructor）；
    # 学生说"帮我批"应转交给教学人员，不产草稿、不开审批 checkpoint
    if intent == "grading_request" and role == "student":
        return True, f"rule_veto_{intent}"

    # 注意：grade_appeal / academic_integrity_question 等高风险 workflow_human
    # 允许 student / ta 发起（申诉、反映、提请教职处理只产提案、暂停等讲师审批，无副作用）；
    # instructor 专属的"终录 / 最终认定"约束在审批端 ApprovalGate.resume 强制，
    # 非讲师即便拿到 resume_token 也会被 blocked/approver_not_authorized 拦下。

    # 高风险 intent 必须 workflow_human（防止被错误降级为直答 / RAG 而绕过审批）
    if intent in _HIGH_RISK_INTENTS and kind != "workflow_human":
        return True, f"rule_veto_{intent}"

    return False, ""
