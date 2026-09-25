"""ApprovalGate：HITL 三道闸 + 单份作业状态机。

状态机：received → draft_graded → flagged → approved → recorded（+ rejected, paused）。

恢复时按顺序经过：
0. 审批授权（approver_role 必须为 instructor，否则 blocked/approver_not_authorized）
   —— 终录 / 最终认定 / 推荐是讲师专属；student / ta 可以发起转交，但不能审批自己或他人的提案
1. resume 令牌校验（无效 → blocked/invalid_resume_token）
2. business_recheck 冻结字段复核（漂移 → blocked/business_fact_drift，返回 drift_field）
3. 幂等键（submission_id + rubric_version + approved_instructor_id + timestamp_bucket）
   重复 → idempotent_replay，不重复副作用

4 个冻结字段：submission_body_hash / rubric_version / similarity_score / submission_timestamp。
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from harness.contracts import (
    GradeGraphState,
    GradingDraft,
    HighRiskProposal,
    SUBMISSION_STATES,
)

# 状态机合法迁移
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "received": {"draft_graded", "paused", "rejected"},
    "draft_graded": {"flagged", "approved", "rejected", "paused", "received"},
    "flagged": {"approved", "rejected", "paused", "received"},
    "approved": {"recorded", "paused", "received"},
    "recorded": set(),
    "rejected": set(),
    "paused": {"draft_graded", "flagged", "approved", "rejected", "received"},
}

FROZEN_FIELDS = (
    "submission_body_hash",
    "rubric_version",
    "similarity_score",
    "submission_timestamp",
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApprovalGate:
    """高风险写动作的 HITL 闸。"""

    def __init__(self) -> None:
        # resume_token -> checkpoint
        self._checkpoints: dict[str, dict[str, Any]] = {}
        # idempotency_key -> already-executed result
        self._executed: dict[str, dict[str, Any]] = {}
        # submission_id -> GradeGraphState
        self._states: dict[str, GradeGraphState] = {}

    # ------------------------------------------------------------------
    # 状态机
    # ------------------------------------------------------------------
    def transition(self, state: str, action: str) -> str:
        """简单状态机迁移；非法迁移抛 ValueError。"""
        if action not in _ALLOWED_TRANSITIONS.get(state, set()):
            raise ValueError(f"illegal transition: {state} -> {action}")
        return action

    def get_state(self, submission_id: str) -> Optional[GradeGraphState]:
        return self._states.get(submission_id)

    # ------------------------------------------------------------------
    # 创建 checkpoint（freeze_snapshot + pause_for_human）
    # ------------------------------------------------------------------
    def create_checkpoint(
        self,
        submission_id: str,
        state: str,
        frozen_fields: dict[str, Any],
        proposal: HighRiskProposal,
    ) -> dict[str, Any]:
        """冻结现场并签发 resume_token，进入 pause_for_human。"""
        resume_token = secrets.token_urlsafe(16)
        checkpoint = {
            "submission_id": submission_id,
            "state": state,
            "frozen_fields": {k: frozen_fields.get(k) for k in FROZEN_FIELDS},
            "proposal": proposal.model_dump(),
            "resume_token": resume_token,
            "created_at": _now_iso(),
            "approved_instructor_id": None,
        }
        self._checkpoints[resume_token] = checkpoint
        self._states[submission_id] = {
            "submission_id": submission_id,
            "state": state,  # type: ignore[typeddict-item]
            "draft": None,
            "draft_score": None,
            "draft_feedback": None,
            "flagged_reasons": [],
            "frozen_fields": checkpoint["frozen_fields"],
            "history": [{"event": "checkpoint_created", "at": checkpoint["created_at"]}],
        }
        return checkpoint

    # ------------------------------------------------------------------
    # business_recheck：恢复时重新拉现场
    # ------------------------------------------------------------------
    def business_recheck(
        self,
        checkpoint: dict[str, Any],
        current_frozen: dict[str, Any],
    ) -> dict[str, Any]:
        """逐字段比对冻结值与当前值。任一漂移即失败。"""
        frozen = checkpoint["frozen_fields"]
        mismatches: dict[str, Any] = {}
        for field in FROZEN_FIELDS:
            if field not in frozen:
                continue
            old = frozen.get(field)
            new = current_frozen.get(field)
            if old != new:
                mismatches[field] = {"frozen": old, "current": new}
        return {
            "passed": not mismatches,
            "reason": None if not mismatches else "business_fact_drift",
            "drift_field": next(iter(mismatches), None),
            "mismatches": mismatches,
        }

    # ------------------------------------------------------------------
    # resume：三道闸
    # ------------------------------------------------------------------
    def resume(
        self,
        resume_token: str,
        approved_action: str,
        *,
        approved_instructor_id: str,
        current_frozen: dict[str, Any],
        timestamp_bucket: str,
        approver_role: str = "instructor",
    ) -> dict[str, Any]:
        """恢复暂停的审批；approved_action ∈ {approved, rejected, needs_more_info}。

        顺序：授权（仅 instructor）→ 1. resume 令牌 → 2. business_recheck → 3. 幂等键。
        """
        # 闸 1：resume 令牌
        checkpoint = self._checkpoints.get(resume_token)
        if checkpoint is None:
            return {
                "status": "blocked",
                "reason": "invalid_resume_token",
                "accepted": False,
                "idempotent_replay": False,
            }

        # 闸 0：审批授权。终录 / 最终认定 / 推荐是 instructor 专属；
        # student / ta 可发起转交，但不能审批（gate 默认 instructor，安全缺省）。
        if approver_role != "instructor":
            return {
                "status": "blocked",
                "reason": "approver_not_authorized",
                "accepted": False,
                "idempotent_replay": False,
            }

        # 闸 2：business_recheck
        recheck = self.business_recheck(checkpoint, current_frozen)
        if not recheck["passed"]:
            return {
                "status": "blocked",
                "reason": "business_fact_drift",
                "drift_field": recheck["drift_field"],
                "mismatches": recheck["mismatches"],
                "accepted": False,
                "idempotent_replay": False,
            }

        # 闸 3：幂等键
        submission_id = checkpoint["submission_id"]
        rubric_version = checkpoint["frozen_fields"].get("rubric_version", "")
        idempotency_key = _sha256(
            f"{submission_id}|{rubric_version}|{approved_instructor_id}|{timestamp_bucket}"
        )
        if idempotency_key in self._executed:
            return {
                "status": "idempotent_replay",
                "reason": "idempotent_replay",
                "accepted": True,
                "idempotent_replay": True,
                "executed": self._executed[idempotency_key],
            }

        # 执行（只在 approval gate 内；不直连 LMS 写）
        # 状态机：当前态 → approved → recorded（两步在一次 resume 内完成）
        if approved_action == "approved":
            self.transition(checkpoint["state"], "approved")  # 第一步：批准
            new_state = self.transition("approved", "recorded")  # 第二步：执行录分
            result = {
                "status": "recorded",
                "reason": "approval_recorded",
                "accepted": True,
                "idempotent_replay": False,
                "proposal": checkpoint["proposal"],
            }
        elif approved_action == "rejected":
            new_state = self.transition(checkpoint["state"], "rejected")
            result = {
                "status": "rejected",
                "reason": "approval_rejected",
                "accepted": False,
                "idempotent_replay": False,
            }
        else:  # needs_more_info
            new_state = self.transition(checkpoint["state"], "paused")
            result = {
                "status": "paused",
                "reason": "needs_more_info",
                "accepted": False,
                "idempotent_replay": False,
            }

        self._executed[idempotency_key] = result
        if submission_id in self._states:
            self._states[submission_id]["state"] = new_state  # type: ignore[typeddict-item]
            self._states[submission_id]["history"].append(
                {"event": "resumed", "action": approved_action, "at": _now_iso()}
            )
        return result

    # ------------------------------------------------------------------
    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """列出仍在 pause_for_human 的 checkpoint。"""
        out = []
        for token, cp in self._checkpoints.items():
            state = self._states.get(cp["submission_id"], {})
            if state.get("state") in {"flagged", "draft_graded", "paused"}:
                out.append(
                    {
                        "resume_token": token,
                        "submission_id": cp["submission_id"],
                        "action": cp["proposal"]["action"],
                        "state": state.get("state"),
                    }
                )
        return out
