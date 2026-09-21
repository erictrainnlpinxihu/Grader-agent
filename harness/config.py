"""极简 ``.env`` 加载器（无第三方依赖）与环境变量读取助手。

为什么需要它
------------
项目所有开关 / 密钥都从 ``os.environ`` 读取（见 ``agent/llm.py``、
``rag/embedding.py``、``harness/lms_client.py``）。本模块在**首次被 import
时自动加载一次 ``.env``**，把其中的键值用 :func:`os.environ.setdefault`
注入环境，因此你可以把配置写进项目根的 ``.env``，而不必每次手动 ``export``。

优先级（从高到低；低优先级不覆盖高优先级）
------------------------------------------
1. Shell 里已经导出的真实环境变量（``export GRADER_LLM_API_KEY=...`` 或命令行前缀）；
2. ``.env`` 文件里的键值（仅填补当前缺失的变量，等价于 setdefault）；
3. 各业务模块 ``os.environ.get(name, default)`` 里写死的代码默认值。

``.env`` 文件定位
-----------------
* 若设置了 ``GRADER_ENV_FILE``（它只能由 shell 环境给定，因为它指向 .env 自身的位置），
  则加载该路径；
* 否则从**当前工作目录向上逐级**查找第一个 ``.env``，所以在项目根或其子目录启动都能命中。

支持的语法：``KEY=VALUE`` 每行一个；``#`` 整行注释；可选的 ``export `` 前缀；
成对的单 / 双引号；非引号值中以空白开头的行内注释（``VALUE  # note``）。
不做 ``${VAR}`` 插值、不做类型转换（布尔判定请用 :func:`get_bool`）。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ENV_FILE_VAR = "GRADER_ENV_FILE"
_INLINE_COMMENT = re.compile(r"\s+#.*$")


def parse_env_line(raw: str) -> "tuple[str, str] | None":
    """解析 .env 的一行；注释行 / 空行 / 无等号的非法行返回 ``None``。"""
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].strip()
    if "=" not in line:
        return None
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        # 成对引号：去掉外层引号；引号内的 # 视为普通字符，不做行内注释裁剪
        value = value[1:-1]
    else:
        value = _INLINE_COMMENT.sub("", value).strip()
    return key, value


def _candidate_paths(explicit: "str | None") -> "list[Path]":
    if explicit:
        return [Path(explicit).expanduser()]
    start = Path.cwd().resolve()
    return [d / ".env" for d in (start, *start.parents)]


def load_dotenv(
    path: "str | os.PathLike[str] | None" = None,
    *,
    override: bool = False,
) -> "dict[str, str]":
    """把 ``.env`` 加载进 :data:`os.environ`，返回本次**实际注入**的键值。

    默认 ``override=False``：只填补当前缺失的变量（shell 已导出的原样保留）。
    找不到文件时返回空 dict，不抛错。
    """
    explicit = os.fspath(path) if path else os.environ.get(ENV_FILE_VAR)
    env_path: "Path | None" = None
    for cand in _candidate_paths(explicit):
        if cand.is_file():
            env_path = cand
            break
    if env_path is None:
        return {}

    loaded: "dict[str, str]" = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        pair = parse_env_line(raw)
        if pair is None:
            continue
        key, value = pair
        if override or key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def get_str(name: str, default: str = "") -> str:
    """读取字符串环境变量；缺失时返回 default。"""
    return os.environ.get(name, default)


def get_bool(name: str, default: bool = False) -> bool:
    """把 ``1 / true / yes / on``（大小写不敏感）视为 True；缺失时返回 default。"""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# 首次 import 即加载一次；Python 只会执行一次模块体，重复 import 天然幂等。
load_dotenv()
