"""GraderAgent：五阶段主 loop（perceive / plan / act / observe / respond）。

模型负责初批提议，规则负责否决，人类教师只在不可逆动作上被叫醒。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from agent.batch_mapreduce import BatchGrader
from agent.final_answer import FinalAnswerComposer
from agent.intent_router import IntentRouter
from agent.llm import get_llm_client
from agent.query_rewrite import QueryRewriter
from agent.react_loop import ReActLoop
from harness.approval_gate import ApprovalGate
from harness.context_builder import ContextBuilder
from harness.contracts import HighRiskProposal, RuntimeContext
from harness.cost import CostGovernor
from harness.hooks import HookManager
from harness.lms_client import LMSClient
from harness.permissions import PermissionError
from harness.source_guard import UNTRUSTED, inspect_source
from harness.tool_runtime import ToolRuntime
from harness.trace import TraceStore, make_event
from rag.hybrid_retrieval import PINNED_DOMAIN, HybridRetriever


def _now_date_bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# 审批通过（recorded）后，按 checkpoint 里的提案动作给出对外话术与已授权动作清单
_RECORDED_ANSWERS = {
    "record_final_grade": "审批通过：{sid} 成绩已录入，草稿评语已对学生公开。",
    "judge_academic_misconduct": "审批通过：{sid} 的学术不端终判已由主讲教师确认并记录。",
    "recommend_deferred_exam": "审批通过：{sid} 的缓考推荐已由主讲教师确认并提交。",
}
_RECORDED_ACTIONS = {
    "record_final_grade": ["record_final_grade", "publish_feedback"],
    "judge_academic_misconduct": ["judge_academic_misconduct"],
    "recommend_deferred_exam": ["recommend_deferred_exam"],
}


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
        # 绑定真实主 loop：批量每份回调 GraderAgent.chat 走真实单份初批
        # （离线 deterministic_score 按 rubric 关键词打分），不再走 72.0 桩。
        self.batch_grader.bind(self.chat)

        # session 级状态
        self._memory: dict[str, dict[str, Any]] = {}
        self._session_resume_token: dict[str, str] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}

    # ==================================================================
    # 主入口
    # ==================================================================
    @staticmethod
    def _llm_snapshot() -> dict[str, float]:
        """LLM 单例计数器快照（调用数 / 累计耗时 / token），供请求前后差值。"""
        llm = get_llm_client()
        return {
            "calls": llm.calls,
            "latency_ms": llm.latency_ms,
            "prompt_tokens": llm.prompt_tokens,
            "completion_tokens": llm.completion_tokens,
        }

    @staticmethod
    def _telemetry(
        t_start: float,
        snap: dict[str, float],
        phases: Optional[dict[str, float]] = None,
    ) -> dict[str, Any]:
        """请求级时延：总耗时 + 真实模型耗时（五阶段分段，早退路径无分段）。"""
        llm = get_llm_client()
        return {
            "schema_version": "grader_latency_v1",
            "total_ms": round((time.perf_counter() - t_start) * 1000, 1),
            "llm_ms": round(llm.latency_ms - snap["latency_ms"], 1),
            "llm_calls": llm.calls - snap["calls"],
            "phases": phases or {},
        }

    def chat(self, request: dict[str, Any]) -> dict[str, Any]:
        session_id = request["session_id"]
        text = request.get("text", "")

        # 请求级遥测基准：总耗时按 wall clock；模型调用 / 耗时 / token 按
        # LLM 单例计数器的请求前后差值（真实在线调用才计数，离线为 0）。
        t_start = time.perf_counter()
        llm_snap = self._llm_snapshot()

        # ---------- 1. perceive ----------
        # 每请求一套 hooks（工具前后 / 错误 / 完成事件进 trace）。
        hooks = HookManager(self.trace_store)
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
        t_perceive = time.perf_counter()

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
                    "source": route_plan.source,
                    "candidate_applied": route_plan.source == "llm_with_policy_constraints",
                },
            )
        )

        # 缓考正式申请升级为 workflow
        if route_plan.intent == "deferred_exam_query" and any(
            k in text for k in ("申请", "提交", "推荐")
        ):
            route_plan = self._escalate_deferred_exam(route_plan, rt)
        t_plan = time.perf_counter()

        # ---------- 3. act ----------
        tool_results: list[dict[str, Any]] = []
        rag_results: list[dict[str, Any]] = []
        tool_obs: list[dict[str, Any]] = []
        batch_state: Optional[dict[str, Any]] = None
        pending_approval: Optional[dict[str, Any]] = None

        tool_args = self._tool_args(request, rewrite, rt)

        # RAG 检索是否命中实例级缓存（rag 分支才会用到，其余分支为 False）
        rag_cache_hit = False

        try:
            if route_plan.route_kind == "tool_readonly":
                react = self.react_loop.run(
                    route_plan, rt, tool_args, hooks=hooks, session_id=session_id
                )
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
                rag_results, rag_cache_hit = self.retriever.retrieve(
                    rewrite.rewritten_query, route_plan.intent
                )
                if rag_cache_hit:
                    self.trace_store.add(
                        make_event(
                            "cache_hit",
                            session_id,
                            {
                                "intent": route_plan.intent,
                                "domains": list({r["domain"] for r in rag_results}),
                            },
                        )
                    )
                self.trace_store.add(
                    make_event(
                        "rag_retrieved",
                        session_id,
                        {
                            "domains": list({r["domain"] for r in rag_results}),
                            "cache_hit": rag_cache_hit,
                        },
                    )
                )
            elif route_plan.route_kind == "workflow_human":
                pending_approval, pinned = self._act_workflow(
                    route_plan, rt, tool_args, session_id
                )
                if pinned:
                    # 高风险学术诚信分支：把直挂政策 citation 并入检索结果，
                    # 由 FinalAnswerComposer 统一映射为对外 citations。
                    rag_results = [pinned]
            elif route_plan.route_kind == "task_planner":
                batch_state = self._run_batch(
                    route_plan, rt, request, session_id
                )
            # deterministic / deterministic_fallback / deterministic_block：无工具
        except PermissionError as exc:
            self.trace_store.add(
                make_event("permission_denied", session_id, {"error": str(exc)})
            )
            return self._deny_response(session_id, route_plan, rt, str(exc), t_start, llm_snap)
        except Exception as exc:  # noqa: BLE001
            # 单条坏输入（如模型产出畸形计划 / 工具名）不得冒泡成 HTTP 500：
            # 记录可观测事件后降级直答，实现请求级隔离，不影响其他会话。
            self.trace_store.add(
                make_event(
                    "act_degraded",
                    session_id,
                    {"error_type": type(exc).__name__, "error": str(exc)[:200]},
                )
            )
            return self._degraded_response(session_id, route_plan, t_start, llm_snap)
        t_act = time.perf_counter()

        # ---------- 4. observe ----------
        observe_ctx = self.context_builder.build(
            rt,
            history=self._history.get(session_id, []),
            tool_results=tool_results,
            rag_results=rag_results,
            memory=mem,
        )
        # context_report：本轮上下文用了哪些来源、冲突如何裁定，写入公开 trace
        self.trace_store.add(
            make_event(
                "context_report",
                session_id,
                {
                    "trust_order": observe_ctx.get("trust_order"),
                    "conflicts": observe_ctx.get("conflicts"),
                    "history_items": len(observe_ctx.get("history", [])),
                    "tool_facts": len(tool_results),
                    "rag_chunks": len(rag_results),
                },
            )
        )
        t_observe = time.perf_counter()

        # ---------- 5. respond ----------
        composed = self.final_composer.compose(
            route_plan, rt, tool_results, rag_results, cache_hit=rag_cache_hit,
            batch_state=batch_state, context=observe_ctx,
        )

        # RAG 缓存命中：respond 阶段跳过最终模型润色（离线本就不走模型，
        # 在线时这里确保不重复调 llm.generate）
        if rag_cache_hit and route_plan.route_kind == "rag":
            self.trace_store.add(
                make_event(
                    "model_answer_skipped",
                    session_id,
                    {"reason": "rag_cache_hit", "intent": route_plan.intent},
                )
            )

        # grading_request：把 proposal 落 checkpoint（HITL）
        if route_plan.intent == "grading_request" and composed.get("proposal"):
            pending_approval = self._open_checkpoint(
                composed["proposal"], session_id, state="draft_graded",
                course_id=request.get("course_id"),
            )
            composed["pending_approval"] = pending_approval

        answer = composed["answer"]
        # on_completion 在构建响应前 fire，保证事件进入当轮 trace_events
        hooks.fire(
            "on_completion",
            session_id=session_id,
            intent=route_plan.intent,
            route_kind=route_plan.route_kind,
            next_action=composed.get("next_action", "answer_user"),
        )
        t_respond = time.perf_counter()

        # 时延与成本：respond 之后统计，把最终模型生成（在线润色 / 结构化初批）
        # 一并计入本请求；安全边界不变——只记账，不跳业务事实与 HITL。
        phases = {
            "perceive_ms": round((t_perceive - t_start) * 1000, 1),
            "plan_ms": round((t_plan - t_perceive) * 1000, 1),
            "act_ms": round((t_act - t_plan) * 1000, 1),
            "observe_ms": round((t_observe - t_act) * 1000, 1),
            "respond_ms": round((t_respond - t_observe) * 1000, 1),
        }
        latency = self._telemetry(t_start, llm_snap, phases)
        llm_now = self._llm_snapshot()
        cost_summary = self.cost.build_cost_summary(
            tool_calls=len(tool_results),
            llm_calls=llm_now["calls"] - llm_snap["calls"],
            tokens=len(text),
            llm_latency_ms=llm_now["latency_ms"] - llm_snap["latency_ms"],
            prompt_tokens=llm_now["prompt_tokens"] - llm_snap["prompt_tokens"],
            completion_tokens=llm_now["completion_tokens"] - llm_snap["completion_tokens"],
        )

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
            "latency": latency,
            "session_state": {
                "routing": {
                    "intent": route_plan.intent,
                    "route_kind": route_plan.route_kind,
                    "guard_override": guard_meta["guard_override"],
                    "guard_reason": guard_meta["guard_reason"],
                    "guard_chain": guard_meta.get("chain", []),
                    "confidence": route_plan.confidence,
                    "source": route_plan.source,
                    "candidate_applied": route_plan.source == "llm_with_policy_constraints",
                },
                # plan 阶段的结构化改写与最终计划：供调试台展示"模型提议了什么"
                "plan": {
                    "rewritten_query": rewrite.rewritten_query,
                    "sub_questions": rewrite.sub_questions,
                    "entities": {
                        "submission_id": rewrite.submission_id,
                        "course_id": rewrite.course_id,
                        "assignment_id": rewrite.assignment_id,
                    },
                    "confidence": route_plan.confidence,
                    "source": route_plan.source,
                    "candidate_applied": route_plan.source == "llm_with_policy_constraints",
                    "required_tools": route_plan.required_tools,
                    "knowledge_domains": route_plan.knowledge_domains,
                    "risk_level": route_plan.risk_level,
                    "fallback_policy": route_plan.fallback_policy,
                },
                "rag": {"cache_hit": rag_cache_hit},
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

        # 审批授权闸：以 LMS 授课名单快照仲裁审批人角色。
        # student / ta 可以发起立案，但终录 / 终判 / 缓考推荐仅 instructor 可审批。
        course_id = checkpoint.get("course_id") or request.get("course_id") or "CS101-2026spring"
        roster = self.lms.get_instructor_roster(course_id) or {}
        if roster.get("instructor_id") == instructor_id:
            approver_role = "instructor"
        elif instructor_id in (roster.get("ta_ids") or []):
            approver_role = "ta"
        elif instructor_id in (roster.get("student_ids") or []):
            approver_role = "student"
        else:
            approver_role = "unknown"

        current_frozen = self._freeze_from_lms(submission_id)

        result = self.approval_gate.resume(
            resume_token,
            gate_action,
            approved_instructor_id=instructor_id,
            current_frozen=current_frozen,
            timestamp_bucket=_now_date_bucket(),
            approver_role=approver_role,
        )

        if result.get("reason") == "approver_not_authorized":
            self.trace_store.add(
                make_event(
                    "approver_authorization_denied",
                    session_id,
                    {"approver_role": approver_role, "gate_action": gate_action},
                )
            )
            pending_state = checkpoint.get("state")
            return {
                "session_id": session_id,
                "answer": (
                    "审批被拒：终录成绩 / 学术不端终判 / 缓考推荐仅主讲教师有权审批。"
                    "立案已保留，将转主讲教师处理。"
                ),
                "status": "blocked",
                "reason": "approver_not_authorized",
                "idempotent_replay": False,
                "recorded_actions": [],
                "workflow": {"state": pending_state},
                "session_state": {
                    "workflow": {"state": pending_state, "pending_action": "require_instructor_approval"}
                },
            }

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
            proposal_action = checkpoint["proposal"]["action"]
            answer = _RECORDED_ANSWERS.get(
                proposal_action, "审批通过：{sid} 的高风险动作已执行。"
            ).format(sid=submission_id)
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
                _RECORDED_ACTIONS.get(checkpoint["proposal"]["action"], [])
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
    ) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
        submission_id = tool_args.get("submission_id") or "S1001"
        if route_plan.intent == "deferred_exam_query":
            action = "recommend_deferred_exam"
        elif route_plan.intent == "grade_appeal":
            # 成绩申诉可能改分，对应终录动作；学术不端疑问对应学术不端终判
            action = "record_final_grade"
        else:
            # academic_integrity_question 默认
            action = "judge_academic_misconduct"
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
        pending = self._open_checkpoint(
            proposal, session_id, state="flagged",
            course_id=tool_args.get("course_id"),
        )

        # 高风险学术诚信分支（成绩申诉 / 学术不端疑问）：确定性直挂政策 citation。
        # 政策是必须逐条完整呈现的硬约束，不参与向量相似度召回，因此在这里
        # 确定性 append 一条 pinned citation，并入 response.citations 与 trace。
        pinned: Optional[dict[str, Any]] = None
        if route_plan.intent in {"grade_appeal", "academic_integrity_question"}:
            pinned = {
                "chunk_id": PINNED_DOMAIN,
                "text": "",
                "domain": PINNED_DOMAIN,
                "score": 1.0,
                "pinned": True,
                "metadata": {
                    "policy_id": "academic_integrity",
                    "scene_key": "policy",
                    "title": "academic_integrity",
                },
            }
            self.trace_store.add(
                make_event(
                    "policy_citation_pinned",
                    session_id,
                    {
                        "domain": PINNED_DOMAIN,
                        "pinned": True,
                        "retrieval_stage": "pre_retrieval",
                        "policy_id": "academic_integrity",
                    },
                )
            )
        return pending, pinned

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
        course_id: Optional[str] = None,
    ) -> dict[str, Any]:
        cp = self.approval_gate.create_checkpoint(
            submission_id=proposal.submission_id,
            state=state,  # type: ignore[arg-type]
            frozen_fields=proposal.frozen_fields,
            proposal=proposal,
        )
        # 记录课程，供 resume 时按授课名单仲裁审批人角色
        if course_id:
            cp["course_id"] = course_id
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
        self,
        session_id: str,
        route_plan: Any,
        rt: RuntimeContext,
        reason: str,
        t_start: float,
        llm_snap: dict[str, float],
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
            "latency": self._telemetry(t_start, llm_snap),
            "session_state": {"routing": {"guard_override": True, "guard_reason": reason}},
        }

    def _degraded_response(
        self,
        session_id: str,
        route_plan: Any,
        t_start: float,
        llm_snap: dict[str, float],
    ) -> dict[str, Any]:
        """act 阶段未预期异常的降级响应：HTTP 200，不产草稿 / 不开审批。"""
        return {
            "session_id": session_id,
            "answer": "暂时无法处理这个请求，请稍后再试或联系助教 / 主讲教师。",
            "signals": ["degraded", "act_degraded"],
            "intent": route_plan.intent,
            "route_kind": "deterministic",
            "grading_draft": None,
            "pending_approval": None,
            "trace_events": [e.model_dump() for e in self.trace_store.list(session_id)],
            "citations": [],
            "next_action": "degraded",
            "needs_human_approval": False,
            "latency": self._telemetry(t_start, llm_snap),
            "session_state": {"system": {"degraded": True}},
        }


# 进程级单例
grader_agent: Optional[GraderAgent] = None


def get_grader_agent() -> GraderAgent:
    global grader_agent
    if grader_agent is None:
        grader_agent = GraderAgent()
    return grader_agent
