"""ReActLoop：只读工具回路（白名单对账 + source_guard semi_trusted）。

离线模式：直接按 route_plan.required_tools 顺序调用 ToolRuntime.execute。
在线模式：LangChain native tool calling，温度=0，recursion_limit=6。

4 个高风险写动作物理上不在工具表内；模型只能在 final_answer 阶段产 HighRiskProposal。
"""

from __future__ import annotations

from typing import Any, Optional

from harness.contracts import RoutePlanCandidate, RuntimeContext
from harness.source_guard import SEMI_TRUSTED, inspect_source
from harness.tool_runtime import READONLY_TOOL_WHITELIST, ToolRuntime

RECURSION_LIMIT = 6
TEMPERATURE = 0.0


class ReActLoop:
    """只读 ReAct 回路。"""

    def __init__(self, tool_runtime: Optional[ToolRuntime] = None) -> None:
        self.tools = tool_runtime or ToolRuntime()

    # ------------------------------------------------------------------
    def run(
        self,
        route_plan: RoutePlanCandidate,
        runtime_context: RuntimeContext,
        tool_args: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """按声明的 required_tools 顺序执行只读工具。

        tool_args: 实体上下文（submission_id / course_id / assignment_id 等）。
        返回 {tool_results, observations, cost_summary, tool_names_called}。
        """
        tool_args = tool_args or {}
        required = list(route_plan.required_tools)

        # 白名单对账：required_tools 必须全在 6 只读白名单内
        for name in required:
            if name not in READONLY_TOOL_WHITELIST:
                raise ValueError(f"tool {name} not in readonly whitelist")

        tool_results: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        tool_names_called: list[str] = []

        for name in required[:RECURSION_LIMIT]:
            args = self._build_args(name, tool_args)
            try:
                result = self.tools.execute(
                    name, args, runtime_context, required_tools=required
                )
                # semi_trusted 过 source_guard（工具返回可能过期，但不可信注入）
                text = result.get("body") or str(result)
                safety = inspect_source(f"tool:{name}", text, SEMI_TRUSTED)
                observations.append(
                    {
                        "tool_name": name,
                        "args": args,
                        "output_summary": self._summarize(result),
                        "status": "success",
                        "safety": {k: safety[k] for k in ("tainted", "matched_pattern", "sha256")},
                    }
                )
                tool_results.append({"tool_name": name, "result": result, "safety": safety})
                tool_names_called.append(name)
            except Exception as exc:  # noqa: BLE001
                observations.append(
                    {"tool_name": name, "args": args, "status": "error", "error": str(exc)}
                )

        return {
            "tool_results": tool_results,
            "observations": observations,
            "tool_names_called": tool_names_called,
            "cost_summary": {
                "tool_call_count": len(tool_names_called),
                "recursion_limit": RECURSION_LIMIT,
                "temperature": TEMPERATURE,
            },
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _build_args(tool_name: str, ctx: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "list_submissions":
            return {
                "course_id": ctx.get("course_id", ""),
                "assignment_id": ctx.get("assignment_id", ""),
            }
        if tool_name == "get_submission":
            return {"submission_id": ctx.get("submission_id", "")}
        if tool_name == "get_rubric":
            return {
                "assignment_id": ctx.get("assignment_id", ""),
                "rubric_version": ctx.get("rubric_version", "v1.0"),
            }
        if tool_name == "get_student_history":
            return {
                "student_id": ctx.get("student_id") or ctx.get("user_id", ""),
                "course_id": ctx.get("course_id", ""),
            }
        if tool_name == "check_similarity":
            return {"submission_id": ctx.get("submission_id", "")}
        if tool_name == "get_submission_timestamp":
            return {"submission_id": ctx.get("submission_id", "")}
        return {}

    @staticmethod
    def _summarize(result: dict[str, Any]) -> str:
        if "status" in result and "submission_id" in result:
            extra = f"，总分 {result['final_score']}" if result.get("final_score") is not None else ""
            return f"[已脱敏] 提交 {result['submission_id']} 状态 {result['status']}{extra}"
        if "items" in result:
            return f"[已脱敏] 返回 {len(result['items'])} 条记录"
        if "similarity_score" in result:
            return f"相似度 {result['similarity_score']:.2f}"
        return "[已脱敏] 工具返回"
