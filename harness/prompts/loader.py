"""PromptRegistry 轻量加载器：选择、排序、拼接 system prompt。

只允许读取 fragments/ 目录下注册过的 md 文件，防目录逃逸。
render_system_prompt 不混入动态学生数据。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROMPTS_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = PROMPTS_DIR / "prompt_registry.yml"
FRAGMENTS_DIR = PROMPTS_DIR / "fragments"


@dataclass(frozen=True)
class PromptFragment:
    """一个可按执行阶段和业务信号选择的稳定 prompt 片段。"""

    name: str
    level: str
    version: str
    load: str
    priority: int
    status: str = "active"
    description: str = ""


class PromptManager:
    """管理稳定规则片段；动态学生数据永远不进 system prompt。"""

    def __init__(self, prompts_dir: Path = PROMPTS_DIR) -> None:
        self.prompts_dir = prompts_dir.resolve()
        self.fragments_dir = (prompts_dir / "fragments").resolve()
        self._registry = self._load_registry()

    @lru_cache(maxsize=None)
    def load(self, name: str) -> str:
        """只允许读取 fragments/ 下注册过的 md 文件。"""
        path = (self.fragments_dir / f"{name}.md").resolve()
        if path.parent != self.fragments_dir:
            raise ValueError(f"Invalid prompt name: {name}")
        if not path.exists():
            raise FileNotFoundError(f"prompt fragment not found: {name}")
        return path.read_text(encoding="utf-8").strip()

    def select_fragments(self, signals: dict[str, Any]) -> list[PromptFragment]:
        """按 load 条件选择片段。signals 可含 route_kind / intent / needs_rag。"""
        selected: list[PromptFragment] = []
        route_kind = signals.get("route_kind") or signals.get("intent")
        for frag in self._registry:
            if frag.status != "active":
                continue
            if self._matches(frag.load, signals, route_kind):
                selected.append(frag)
        return sorted(selected, key=lambda f: (-f.priority, f.name))

    def _matches(self, load: str, signals: dict[str, Any], route_kind: Any) -> bool:
        if load == "always":
            return True
        if load == "when_rag":
            return bool(signals.get("needs_rag"))
        if load == "when_route":
            # 高风险路由时加载
            return bool(signals.get("requires_workflow") or signals.get("needs_human_approval"))
        if load.startswith("when_route="):
            target = load.split("=", 1)[1]
            return route_kind == target
        return False

    def render_system_prompt(self, signals: dict[str, Any]) -> str:
        """按 load 条件选择片段，按 priority 排序，拼接成 system prompt。"""
        fragments = self.select_fragments(signals)
        return "\n\n".join(
            f"[{f.name}|{f.level}|{f.version}|priority={f.priority}]\n{self.load(f.name)}"
            for f in fragments
        )

    def _load_registry(self) -> list[PromptFragment]:
        payload = yaml.safe_load(
            (self.prompts_dir / "prompt_registry.yml").read_text(encoding="utf-8")
        ) or {}
        return [
            PromptFragment(
                name=item["name"],
                level=item.get("level", "system"),
                version=item.get("version", "v1"),
                load=item["load"],
                priority=int(item["priority"]),
                status=item.get("status", "active"),
                description=item.get("description", ""),
            )
            for item in payload.get("fragments", [])
        ]


# 全局单例
_prompt_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager


def render_system_prompt(signals: dict[str, Any]) -> str:
    """模块级便捷函数。"""
    return get_prompt_manager().render_system_prompt(signals)
