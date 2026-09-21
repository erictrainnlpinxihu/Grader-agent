"""harness.config：.env 加载器与读取助手的单元测试。"""

from __future__ import annotations

import os
from pathlib import Path

import harness.config as cfg


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_env_line_forms() -> None:
    assert cfg.parse_env_line("# 整行注释") is None
    assert cfg.parse_env_line("   ") is None
    assert cfg.parse_env_line("NO_EQUAL_SIGN") is None
    assert cfg.parse_env_line("export GRADER_A=hello") == ("GRADER_A", "hello")
    assert cfg.parse_env_line('GRADER_B="quoted value"') == ("GRADER_B", "quoted value")
    assert cfg.parse_env_line("GRADER_C='single x'") == ("GRADER_C", "single x")
    assert cfg.parse_env_line("GRADER_D=plain # inline note") == ("GRADER_D", "plain")
    # 引号内的 # 是普通字符
    assert cfg.parse_env_line('GRADER_E="a # b"') == ("GRADER_E", "a # b")


def test_setdefault_never_overrides_shell(tmp_path: Path, monkeypatch) -> None:
    env_file = _write(
        tmp_path / ".env",
        "GRADER_CFG_X=from_file\nGRADER_CFG_Y=from_file\n",
    )
    monkeypatch.setenv("GRADER_CFG_X", "from_shell")
    monkeypatch.delenv("GRADER_CFG_Y", raising=False)

    loaded = cfg.load_dotenv(env_file)

    assert os.environ["GRADER_CFG_X"] == "from_shell"  # shell 优先，未被覆盖
    assert os.environ["GRADER_CFG_Y"] == "from_file"  # 缺失项被填补
    assert loaded == {"GRADER_CFG_Y": "from_file"}  # 只返回实际注入的键


def test_explicit_env_file_var(tmp_path: Path, monkeypatch) -> None:
    env_file = _write(tmp_path / "x.env", "GRADER_CFG_Z=9\n")
    monkeypatch.setenv(cfg.ENV_FILE_VAR, str(env_file))
    monkeypatch.delenv("GRADER_CFG_Z", raising=False)

    assert cfg.load_dotenv() == {"GRADER_CFG_Z": "9"}


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert cfg.load_dotenv(tmp_path / "nope" / ".env") == {}


def test_search_upward_from_cwd(tmp_path: Path, monkeypatch) -> None:
    _write(tmp_path / ".env", "GRADER_CFG_UP=yes\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.delenv("GRADER_CFG_UP", raising=False)

    old_cwd = Path.cwd()
    os.chdir(nested)
    try:
        assert cfg.load_dotenv() == {"GRADER_CFG_UP": "yes"}
    finally:
        os.chdir(old_cwd)


def test_get_bool(monkeypatch) -> None:
    for truthy in ("1", "true", "YES", "on"):
        monkeypatch.setenv("GRADER_CFG_BOOL", truthy)
        assert cfg.get_bool("GRADER_CFG_BOOL") is True
    monkeypatch.setenv("GRADER_CFG_BOOL", "0")
    assert cfg.get_bool("GRADER_CFG_BOOL") is False
    monkeypatch.delenv("GRADER_CFG_BOOL")
    assert cfg.get_bool("GRADER_CFG_BOOL", default=False) is False
    assert cfg.get_bool("GRADER_CFG_BOOL", default=True) is True
