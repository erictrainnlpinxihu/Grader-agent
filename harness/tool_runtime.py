"""ToolRuntime：6 个只读工具白名单 + 4 个高风险写动作提案器。

4 个写动作**不实现为工具**，物理上不在 ReAct 工具表；只产 HighRiskProposal 进 HITL。
"""

from __future__ import annotations

from typing import Any, Optional

from harness.contracts import (
    HIGH_RISK_ACTIONS,
    HighRiskProposal,
    RuntimeContext,
)
from harness.lms_client import LMSClient
from harness.permissions import PermissionError, can_query_any_grade


# 6 个只读白名单工具
READONLY_TOOL_WHITELIST = {
    "list_submissions",
    "get_submission",
    "get_rubric",
    "get_student_history",
    "check_similarity",
    "get_submission_timestamp",
}


class ToolRuntime:
    """只读工具运行时 + 高风险提案器。"""

    def __init__(self, lms: Optional[LMSClient] = None) -> None:
        self.lms = lms or LMSClient()

    # ------------------------------------------------------------------
    # 6 个只读工具函数
    # ------------------------------------------------------------------
    def list_submissions(self, args: dict[str, Any], rt: RuntimeContext) -> dict[str, Any]:
        return {
            "items": self.lms.list_submissions(
                args["course_id"], args["assignment_id"]
            )
        }

    def get_submission(self, args: dict[str, Any], rt: RuntimeContext) -> dict[str, Any]:
        sub = self.lms.get_submission(args["submission_id"]) or {}
        # 学生只能查自己的提交
        if rt.role == "student" and sub.get("student_id") != rt.user_id:
            raise PermissionError(
                f"student {rt.user_id} cannot view submission {args['submission_id']} owned by {sub.get('student_id')}"
            )
        return sub

    def get_rubric(self, args: dict[str, Any], rt: RuntimeContext) -> dict[str, Any]:
        return self.lms.get_rubric(args["assignment_id"], args.get("rubric_version", "v1.0")) or {}

    def get_student_history(self, args: dict[str, Any], rt: RuntimeContext) -> dict[str, Any]:
        sid = args["student_id"]
        # 学生只能查自己的历史
        if rt.role == "student" and sid != rt.user_id:
            raise PermissionError(f"student {rt.user_id} cannot view history of {sid}")
        return {"items": self.lms.get_student_history(sid, args["course_id"])}

    def check_similarity(self, args: dict[str, Any], rt: RuntimeContext) -> dict[str, Any]:
        return self.lms.check_similarity(args["submission_id"])

    def get_submission_timestamp(self, args: dict[str, Any], rt: RuntimeContext) -> dict[str, Any]:
        ts = self.lms.get_submission_timestamp(args["submission_id"])
        return {"submission_id": args["submission_id"], "submitted_at": ts}

    # ------------------------------------------------------------------
    # execute：白名单 + 权限 + 对账
    # ------------------------------------------------------------------
    def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        runtime_context: RuntimeContext,
        required_tools: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        # 1. 白名单
        if tool_name not in READONLY_TOOL_WHITELIST:
            raise PermissionError(f"tool {tool_name} not in readonly whitelist")

        # 2. 对账：RoutePlan.required_tools 必须包含该工具
        if required_tools is not None and tool_name not in required_tools:
            raise PermissionError(
                f"tool {tool_name} not declared in RoutePlan.required_tools={required_tools}"
            )

        # 3. 权限
        handler = getattr(self, tool_name)
        return handler(args, runtime_context)

    # ------------------------------------------------------------------
    # 4 个高风险写动作：只产 HighRiskProposal，不执行
    # ------------------------------------------------------------------
    def propose(
        self,
        action: HIGH_RISK_ACTIONS,
        submission_id: str,
        payload: dict[str, Any],
        frozen_fields: dict[str, Any],
    ) -> HighRiskProposal:
        return HighRiskProposal(
            action=action,
            submission_id=submission_id,
            proposed_payload=payload,
            frozen_fields=frozen_fields,
            pending_instructor_approval=True,
        )
