"""CostGovernor：成本治理。

安全边界：成本治理不得跳过业务事实（check_similarity 等）与 HITL。
缓存命中 / token 预算截断只能跳最终模型生成。
"""

from __future__ import annotations

from typing import Any


class CostGovernor:
    """记录工具 / LLM / token 消耗，并在超预算时告警。"""

    def __init__(self, token_budget: int = 8000) -> None:
        self.token_budget = token_budget

    def build_cost_summary(
        self,
        tool_calls: int = 0,
        llm_calls: int = 0,
        tokens: int = 0,
        llm_latency_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> dict[str, Any]:
        return {
            "schema_version": "grader_cost_v1",
            "tool_call_count": tool_calls,
            "llm_call_count": llm_calls,
            "tokens_used": tokens,
            "tokens_budget": self.token_budget,
            "budget_ratio": round(tokens / max(self.token_budget, 1), 4),
            # 真实模型开销（离线 / 缺 key 的短路调用为 0）：
            # 耗时按请求前后差值、token 按在线回包 usage 累计。
            "llm_latency_ms": round(llm_latency_ms, 1),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_llm_tokens": prompt_tokens + completion_tokens,
            "safety_boundary": {
                "cost_does_not_skip_business_facts": True,
                "cost_does_not_skip_hitl": True,
            },
        }

    def observation_compression(self, observation: str, max_chars: int = 2000) -> str:
        """超长 observation 按长度截断（按评分点相关性压缩在 agent 层做）。"""
        if len(observation) <= max_chars:
            return observation
        return observation[:max_chars] + "\n[truncated-by-cost-governor]"

    def token_budget_check(self, current: int, budget: int | None = None) -> bool:
        """超 80% 告警，100% 停止。返回 True 表示仍可继续。"""
        budget = budget or self.token_budget
        if current >= budget:
            return False  # 100% 停止
        if current >= budget * 0.8:
            # 80% 告警：仍可继续，但 agent 层应考虑 skip final model
            return True
        return True
