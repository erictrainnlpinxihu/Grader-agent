"""LLM 客户端双轨封装。

在线模式（GRADER_DISABLE_LLM 未设置）：用 langchain-openai 的 ChatOpenAI，
通过 ``with_structured_output`` 绑定 Pydantic schema。

离线模式（GRADER_DISABLE_LLM=1）：所有语义调用返回 ``None``，调用方走确定性规则替身。
本模块不缓存任何 prompt 正文，不混入动态学生数据。
"""

from __future__ import annotations

import os
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
            timeout=20.0,
        )
        return self._llm

    # ------------------------------------------------------------------
    def structured(self, pydantic_model: type, prompt: str) -> Optional[Any]:
        """在线：返回绑定 schema 的模型实例；离线返回 None。"""
        if self.disabled:
            return None
        if not self._api_key():
            # 无 key 时不硬报错，降级离线（安全边界：不因为缺 key 跳过 guard）
            return None
        llm = self._build_llm(temperature=0.0)
        try:
            bound = llm.with_structured_output(pydantic_model)
            return bound.invoke(prompt)
        except Exception:
            return None

    def generate(self, system: str, user: str) -> Optional[str]:
        """在线：自由文本生成最终答案；离线返回 None。"""
        if self.disabled:
            return None
        if not self._api_key():
            return None
        llm = self._build_llm(temperature=0.0)
        try:
            resp = llm.invoke([("system", system), ("human", user)])
            return getattr(resp, "content", str(resp))
        except Exception:
            return None


# 进程级单例
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
