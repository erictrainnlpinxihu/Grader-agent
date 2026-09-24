"""FinalAnswerComposer：最终答案生成 + 六种 skip final model 场景。

六种 skip：
1. security_blocked        → 确定性拒绝话术
2. deterministic_short_circuit → general_chat / degradation / low_confidence 直答
3. awaiting_human_approval → "已转主讲教师审批"，不调模型
4. tool_empty_or_error     → 降级话术
5. tainted_source_redacted → [tainted-source-redacted]，仍按 rubric 打分
6. cost_budget_truncated   → 跳过最终模型润色，直接拼装

grading_request 分支：产 GradingDraft（离线确定性打分）+ HighRiskProposal(record_final_grade)。
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from agent.llm import get_llm_client
from harness.contracts import (
    GradingDraft,
    GradingDraftItem,
    HighRiskProposal,
    RoutePlanCandidate,
    RuntimeContext,
)
from harness.prompts.loader import render_system_prompt
from harness.source_guard import UNTRUSTED, inspect_source


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def deterministic_score(body: str, rubric_items: list[dict[str, Any]]) -> list[GradingDraftItem]:
    """离线确定性打分：基于正文关键词的启发式（温度 0，可重放）。"""
    items: list[GradingDraftItem] = []
    for it in rubric_items:
        rid = it["rubric_item_id"]
        max_s = float(it["max_score"])
        score = max_s * 0.6  # 基准 60%
        reason = "依据 rubric 条目按正文覆盖度评定"
        if rid == "correctness":
            if "O(n^2)" in body and "O(n log n)" in body:
                score = max_s * 0.8
                reason = "复杂度分析成立，O(n^2) 与 O(n log n) 结论正确"
            else:
                score = max_s * 0.5
                reason = "复杂度分析不完整"
        elif rid == "reasoning":
            if "最坏" in body or "退化" in body:
                score = max_s * 0.72
                reason = "讨论了最坏情况与退化情形"
            else:
                score = max_s * 0.5
                reason = "缺少最坏情况讨论"
        elif rid == "structure":
            score = max_s * 0.8
            reason = "论述结构清晰、术语规范"
        elif rid == "citation":
            if ("没有引用" in body) or ("未引用" in body) or ("没有讨论" in body):
                score = max_s * 0.32
                reason = "正文未引用教材/讲义/文献"
            elif "引用" in body:
                score = max_s * 0.72
                reason = "有引用但可能不完整"
            else:
                score = max_s * 0.5
                reason = "引用情况不明"
        items.append(
            GradingDraftItem(
                rubric_item_id=rid,
                score=round(score, 1),
                max_score=max_s,
                reason=reason,
                cited_chunk_hash=_sha(body[:200]),
            )
        )
    return items


class FinalAnswerComposer:
    """组装最终答案；六种 skip 命中时不调最终模型。"""

    def __init__(self) -> None:
        self.llm = get_llm_client()

    # ------------------------------------------------------------------
    def compose(
        self,
        route_plan: RoutePlanCandidate,
        runtime_context: RuntimeContext,
        tool_results: list[dict[str, Any]],
        rag_results: list[dict[str, Any]],
        trace_events: Optional[list[dict[str, Any]]] = None,
        grading_draft: Optional[GradingDraft] = None,
        cache_hit: bool = False,
        batch_state: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        intent = route_plan.intent
        route_kind = route_plan.route_kind

        # 1. security_blocked
        if route_kind == "deterministic_block" or intent == "security_request":
            return self._blocked()

        # 4. tool_empty_or_error
        tool_ok = any(t.get("status", "success") == "success" for t in tool_results)
        if route_kind == "tool_readonly" and not tool_results:
            return self._tool_empty()
        if route_kind == "tool_readonly" and not tool_ok and intent != "grading_request":
            return self._tool_empty()

        # 2. deterministic_short_circuit
        if route_kind in {"deterministic", "deterministic_fallback"}:
            return self._deterministic(intent, route_plan, tool_results, rag_results)

        # 5. tainted_source_redacted（作业正文被污染仍按 rubric 打分，不回显）
        tainted = any(
            (t.get("safety") or {}).get("tainted")
            for t in tool_results
        )

        # grading_request 分支
        if intent == "grading_request":
            return self._grading(route_plan, tool_results, grading_draft, tainted)

        # workflow_human 分支（已由 loop 创建 checkpoint）
        if route_kind == "workflow_human":
            return self._workflow(intent, rag_results)

        # rag 分支
        if route_kind == "rag":
            return self._rag_answer(
                route_plan, rag_results, tainted, cache_hit=cache_hit, context=context
            )

        # task_planner 由 batch 结果直答（确定性模板，不调最终模型）
        if route_kind == "task_planner":
            return self._batch_answer(batch_state)

        return self._deterministic(intent, route_plan, tool_results, rag_results)

    # ------------------------------------------------------------------
    # grading_request
    # ------------------------------------------------------------------
    def _structured_draft(
        self,
        sub: dict[str, Any],
        rubric: dict[str, Any],
    ) -> Optional[GradingDraft]:
        """在线结构化初批：llm.structured(GradingDraft) 逐 rubric 条目打分。

        作业正文是 Untrusted 输入：命中注入正则时整段不进模型 prompt
        （skip #5 tainted_source_redacted），直接返回 None 走确定性打分；
        离线模式 / 结构化解析失败同样返回 None。
        """
        body = sub.get("body", "")
        safety = inspect_source("submission_body", body, UNTRUSTED)
        if safety["tainted"]:
            return None
        prompt = (
            "你是作业初批助教。按 rubric 逐条打分：每条给 score（不超过 max_score）、"
            "一句理由；总分 overall_score 为各条目之和；引用的作业段落填前 200 字。"
            f"rubric：{rubric.get('items', [])}。作业正文：{body[:2000]}"
        )
        online = self.llm.structured(GradingDraft, prompt)
        return online if isinstance(online, GradingDraft) else None

    def _grading(
        self,
        route_plan: RoutePlanCandidate,
        tool_results: list[dict[str, Any]],
        grading_draft: Optional[GradingDraft],
        tainted: bool,
    ) -> dict[str, Any]:
        sub = next(
            (t["result"] for t in tool_results if t["tool_name"] == "get_submission"),
            {},
        )
        rubric = next(
            (t["result"] for t in tool_results if t["tool_name"] == "get_rubric"),
            {},
        )
        sim = next(
            (t["result"] for t in tool_results if t["tool_name"] == "check_similarity"),
            {},
        )
        if grading_draft is None:
            # 在线主路径：with_structured_output(GradingDraft) 结构化初批；
            # 正文命中注入 / 离线 / 解析失败均返回 None，回落确定性打分。
            grading_draft = self._structured_draft(sub, rubric)
        if grading_draft is None:
            body = sub.get("body", "")
            items = deterministic_score(body, rubric.get("items", []))
            total = round(sum(i.score for i in items), 1)
            flagged = bool(sim.get("flagged")) or tainted
            reasons = []
            if sim.get("flagged"):
                reasons.append("similarity_score 达到红旗阈值")
            if tainted:
                reasons.append("作业正文命中注入，已清洗")
            grading_draft = GradingDraft(
                submission_id=sub.get("submission_id", ""),
                rubric_version=rubric.get("rubric_version", "v1.0"),
                items=items,
                overall_score=total,
                draft_feedback=(
                    "已按 rubric 逐条打分并绑定段落 hash；"
                    "最终成绩须经主讲教师审批后录入。"
                ),
                flagged=flagged,
                flagged_reasons=reasons,
            )

        # HighRiskProposal：record_final_grade
        proposal = HighRiskProposal(
            action="record_final_grade",
            submission_id=grading_draft.submission_id,
            proposed_payload={
                "total_score": grading_draft.overall_score,
                "rubric_version": grading_draft.rubric_version,
                "flagged": grading_draft.flagged,
            },
            frozen_fields={
                "submission_body_hash": sub.get("body_hash"),
                "rubric_version": grading_draft.rubric_version,
                "similarity_score": sim.get("similarity_score", sub.get("similarity_score", 0.0)),
                "submission_timestamp": sub.get("submitted_at"),
            },
        )

        answer = (
            f"已完成初批：总分 {grading_draft.overall_score}/100。"
            "草稿已提交主讲教师确认，确认通过后才会正式录入成绩。"
        )
        if tainted:
            answer = "[tainted-source-redacted] " + answer
        return {
            "answer": answer,
            "signals": ["draft_graded", "require_approval", "tool_readonly"],
            "grading_draft": grading_draft.model_dump(),
            "proposal": proposal,
            "skip_reason": "awaiting_human_approval",
            "next_action": "require_approval",
            "needs_human_approval": True,
            "citations": [],
        }

    # ------------------------------------------------------------------
    def _workflow(self, intent: str, rag_results: list[dict[str, Any]]) -> dict[str, Any]:
        if intent == "grade_appeal":
            answer = "已收到你的申诉，将转交主讲教师复核。申诉期间原判定暂缓执行。"
        elif intent == "deferred_exam_query":
            # 缓考正式申请（loop 内由"申请/提交/推荐"升级而来）：
            # 对应 recommend_deferred_exam 提案，话术不与学术不端串台
            answer = (
                "已收到缓考正式申请，将转交主讲教师审批推荐；"
                "审批通过前不会变更任何考试安排。"
            )
        else:
            answer = "已记录学术不端相关疑问，将转交主讲教师复核证据。系统不自动处分。"
        return {
            "answer": answer,
            "signals": ["workflow_human", "needs_human_approval"],
            "grading_draft": None,
            "proposal": None,
            "skip_reason": "awaiting_human_approval",
            "next_action": "require_approval",
            "needs_human_approval": True,
            "citations": self._citations(rag_results),
        }

    # ------------------------------------------------------------------
    def _rag_answer(
        self,
        route_plan: RoutePlanCandidate,
        rag_results: list[dict[str, Any]],
        tainted: bool,
        cache_hit: bool = False,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not rag_results:
            return self._tool_empty()
        # 离线：拼装 top chunk；在线：LLM 润色（不混入动态学生数据）
        top = rag_results[0]
        snippet = (top.get("text") or top.get("title") or "").strip().splitlines()
        snippet_text = snippet[0] if snippet else top.get("domain", "")
        answer = f"依据{top.get('domain', '相关政策')}：{snippet_text[:160]}"
        if tainted:
            answer = "[tainted-source-redacted] " + answer
        # 缓存命中或离线：跳过最终模型受控表达，直接用确定性模板
        if not cache_hit:
            entities: dict[str, Any] = {}
            if context is not None:
                entities = {k: v for k, v in (context.get("memory") or {}).items() if v}
            # 受控表达：确定性答案为基准，模型只改写表达——不得改变事实、
            # 数字、资格判断、风险等级或下一步动作，不得补充证据之外的信息
            user_prompt = (
                "把下面的确定性答案改写得更自然。只能调整表达方式，不得改变"
                "事实与数字、资格判断、风险等级或下一步动作，不得补充新信息。"
                f"确定性答案：{answer}；可用证据：{rag_results[:2]}"
            )
            if entities:
                user_prompt += f"；当前会话实体：{entities}"
            online = self.llm.generate(
                render_system_prompt({"needs_rag": True, "route_kind": "rag"}),
                user_prompt,
            )
            if online:
                answer = online
        return {
            "answer": answer,
            "signals": ["rag_hit", f"domain:{top.get('domain', 'unknown')}"],
            "grading_draft": None,
            "proposal": None,
            "skip_reason": "rag_cache_hit" if cache_hit else None,
            "next_action": "answer_user",
            "needs_human_approval": False,
            "citations": self._citations(rag_results),
        }

    # ------------------------------------------------------------------
    def _deterministic(
        self,
        intent: str,
        route_plan: RoutePlanCandidate,
        tool_results: list[dict[str, Any]],
        rag_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if intent == "general_chat":
            answer = "你好，我是 Grader 初批助教。你可以让我查作业状态、查 rubric，或请求批改作业。"
            signals = ["general_chat", "deterministic"]
        elif intent == "grading_request":
            # student 发起初批被 rule_veto 降级到此处：不产草稿、不开 checkpoint
            answer = (
                "作业初批由助教或主讲教师完成，我已记录你的请求；"
                "正式成绩须经主讲教师审批后才会录入。你也可以先查询作业状态或评分标准。"
            )
            signals = ["grading_request_forwarded", "deterministic"]
        elif intent == "grade_appeal":
            # 纵深防御：高风险 workflow 若被任何路径降级到 deterministic，
            # 仍给稳定的转人工话术，绝不串台到作业查询或编造结果
            answer = "已收到你的申诉，将转交主讲教师复核。申诉期间原判定暂缓执行。"
            signals = ["workflow_human", "needs_human_approval", "deterministic"]
        elif intent == "academic_integrity_question":
            answer = "已记录学术不端相关疑问，将转交主讲教师复核证据。系统不自动处分。"
            signals = ["workflow_human", "needs_human_approval", "deterministic"]
        elif intent == "low_confidence_query":
            answer = "我没太理解你的问题，能否补充一下是查作业状态、查 rubric，还是请求批改？"
            signals = ["low_confidence", "deterministic_fallback", "ask_clarification"]
        elif intent == "degradation_request":
            answer = "相关系统暂不可用，已切换离线降级模式；核心初批与只读查询仍可用。"
            signals = ["degraded", "deterministic"]
        elif intent == "deferred_exam_query":
            answer = self._rag_answer(route_plan, rag_results, False)["answer"]
            signals = ["rag_hit", "deferred_exam"]
        else:
            # assignment_status_query 走 tool_readonly，这里兜底
            sub = next(
                (t["result"] for t in tool_results if t["tool_name"] == "get_submission"),
                {},
            )
            if sub:
                if sub.get("final_score") is not None:
                    answer = (
                        f"你的作业 {sub.get('submission_id')} 状态为 {sub.get('status')}，"
                        f"总分 {sub.get('final_score')}/100。"
                    )
                else:
                    answer = f"你的作业 {sub.get('submission_id')} 状态为 {sub.get('status')}，尚未录入成绩。"
            else:
                answer = "未查询到对应作业记录。"
            signals = ["assignment_status_query", "tool_readonly"]
            # 在线受控表达：与 RAG 分支同一契约（确定性答案为基准，只改写话术）
            online = self.llm.generate(
                render_system_prompt({"needs_rag": False, "route_kind": "tool_readonly"}),
                "把下面的确定性答案改写得更自然。只能调整表达方式，不得改变事实"
                f"与数字或下一步动作，不得补充新信息。确定性答案：{answer}",
            )
            if online:
                answer = online
        return {
            "answer": answer,
            "signals": signals,
            "grading_draft": None,
            "proposal": None,
            "skip_reason": "deterministic_short_circuit",
            "next_action": "answer_user",
            "needs_human_approval": False,
            "citations": self._citations(rag_results),
        }

    # ------------------------------------------------------------------
    def _batch_answer(self, batch_state: Optional[dict[str, Any]]) -> dict[str, Any]:
        """task_planner 批量初批的确定性直答（skip final model）。"""
        if not batch_state or batch_state.get("state") == "denied":
            answer = "批量初批未执行：该请求已被权限规则拦截，仅助教 / 主讲教师可发起。"
            signals = ["batch_denied", "deterministic"]
        else:
            answer = (
                f"批量初批完成：共 {batch_state.get('total', 0)} 份，"
                f"已处理 {batch_state.get('processed', 0)} 份，"
                f"失败 {batch_state.get('failed', 0)} 份；"
                f"分片 {batch_state.get('processed_shards', 0)}/{batch_state.get('total_shards', 0)}。"
                "每份草稿仍需主讲教师审批后才会录入成绩。"
            )
            signals = ["batch_grading", "task_planner", "deterministic"]
        return {
            "answer": answer,
            "signals": signals,
            "grading_draft": None,
            "proposal": None,
            "skip_reason": "deterministic_short_circuit",
            "next_action": "answer_user",
            "needs_human_approval": False,
            "citations": [],
        }

    def _blocked(self) -> dict[str, Any]:
        return {
            "answer": "该请求已被安全策略拦截，如需帮助请联系主讲教师或助教。",
            "signals": ["security_blocked", "deterministic_block"],
            "grading_draft": None,
            "proposal": None,
            "skip_reason": "security_blocked",
            "next_action": "blocked",
            "needs_human_approval": False,
            "citations": [],
        }

    def _tool_empty(self) -> dict[str, Any]:
        return {
            "answer": "暂时没有查到相关作业数据，请稍后再试或联系助教。",
            "signals": ["tool_empty_or_error"],
            "grading_draft": None,
            "proposal": None,
            "skip_reason": "tool_empty_or_error",
            "next_action": "answer_user",
            "needs_human_approval": False,
            "citations": [],
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _citations(rag_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for r in rag_results[:5]:
            out.append(
                {
                    "source": r.get("domain", "unknown"),
                    "title": (r.get("metadata") or {}).get("title", r.get("chunk_id")),
                    "score": r.get("score", 0.0),
                    "retrieval_stage": "pre_retrieval" if r.get("pinned") else "tool_retrieval",
                }
            )
        return out
