"""ContextBuilder：五级信任序 + 冲突仲裁 + 历史压缩。

信任序（数字越小越可信）：
    1. runtime_context（LMS 身份快照）  → Trusted
    2. verified_tool_fact（6 只读工具返回，已对账） → Semi-trusted
    3. memory（长期记忆：rubric 偏好 / batch 进度） → Semi-trusted 偏低
    4. history（对话历史窗口） → 偏低
    5. user_message + 学生作业正文 / 申诉 / 聊天输入 → Untrusted

冲突仲裁：LMS 快照 > 用户自称。
"""

from __future__ import annotations

from typing import Any, Optional

from harness.contracts import RuntimeContext
from harness.trace import _sanitize_value


TRUST_ORDER = [
    "runtime_context",
    "verified_tool_fact",
    "memory",
    "history",
    "user_message",
]


class ContextBuilder:
    """按信任序组装上下文，并做冲突仲裁与历史压缩。"""

    def build(
        self,
        runtime_context: RuntimeContext,
        history: Optional[list[dict[str, Any]]] = None,
        tool_results: Optional[list[dict[str, Any]]] = None,
        rag_results: Optional[list[dict[str, Any]]] = None,
        memory: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        history = history or []
        tool_results = tool_results or []
        rag_results = rag_results or []
        memory = memory or {}

        compressed_history = self.history_compression(history)

        # 冲突仲裁：用户自报 vs LMS 快照
        conflicts: list[str] = []
        if runtime_context.claimed_role and runtime_context.claimed_role != runtime_context.role:
            conflicts.append("identity_claim_override_rejected")
            runtime_context.identity_conflicts = list(
                set(runtime_context.identity_conflicts + ["identity_claim_override_rejected"])
            )

        ctx = {
            "runtime_context": runtime_context.model_dump(),
            "verified_tool_facts": tool_results,
            "rag_results": rag_results,
            "memory": memory,
            "history": compressed_history,
            "user_message": None,
            "trust_order": TRUST_ORDER,
            "conflicts": conflicts,
        }
        # 隐私脱敏：整个 context 再过一遍 PII 脱敏
        return _sanitize_value(ctx)

    def conflict_arbitration(self, claims: list[dict[str, Any]]) -> str:
        """用户自报 vs LMS 快照冲突时，信任 LMS 快照。

        claims 形如 [{"claim": ..., "snapshot": ...}, ...]
        返回仲裁结果字符串。
        """
        for claim in claims:
            if claim.get("claim") != claim.get("snapshot"):
                return "lms_snapshot_wins"
        return "no_conflict"

    def history_compression(
        self, history: list[dict[str, Any]], token_budget: int = 4000
    ) -> list[dict[str, Any]]:
        """超过 token 预算时压缩最旧的 tool observation。

        粗略按字符数 ÷ 4 估算 token。
        """
        if not history:
            return []
        estimated = sum(len(str(item)) // 4 for item in history)
        if estimated <= token_budget:
            return list(history)

        # 压缩最旧的 tool observation
        out: list[dict[str, Any]] = []
        budget_left = token_budget
        for item in reversed(history):
            cost = len(str(item)) // 4
            if cost <= budget_left:
                out.append(item)
                budget_left -= cost
            elif item.get("type") == "tool_observation":
                out.append({"type": "tool_observation", "compressed": True, "note": "[history-compressed]"})
        out.reverse()
        return out
