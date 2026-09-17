"""GraderAgent：五阶段主 loop（perceive / plan / act / observe / respond）。

模型负责初批提议，规则负责否决，人类教师只在不可逆动作上被叫醒。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.batch_mapreduce import BatchGrader
from agent.final_answer import FinalAnswerComposer
from agent.intent_router import IntentRouter
from agent.query_rewrite import QueryRewriter
from agent.react_loop import ReActLoop
from harness.approval_gate import ApprovalGate
from harness.context_builder import ContextBuilder
from harness.contracts import HighRiskProposal, RuntimeContext
from harness.cost import CostGovernor
from harness.lms_client import LMSClient
from harness.permissions import PermissionError
from harness.source_guard import UNTRUSTED, inspect_source
from harness.tool_runtime import ToolRuntime
from harness.trace import TraceStore, make_event
from rag.hybrid_retrieval import HybridRetriever


def _now_date_bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class GraderAgent:
    """五阶段主 loop。"""

    def __init__(
        self,
        lms: Optional[LMSClient] = None,
        approval_gate: Optional[ApprovalGate] = None,
        trace_store: Optional[TraceStore] = None,
    ) -> None:
        self.lms = lms or LMSClient()
        self.tools = ToolRuntime(self.lms)
        self.retriever = HybridRetriever()
        self.approval_gate = approval_gate or ApprovalGate()
        self.trace_store = trace_store or TraceStore()
        self.context_builder = ContextBuilder()
        self.cost = CostGovernor()
        self.query_rewriter = QueryRewriter()
        self.intent_router = IntentRouter()
        self.react_loop = ReActLoop(self.tools)
        self.final_composer = FinalAnswerComposer()
        self.batch_grader = BatchGrader()

        # session 级状态
        self._memory: dict[str, dict[str, Any]] = {}
        self._session_resume_token: dict[str, str] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}

    # ==================================================================
    # 主入口
    # ==================================================================
    def chat(self, request: dict[str, Any]) -> dict[str, Any]:
        session_id = request["session_id"]
        text = request.get("text", "")

        # ---------- 1. perceive ----------
        rt = self._build_runtime_context(request)
        safety = inspect_source("user_message", text, UNTRUSTED)
        self.trace_store.add(
            make_event("perceive_input_received", session_id, {"role": rt.role})
        )
        self.trace_store.add(
            make_event(
                "context_source_safety_checked",
                session_id,
                {"source_safety": {k: safety[k] for k in ("tainted", "matched_pattern", "length", "sha256")}},
            )
        )

        # ---------- 2. plan ----------
        mem = self._memory.get(session_id, {})
        rewrite = self.query_rewriter.rewrite(text, rt, mem)
        route_plan, guard_meta = self.intent_router.route(
            rewrite, rt, self._history.get(session_id, [])
        )
        if guard_meta["guard_override"]:
            self.trace_store.add(
                make_event(
                    "rule_guard_overridden",
                    session_id,
                    {"guard_reason": guard_meta["guard_reason"]},
                )
            )
        self.trace_store.add(
            make_event(
                "route_planned",
                session_id,
                {
                    "intent": route_plan.intent,
                    "route_kind": route_plan.route_kind,
                    "confidence": route_plan.confidence,
                },
            )
        )

        # 缓考正式申请升级为 workflow
        if route_plan.intent == "deferred_exam_query" and any(
            k in text for k in ("申请", "提交", "推荐")
        ):
            route_plan = self._escalate_deferred_exam(route_plan, rt)

        # ---------- 3. act ----------
        tool_results: list[dict[str, Any]] = []
        rag_results: list[dict[str, Any]] = []
        tool_obs: list[dict[str, Any]] = []
        batch_state: Optional[dict[str, Any]] = None
        pending_approval: Optional[dict[str, Any]] = None

        tool_args = self._tool_args(request, rewrite, rt)

        try:
            if route_plan.route_kind == "tool_readonly":
                react = self.react_loop.run(route_plan, rt, tool_args)
                tool_results = react["tool_results"]
                tool_obs = react["observations"]
                self.trace_store.add(
                    make_event(
                        "tool_called",
                        session_id,
                        {"tools": react["tool_names_called"]},
                    )
                )
            elif route_plan.route_kind == "rag":
                rag_results = self.retriever.retrieve(rewrite.rewritten_query, route_plan.intent)
                self.trace_store.add(
                    make_event(
                        "rag_retrieved",
                        session_id,
                        {"domains": list({r["domain"] for r in rag_results})},
                    )
                )
            elif route_plan.route_kind == "workflow_human":
                pending_approval = self._act_workflow(
                    route_plan, rt, tool_args, session_id
                )
            elif route_plan.route_kind == "task_planner":
                batch_state = self._run_batch(
                    route_plan, rt, request, session_id
                )
            # deterministic / deterministic_fallback / deterministic_block：无工具
        except PermissionError as exc:
            self.trace_store.add(
                make_event("permission_denied", session_id, {"error": str(exc)})
            )
            return self._deny_response(session_id, route_plan, rt, str(exc))

        # ---------- 4. observe ----------
        observe_ctx = self.context_builder.build(
            rt,
            history=self._history.get(session_id, []),
            tool_results=tool_results,
            rag_results=rag_results,
            memory=mem,
        )
        cost_summary = self.cost.build_cost_summary(
            tool_calls=len(tool_results), llm_calls=0, tokens=len(text)
        )

        # ---------- 5. respond ----------
        composed = self.final_composer.compose(
            route_plan, rt, tool_results, rag_results,
        )

        # grading_request：把 proposal 落 checkpoint（HITL）
        if route_plan.intent == "grading_request" and composed.get("proposal"):
            pending_approval = self._open_checkpoint(
                composed["proposal"], session_id, state="draft_graded"
            )
            composed["pending_approval"] = pending_approval

        answer = composed["answer"]
        response: dict[str, Any] = {
            "session_id": session_id,
            "answer": answer,
            "signals": composed["signals"],
            "intent": route_plan.intent,
            "route_kind": route_plan.route_kind,
            "grading_draft": composed.get("grading_draft"),
            "pending_approval": pending_approval or composed.get("pending_approval"),
            "trace_events": [e.model_dump() for e in self.trace_store.list(session_id)],
            "citations": composed.get("citations", []),
            "tool_calls": tool_obs,
            "next_action": composed.get("next_action", "answer_user"),
            "needs_human_approval": composed.get("needs_human_approval", False),
            "session_state": {
                "routing": {
                    "intent": route_plan.intent,
                    "route_kind": route_plan.route_kind,
                    "guard_override": guard_meta["guard_override"],
                    "guard_reason": guard_meta["guard_reason"],
                    "confidence": route_plan.confidence,
                },
                "workflow": self._workflow_state(session_id, pending_approval),
                "batch": batch_state,
                "cost_summary": cost_summary,
            },
            "cost_summary": cost_summary,
        }

        # memory：只白名单存 course/assignment，不存 PII
        self._memory[session_id] = {
            "current_submission_id": tool_args.get("submission_id"),
            "current_assignment_id": tool_args.get("assignment_id"),
        }
        self._history.setdefault(session_id, []).append(
            {"role": "user", "content": text, "type": "user_message"}
        )
        self._history[session_id].append(
            {"role": "assistant", "content": answer, "type": "assistant_message"}
        )
        return response

    # ==================================================================
    # resume（三道闸）
    # ==================================================================
    def resume(self, request: dict[str, Any]) -> dict[str, Any]:
        session_id = request["session_id"]
        resume_token = request["resume_token"]
        approved_action = request.get("approved_action", {}) or {}
        decision = approved_action.get("decision", "approve")
        # 映射 HTTP 决策词 → ApprovalGate 状态词
        decision_map = {"approve": "approved", "reject": "rejected", "approved": "approved", "rejected": "rejected"}
        gate_action = decision_map.get(decision, decision)
        instructor_id = approved_action.get("instructor_id") or request.get("instructor_id") or "ins-001"

        # 闸 2 需要当前冻结现场：重新拉
        checkpoint = None
        for tok, cp in self.approval_gate._checkpoints.items():  # noqa: SLF001
            if tok == resume_token:
                checkpoint = cp
                break
        if checkpoint is None:
            self.trace_store.add(
                make_event("resume_token_rejected", session_id, {"reason": "invalid_resume_token"})
            )
            return {
                "session_id": session_id,
                "answer": "审批失败：resume 令牌无效或已过期。",
                "status": "blocked",
                "reason": "invalid_resume_token",
            }

        submission_id = checkpoint["submission_id"]
        current_frozen = self._freeze_from_lms(submission_id)

        result = self.approval_gate.resume(
            resume_token,
            gate_action,
            approved_instructor_id=instructor_id,
            current_frozen=current_frozen,
            timestamp_bucket=_now_date_bucket(),
        )

        self.trace_store.add(
            make_event(
                "resume_completed",
                session_id,
                {k: v for k, v in result.items() if k in ("status", "reason", "idempotent_replay", "drift_field")},
            )
        )

        if result["status"] == "blocked" and result.get("reason") == "business_fact_drift":
            answer = (
                f"审批被拒：现场发生漂移（{result.get('drift_field')}），"
                "已回到 draft_graded 重新初批。"
            )
        elif result["status"] == "recorded":
            answer = (
                f"审批通过：{submission_id} 成绩已录入，草稿评语已对学生公开。"
            )
        elif result["status"] == "rejected":
            answer = "已退回：主讲教师驳回了本次初批草稿。"
        elif result["status"] == "paused":
            answer = "已暂停：主讲教师要求补充材料，工作流保持暂停。"
        else:
            answer = f"恢复结果：{result['status']}"

        return {
            "session_id": session_id,
            "answer": answer,
            "status": result["status"],
            "reason": result.get("reason"),
            "idempotent_replay": result.get("idempotent_replay", False),
            "recorded_actions": (
                ["record_final_grade", "publish_feedback"]
                if result["status"] == "recorded"
                else []
            ),
            "workflow": {"state": result["status"]},
            "business_recheck": {
                "passed": result["status"] not in {"blocked", "business_fact_drift"},
                "drift_fields": [result.get("drift_field")] if result.get("drift_field") else [],
            },
            "session_state": {"workflow": {"state": result["status"]}},
        }

    # ==================================================================
    # 内部：act 分支
    # ==================================================================
    def _build_runtime_context(self, request: dict[str, Any]) -> RuntimeContext:
        user_id = request["user_id"]
        course_id = request["course_id"]
        claimed = request.get("claimed_role")
        # LMS 授课名单快照仲裁
        roster = self.lms.get_instructor_roster(course_id) or {}
        if roster.get("instructor_id") == user_id:
            actual = "instructor"
        elif user_id in (roster.get("ta_ids") or []):
            actual = "ta"
        elif user_id in (roster.get("student_ids") or []):
            actual = "student"
        else:
            actual = request.get("role", "student")

        rt = RuntimeContext(
            user_id=user_id,
            role=actual,  # type: ignore[arg-type]
            course_id=course_id,
            instructor_in_snapshot=roster.get("instructor_id") == user_id,
            current_page=request.get("current_page", "home"),
            claimed_role=claimed,
        )
        if claimed and claimed != actual:
            rt.identity_conflicts.append("identity_claim_override_rejected")
        return rt

    def _tool_args(self, request: dict[str, Any], rewrite: Any, rt: RuntimeContext) -> dict[str, Any]:
        assignment_id = rewrite.assignment_id or request.get("assignment_id") or "A3"
        submission_id = rewrite.submission_id or request.get("submission_id")
        assignment = self.lms.get_assignment(assignment_id) or {}
        return {
            "course_id": rewrite.course_id or request.get("course_id"),
            "assignment_id": assignment_id,
            "submission_id": submission_id,
            "user_id": rt.user_id,
            "student_id": rt.user_id,
            "rubric_version": assignment.get("rubric_version", "v1.0"),
        }

    def _act_workflow(
        self,
        route_plan: Any,
        rt: RuntimeContext,
        tool_args: dict[str, Any],
        session_id: str,
    ) -> Optional[dict[str, Any]]:
        submission_id = tool_args.get("submission_id") or "S1001"
        action = "judge_academic_misconduct"
        if route_plan.intent == "deferred_exam_query":
            action = "recommend_deferred_exam"
        frozen = self._freeze_from_lms(submission_id)
        proposal = HighRiskProposal(
            action=action,
            submission_id=submission_id,
            proposed_payload={"intent": route_plan.intent},
            frozen_fields=frozen,
        )
        self.trace_store.add(
            make_event(
                "workflow_proposal_created",
                session_id,
                {"action": action, "submission_id": submission_id},
            )
        )
        return self._open_checkpoint(proposal, session_id, state="flagged")

    def _run_batch(
        self,
        route_plan: Any,
        rt: RuntimeContext,
        request: dict[str, Any],
        session_id: str,
    ) -> dict[str, Any]:
        if rt.role not in {"ta", "instructor"}:
            self.trace_store.add(
                make_event("permission_denied", session_id, {"action": "batch_grading"})
            )
            return {"state": "denied"}
        course_id = request["course_id"]
        assignment_id = request.get("assignment_id") or "A3"
        subs = self.lms.list_submissions(course_id, assignment_id)
        sub_ids = [s["submission_id"] for s in subs]
        self.trace_store.add(
            make_event(
                "task_planned",
                session_id,
                {"total": len(sub_ids), "shard_size": 20},
            )
        )
        state = self.batch_grader.run_batch(
            course_id, assignment_id, sub_ids, rt.model_dump(),
        )
        self.trace_store.add(
            make_event(
                "shard_completed",
                session_id,
                {"processed_shards": sum(1 for s in state.shards if s.status == "done")},
            )
        )
        total_shards = len(state.shards)
        return {
            "batch_id": state.batch_id,
            "total_shards": total_shards,
            "shard_size": 20,
            "processed_shards": sum(1 for s in state.shards if s.status == "done"),
            "state": "completed" if state.processed >= state.total else "paused",
            "checkpoint_id": state.next_resume_token,
            "parallelism": 1,
            "total": state.total,
            "processed": state.processed,
            "failed": state.failed,
        }

    def _open_checkpoint(
        self,
        proposal: HighRiskProposal,
        session_id: str,
        state: str,
    ) -> dict[str, Any]:
        cp = self.approval_gate.create_checkpoint(
            submission_id=proposal.submission_id,
            state=state,  # type: ignore[arg-type]
            frozen_fields=proposal.frozen_fields,
            proposal=proposal,
        )
        self._session_resume_token[session_id] = cp["resume_token"]
        self.trace_store.add(
            make_event(
                "workflow_checkpoint_created",
                session_id,
                {
                    "action": proposal.action,
                    "state": state,
                    "submission_id": proposal.submission_id,
                },
            )
        )
        return {
            "resume_token": cp["resume_token"],
            "submission_id": proposal.submission_id,
            "action": proposal.action,
            "state": state,
            "frozen_fields": cp["frozen_fields"],
        }

    def _freeze_from_lms(self, submission_id: str) -> dict[str, Any]:
        sub = self.lms.get_submission(submission_id) or {}
        assignment = self.lms.get_assignment(sub.get("assignment_id", "")) or {}
        return {
            "submission_body_hash": sub.get("body_hash"),
            "rubric_version": sub.get("rubric_version") or assignment.get("rubric_version", "v1.0"),
            "similarity_score": sub.get("similarity_score", 0.0),
            "submission_timestamp": sub.get("submitted_at"),
        }

    def _workflow_state(
        self, session_id: str, pending: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        if not pending:
            st = self.approval_gate.get_state(
                next(
                    (s for s, cp in self.approval_gate._states.items() if True),  # noqa: SLF001
                    "",
                )
            )
            return None
        return {
            "state": pending.get("state"),
            "pending_action": "require_approval",
            "resume_token": pending.get("resume_token"),
        }

    def _escalate_deferred_exam(self, route_plan: Any, rt: RuntimeContext) -> Any:
        from harness.contracts import RoutePlanCandidate

        return RoutePlanCandidate(
            intent="deferred_exam_query",
            route_kind="workflow_human",
            confidence=1.0,
            requires_workflow=True,
            risk_level="high",
            fallback_policy="workflow_first",
        )

    def _deny_response(
        self, session_id: str, route_plan: Any, rt: RuntimeContext, reason: str
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "answer": "该请求因权限不足被拒绝，如需帮助请联系主讲教师。",
            "signals": ["permission_denied"],
            "intent": route_plan.intent,
            "route_kind": route_plan.route_kind,
            "grading_draft": None,
            "pending_approval": None,
            "trace_events": [e.model_dump() for e in self.trace_store.list(session_id)],
            "citations": [],
            "next_action": "blocked",
            "needs_human_approval": False,
            "session_state": {"routing": {"guard_override": True, "guard_reason": reason}},
        }


# 进程级单例
grader_agent: Optional[GraderAgent] = None


def get_grader_agent() -> GraderAgent:
    global grader_agent
    if grader_agent is None:
        grader_agent = GraderAgent()
    return grader_agent
