"""三级权限矩阵（student / ta / instructor）。

权限硬编码在代码里，不靠 prompt 软约束。用户自称角色只展示不授权；
授权以 LMS 授课名单快照为准。
"""

from __future__ import annotations

from typing import Any


class PermissionError(RuntimeError):
    """越权访问被拒。"""


def can_query_own_grade(role: str) -> bool:
    return role in {"student", "ta", "instructor"}


def can_query_any_grade(role: str) -> bool:
    return role in {"ta", "instructor"}


def can_draft_grade(role: str) -> bool:
    """发起初批草稿。"""
    return role in {"ta", "instructor"}


def can_record_final_grade(role: str) -> bool:
    """终录成绩：仅 instructor。"""
    return role == "instructor"


def can_judge_misconduct(role: str) -> bool:
    """学术不端终判：仅 instructor。"""
    return role == "instructor"


def can_batch_grade(role: str) -> bool:
    """批量初批：ta / instructor。"""
    return role in {"ta", "instructor"}


def verify_instructor(user_id: str, course_id: str, roster: dict[str, Any]) -> bool:
    """以 LMS 授课名单快照为准校验 instructor 身份。

    claimed_role 仅展示不授权；这里只信任 roster 快照。
    """
    if not roster:
        return False
    return roster.get("instructor_id") == user_id


def assert_role(condition: bool, action: str, role: str) -> None:
    if not condition:
        raise PermissionError(f"role={role} not permitted for action={action}")
