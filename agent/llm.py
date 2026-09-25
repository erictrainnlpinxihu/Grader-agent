"""LLM 客户端双轨封装。

在线模式（GRADER_DISABLE_LLM 未设置）：用 langchain-openai 的 ChatOpenAI，
通过 ``with_structured_output`` 绑定 Pydantic schema。

离线模式（GRADER_DISABLE_LLM=1）：所有语义调用返回 ``None``，调用方走确定性规则替身。
本模块不缓存任何 prompt 正文，不混入动态学生数据。
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import harness.config  # noqa: F401  # 首次 import 即加载 .env，须早于下面的环境变量读取


def llm_disabled() -> bool:
    """GRADER_DISABLE_LLM=1 时为离线模式。"""
    return os.environ.get("GRADER_DISABLE_LLM", "") == "1"


class LLMClient:
    """轻量 LLM 封装：结构化输出 + 自由文本生成。

    离线模式下所有调用都返回 None，由调用方的确定性规则兜底；
    在线模式下才真正构造 langchain 客户端。
    """

    def __init__(self) -> None:
        self.disabled = llm_disabled()
        self._llm: Any = None
        self._llm_text: Any = None
        # 真实在线调用计数（离线 / 缺 key 的短路返回不计），供成本记账读取。
        # 进程级单例累计，调用方按"请求前后差值"取本请求的真实调用数。
        self.calls = 0
        # 真实在线调用的累计耗时（毫秒）与 token 用量（离线 / 缺 key 不计）。
        # 同样按"请求前后差值"取本请求的模型时延与 token 开销，供 /chat 响应
        # 的 latency / cost_summary 暴露给调试台。
        self.latency_ms = 0.0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    # ------------------------------------------------------------------
    def _base_url(self) -> str:
        return os.environ.get("GRADER_LLM_BASE_URL", "https://api.siliconflow.cn/v1")

    def _model(self) -> str:
        return os.environ.get("GRADER_LLM_MODEL", "Qwen/Qwen3-8B")

    def _api_key(self) -> str:
        key = os.environ.get("GRADER_LLM_API_KEY", "")
        if not key or key in {"placeholder", "sk-xxx"}:
            return ""
        return key

    def _build_llm(self, temperature: float = 0.0) -> Any:
        if self._llm is not None:
            return self._llm
        from langchain_openai import ChatOpenAI

        self._llm = ChatOpenAI(
            model=self._model(),
            temperature=temperature,
            base_url=self._base_url(),
            api_key=self._api_key() or "missing",
            # 在线结构化输出实测可达数十秒甚至更久（高峰期路由分类 >120s），
            # 与前端 300s 请求预算对齐；不做 SDK 重试——超时/失败直接走
            # 确定性规则兜底，避免重试叠加撑爆前端超时。
            timeout=300.0,
            max_retries=0,
        )
        return self._llm

    # ------------------------------------------------------------------
    def _record_usage(self, resp: Any) -> None:
        """从在线回包提取真实 token 用量，累加到单例计数器。

        usage_metadata（langchain-core 标准）优先，OpenAI 的
        response_metadata.token_usage 兜底；两者皆缺则不计（保持 0）。
        """
        if resp is None:
            return
        usage = getattr(resp, "usage_metadata", None) or {}
        if usage:
            self.prompt_tokens += int(usage.get("input_tokens", 0) or 0)
            self.completion_tokens += int(usage.get("output_tokens", 0) or 0)
            return
        token_usage = (getattr(resp, "response_metadata", None) or {}).get("token_usage") or {}
        self.prompt_tokens += int(token_usage.get("prompt_tokens", 0) or 0)
        self.completion_tokens += int(token_usage.get("completion_tokens", 0) or 0)

    # ------------------------------------------------------------------
    def structured(self, pydantic_model: type, prompt: str) -> Optional[Any]:
        """在线：返回绑定 schema 的模型实例；离线返回 None。

        include_raw=True 保留原始 AIMessage 以读取 token 用量；
        解析失败与调用异常同样返回 None，由调用方走确定性规则兜底。
        """
        if self.disabled:
            return None
        if not self._api_key():
            # 无 key 时不硬报错，降级离线（安全边界：不因为缺 key 跳过 guard）
            return None
        llm = self._build_llm(temperature=0.0)
        self.calls += 1
        t0 = time.perf_counter()
        try:
            bound = llm.with_structured_output(
                pydantic_model,
                # Qwen 系模型走 json_schema（默认路径）易产出非对象 JSON 导致
                # 解析失败（实测 0/3）；tool calling 路径稳定（实测 3/3），显式指定。
                method="function_calling",
                include_raw=True,
            )
            payload = bound.invoke(prompt)
        except Exception:
            return None
        finally:
            self.latency_ms += (time.perf_counter() - t0) * 1000
        if not isinstance(payload, dict) or payload.get("parsing_error"):
            return None
        self._record_usage(payload.get("raw"))
        return payload.get("parsed")

    def generate(self, system: str, user: str) -> Optional[str]:
        """在线：自由文本生成最终答案；离线返回 None。"""
        if self.disabled:
            return None
        if not self._api_key():
            return None
        llm = self._build_llm(temperature=0.0)
        self.calls += 1
        t0 = time.perf_counter()
        try:
            resp = llm.invoke([("system", system), ("human", user)])
        except Exception:
            return None
        finally:
            self.latency_ms += (time.perf_counter() - t0) * 1000
        self._record_usage(resp)
        return getattr(resp, "content", str(resp))


# 进程级单例
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
