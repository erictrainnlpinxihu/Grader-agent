"""EvalRunner：20 case 离线回归 + 5 项扩展断言。

5 项扩展：
1. consistency_check：双跑分数方差
2. expected_trace_payload：payload 点路径断言
3. resume_fixture_mutation：冻结字段变异后 business_fact_drift
4. offline_expected_signals：离线切换断言集
5. batch.* session_state 点路径

``python -m eval.runner`` 可直接运行。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from agent.loop import GraderAgent
from eval.feedback import FailureAttributor

CASES_PATH = Path(__file__).resolve().parent / "cases.yml"


def _get_dot(obj: dict[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _dot_in(answer: str, needles: list[str]) -> list[str]:
    return [n for n in needles if n not in answer]


class EvalRunner:
    def __init__(self) -> None:
        self.offline = os.environ.get("GRADER_DISABLE_LLM", "") == "1"

    # ------------------------------------------------------------------
    def run(self, case_id: Optional[str] = None) -> dict[str, Any]:
        cases = self._load_cases()
        if case_id:
            cases = [c for c in cases if c["case_id"] == case_id]
            if not cases:
                return {"total": 0, "passed": 0, "failed": 0, "cases": [], "error": f"case {case_id} not found"}

        results: list[dict[str, Any]] = []
        for case in cases:
            res = self._run_one(case)
            results.append(res)

        passed = sum(1 for r in results if r["passed"])
        return {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "cases": results,
            "summary": {"pass_rate": round(passed / max(len(results), 1), 3)},
        }

    # ------------------------------------------------------------------
    def _load_cases(self) -> list[dict[str, Any]]:
        data = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8")) or {}
        return data.get("cases", [])

    # ------------------------------------------------------------------
    def _run_one(self, case: dict[str, Any]) -> dict[str, Any]:
        cid = case["case_id"]
        ctype = case.get("case_type", "single_turn")
        try:
            if ctype == "consistency_check":
                return self._run_consistency(case)
            if ctype == "feedback":
                return self._run_feedback(case)
            if ctype == "resume":
                return self._run_resume(case)
            return self._run_chat_case(case)
        except Exception as exc:  # noqa: BLE001
            return {"case_id": cid, "passed": False, "reason": f"runner_error: {exc}"}

    # ------------------------------------------------------------------
    def _fresh_agent(self) -> GraderAgent:
        return GraderAgent()

    @staticmethod
    def _public_response(
        resp: dict[str, Any],
        all_trace_events: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """把一次 chat/resume 响应裁剪为可对外回放链路的形式。

        只包含后端本就公开的字段（trace 已在 harness/trace.py 递归脱敏），
        剔除 ``_`` 前缀的内部聚合键；不含 hidden CoT。
        """
        pub = {k: v for k, v in resp.items() if not k.startswith("_")}
        if all_trace_events is not None:
            pub["trace_events"] = all_trace_events
        return pub

    def _run_chat_case(self, case: dict[str, Any]) -> dict[str, Any]:
        rt = case["input"]["runtime_context"]
        messages = case["input"]["user_messages"]
        agent = self._fresh_agent()
        last: dict[str, Any] = {}
        all_trace_events: list[dict[str, Any]] = []
        for i, msg in enumerate(messages):
            payload = self._chat_payload(rt, msg, f"{case['case_id']}-s{i}")
            last = agent.chat(payload)
            all_trace_events.extend(last.get("trace_events", []))
        last["_all_trace_events"] = all_trace_events
        result = self._assert(case, last, agent)
        # 公开响应 + 多轮聚合 trace，供前端 Eval 页回放决策链路
        result["response"] = self._public_response(last, all_trace_events)

        # byte_identical_runs：离线连跑 N 次，actual_answer 字节级一致才 pass。
        # 用于 degradation 等确定性话术的可复现性回归。
        n = case.get("byte_identical_runs")
        if n:
            answers = [last.get("answer", "")]
            for _ in range(int(n) - 1):
                fresh = self._fresh_agent()
                again = fresh.chat(
                    self._chat_payload(rt, messages[0], f"{case['case_id']}-bi")
                )
                answers.append(again.get("answer", ""))
            if len(set(answers)) != 1:
                result["passed"] = False
                result["reason"] = (
                    (result.get("reason", "") + "; " if result.get("reason") else "")
                    + f"byte_identical mismatch across {n} runs (variants={len(set(answers))})"
                )
        return result

    # ------------------------------------------------------------------
    def _run_resume(self, case: dict[str, Any]) -> dict[str, Any]:
        rt = case["input"]["runtime_context"]
        agent = self._fresh_agent()
        start_msg = case["input"].get("start_message")
        resume_cfg = case["input"].get("resume", {})
        expected = case.get("expected", {})
        subscenes = case.get("subscenes")

        # 跑 start
        start_resp: dict[str, Any] = {}
        if start_msg:
            start_resp = agent.chat(self._chat_payload(rt, start_msg, f"{case['case_id']}-start"))

        # 子场景（freeze drift）
        if subscenes:
            return self._run_resume_subscenes(case, agent, rt, start_resp, subscenes)

        token = (start_resp.get("pending_approval") or {}).get("resume_token")
        token = resume_cfg.get("resume_token_override") or token
        repeat = resume_cfg.get("repeat", False)

        resume_resp = agent.resume(
            {
                "session_id": f"{case['case_id']}-start",
                "resume_token": token or "",
                "approved_action": {
                    "decision": resume_cfg.get("decision", "approve"),
                    "instructor_id": resume_cfg.get("instructor_id", "ins-001"),
                },
            }
        )
        results: list[dict[str, Any]] = []
        if repeat:
            # 首次：recorded；重复：idempotent_replay
            r1 = self._assert_resume(case, resume_resp, require_idempotent=False)
            again = agent.resume(
                {
                    "session_id": f"{case['case_id']}-start",
                    "resume_token": token or "",
                    "approved_action": {
                        "decision": resume_cfg.get("decision", "approve"),
                        "instructor_id": resume_cfg.get("instructor_id", "ins-001"),
                    },
                }
            )
            r2 = self._assert_resume(case, again, require_idempotent=True)
            results = [r1, r2]
        else:
            results = [self._assert_resume(case, resume_resp)]

        passed = all(r["passed"] for r in results)
        return {
            "case_id": case["case_id"],
            "passed": passed,
            "details": results,
            # start 轮（发起审批）的公开响应，供前端回放链路
            "response": self._public_response(start_resp) if start_resp else None,
        }

    # ------------------------------------------------------------------
    def _run_resume_subscenes(
        self,
        case: dict[str, Any],
        agent: GraderAgent,
        rt: dict[str, Any],
        start_resp: dict[str, Any],
        subscenes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        mutation_expected = (case.get("expected", {}).get("resume") or {})
        out: list[dict[str, Any]] = []
        for sub in subscenes:
            # 每个子场景用新 agent，从干净 start 开始
            sa = self._fresh_agent()
            start_msg = case["input"].get("start_message")
            sr = sa.chat(self._chat_payload(rt, start_msg, f"{case['case_id']}-{sub['name']}"))
            token = (sr.get("pending_approval") or {}).get("resume_token")
            mut = sub.get("mutation", {})
            self._mutate_fixture(sa, rt.get("submission_id"), mut.get("field"), mut.get("to"))
            resume_cfg = case["input"].get("resume", {})
            rr = sa.resume(
                {
                    "session_id": f"{case['case_id']}-{sub['name']}",
                    "resume_token": token or "",
                    "approved_action": {
                        "decision": resume_cfg.get("decision", "approve"),
                        "instructor_id": resume_cfg.get("instructor_id", "ins-001"),
                    },
                }
            )
            self._restore_fixture(sa)
            ok = rr.get("status") == "blocked" and rr.get("reason") == "business_fact_drift"
            out.append(
                {
                    "subscene": sub["name"],
                    "passed": ok,
                    "result": rr,
                    "response": self._public_response(sr),
                }
            )
        return {
            "case_id": case["case_id"],
            "passed": all(o["passed"] for o in out),
            "details": out,
        }

    # ------------------------------------------------------------------
    def _run_consistency(self, case: dict[str, Any]) -> dict[str, Any]:
        rt = case["input"]["runtime_context"]
        msg = case["input"]["user_messages"][0]
        score_regex = case.get("score_regex", r"总分\s*([0-9.]+)")
        max_var = float(case.get("max_variance", 2))
        scores: list[float] = []
        last_resp: dict[str, Any] = {}
        for run in case.get("runs", [{}, {}]):
            agent = self._fresh_agent()
            payload = dict(rt)
            payload.update(run.get("identity_override", {}))
            resp = agent.chat(self._chat_payload(payload, msg, f"{case['case_id']}-run"))
            last_resp = resp
            m = re.search(score_regex, resp.get("answer", ""))
            if not m:
                return {
                    "case_id": case["case_id"],
                    "passed": False,
                    "reason": f"score_regex no match: {resp.get('answer','')[:80]}",
                    "response": self._public_response(resp),
                }
            scores.append(float(m.group(1)))
        variance = abs(scores[0] - scores[1])
        return {
            "case_id": case["case_id"],
            "passed": variance <= max_var,
            "details": {"scores": scores, "variance": variance, "max_variance": max_var},
            "response": self._public_response(last_resp) if last_resp else None,
        }

    # ------------------------------------------------------------------
    def _run_feedback(self, case: dict[str, Any]) -> dict[str, Any]:
        attributor = FailureAttributor()
        attr = attributor.attribute(
            case["input"].get("session_id", "sess-fb"),
            [],
            case["input"].get("feedback_text", ""),
        )
        backfilled = attributor.build_backfilled_case(case["input"], attr)
        expected_attr = set(case.get("expected", {}).get("attribution", []))
        ok = expected_attr.issubset(set(attr["dimensions"])) and backfilled.get("case_id", "").startswith("feedback-")
        return {"case_id": case["case_id"], "passed": ok, "details": {"attribution": attr, "backfilled": backfilled}}

    # ------------------------------------------------------------------
    def _chat_payload(self, rt: dict[str, Any], text: str, session_id: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "user_id": rt["user_id"],
            "role": rt.get("role", "student"),
            "course_id": rt["course_id"],
            "assignment_id": rt.get("assignment_id"),
            "submission_id": rt.get("submission_id"),
            "current_page": rt.get("current_page", "home"),
            "text": text,
            "claimed_role": rt.get("claimed_role"),
        }

    # ------------------------------------------------------------------
    # 断言
    # ------------------------------------------------------------------
    def _assert(self, case: dict[str, Any], resp: dict[str, Any], agent: GraderAgent) -> dict[str, Any]:
        exp = case.get("expected", {})
        failures: list[str] = []

        # intent / route_kind
        if "intent" in exp and resp.get("intent") != exp["intent"]:
            failures.append(f"intent={resp.get('intent')} expected={exp['intent']}")
        if "route_kind" in exp and resp.get("route_kind") != exp["route_kind"]:
            failures.append(f"route_kind={resp.get('route_kind')} expected={exp['route_kind']}")

        # expected_signals（离线优先 offline_expected_signals）
        signals_src = exp.get("expected_signals", [])
        if self.offline and case.get("offline_expected_signals"):
            signals_src = case["offline_expected_signals"]
        missing = _dot_in(resp.get("answer", ""), signals_src)
        if missing:
            failures.append(f"missing_signals={missing}")

        # expected_trace_events（多轮聚合）
        event_names = [e.get("event") for e in resp.get("trace_events", [])]
        all_names = [e.get("event") for e in resp.get("_all_trace_events", [])]
        for ev in exp.get("expected_trace_events", []):
            if ev not in event_names and ev not in all_names:
                failures.append(f"missing_trace_event={ev}")

        # expected_trace_payload：按 event 名定位 trace 事件，对 payload 做点路径相等断言
        all_trace = list(resp.get("trace_events", [])) + list(resp.get("_all_trace_events", []))
        for expected in exp.get("expected_trace_payload", []):
            ev_name = expected.get("event")
            dot = expected.get("path")
            want = expected.get("value")
            hit = False
            got_seen: list[Any] = []
            for ev in all_trace:
                if ev.get("event") != ev_name:
                    continue
                got = _get_dot(ev.get("payload", {}), dot)
                got_seen.append(got)
                if got == want:
                    hit = True
                    break
            if not hit:
                failures.append(
                    f"trace_payload {ev_name}.{dot} != {want} (seen={got_seen})"
                )

        # expected_session_state
        for path, want in (exp.get("expected_session_state") or {}).items():
            got = _get_dot(resp.get("session_state", {}), path)
            if got != want:
                failures.append(f"session_state.{path}={got} expected={want}")

        # expected_tools / forbidden_tools
        called = {o.get("tool_name") for o in self._tool_obs(resp)}
        for t in exp.get("expected_tools", []):
            if t not in called:
                failures.append(f"expected_tool_missing={t}")
        for t in exp.get("forbidden_tools", []):
            if t in called:
                failures.append(f"forbidden_tool_called={t}")

        # forbidden_text
        for t in exp.get("forbidden_text", []):
            if t in resp.get("answer", ""):
                failures.append(f"forbidden_text_hit={t}")

        # expected_citations：至少有一条 citation 的 source 命中期望域
        citations = resp.get("citations", [])
        for expected in exp.get("expected_citations", []):
            want_src = expected.get("source")
            want_stage = expected.get("retrieval_stage")
            hit = False
            for c in citations:
                if c.get("source") != want_src:
                    continue
                if want_stage and c.get("retrieval_stage") != want_stage:
                    continue
                hit = True
                break
            if not hit:
                failures.append(
                    f"missing_citation source={want_src} stage={want_stage} "
                    f"got={[c.get('source') for c in citations]}"
                )

        return {
            "case_id": case["case_id"],
            "passed": not failures,
            "reason": "; ".join(failures) if failures else "ok",
        }

    def _assert_resume(self, case: dict[str, Any], resp: dict[str, Any], require_idempotent: Optional[bool] = None) -> dict[str, Any]:
        exp = (case.get("expected", {}).get("resume") or {})
        failures: list[str] = []
        if "status" in exp and resp.get("status") != exp["status"]:
            failures.append(f"status={resp.get('status')} expected={exp['status']}")
        if "reason" in exp and resp.get("reason") != exp["reason"]:
            failures.append(f"reason={resp.get('reason')} expected={exp['reason']}")
        if require_idempotent is True and not resp.get("idempotent_replay"):
            failures.append("idempotent_replay=false")
        if require_idempotent is False and resp.get("idempotent_replay"):
            failures.append("unexpected_idempotent_replay")
        for s in exp.get("expected_signals", []):
            if s not in resp.get("answer", ""):
                failures.append(f"missing_signal={s}")
        return {"passed": not failures, "reason": "; ".join(failures) or "ok", "result": resp}

    # ------------------------------------------------------------------
    def _tool_obs(self, resp: dict[str, Any]) -> list[dict[str, Any]]:
        return resp.get("tool_calls", [])

    # ------------------------------------------------------------------
    # fixture 变异（改 seed 后还原）
    # ------------------------------------------------------------------
    def _mutate_fixture(self, agent: GraderAgent, submission_id: str, field: str, to: Any) -> None:
        seed = agent.lms._seed  # noqa: SLF001
        if not seed:
            return
        sub = seed.get("submissions", {}).get(submission_id, {})
        if field == "body_hash":
            sub["body_hash"] = to
        elif field == "rubric_version":
            # 提交侧不直接存 rubric_version；改 assignment 指向的 rubric key
            sub["rubric_version"] = to
        elif field == "similarity_score":
            sub["similarity_score"] = float(to)

    def _restore_fixture(self, agent: GraderAgent) -> None:
        # 重新从磁盘加载 seed，丢弃内存修改
        agent.lms._seed = None  # noqa: SLF001


# 直接运行
def main() -> None:
    runner = EvalRunner()
    report = runner.run()
    print(f"total={report['total']} passed={report['passed']} failed={report['failed']}")
    for c in report["cases"]:
        flag = "PASS" if c["passed"] else "FAIL"
        print(f"[{flag}] {c['case_id']}  {c.get('reason', '')}")


if __name__ == "__main__":
    main()
