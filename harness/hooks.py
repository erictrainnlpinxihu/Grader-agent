"""HookManager：工具前后 / 错误 / 完成治理事件。

默认 hook：记录 trace、成本统计、source_guard 检查。
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from harness.trace import TraceStore, make_event


HookFn = Callable[..., None]


class HookManager:
    """轻量 hook 注册表。"""

    def __init__(self, trace_store: Optional[TraceStore] = None) -> None:
        self._trace = trace_store or TraceStore()
        self._hooks: dict[str, list[HookFn]] = {
            "pre_tool_call": [],
            "post_tool_call": [],
            "on_error": [],
            "on_completion": [],
        }

    def register(self, stage: str, fn: HookFn) -> None:
        if stage not in self._hooks:
            raise ValueError(f"unknown hook stage: {stage}")
        self._hooks[stage].append(fn)

    def fire(self, stage: str, *, session_id: str, **payload: Any) -> None:
        # 默认：所有 hook 事件都进 trace
        self._trace.add(make_event(f"hook_{stage}", session_id, payload))
        for fn in self._hooks.get(stage, []):
            try:
                fn(session_id=session_id, **payload)
            except Exception as exc:  # noqa: BLE001
                self._trace.add(
                    make_event("hook_error", session_id, {"stage": stage, "error": str(exc)})
                )

    @property
    def trace(self) -> TraceStore:
        return self._trace
