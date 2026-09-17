"""LMS 数据客户端（双轨）。

- 在线模式：httpx 调真实 LMS，带委派身份头。
- 离线模式（GRADER_OFFLINE_FACTS=1）：回退到 configs/seed_data.json。

所有返回 dict 都打 ``_fact_source`` 标记：
- ``grader_seed_mirror``（离线种子镜像）
- ``lms_api``（在线 LMS 直连）
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import httpx

_CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"
_SEED_PATH = _CONFIGS_DIR / "seed_data.json"

OFFLINE_SOURCE = "grader_seed_mirror"
ONLINE_SOURCE = "lms_api"


def _env_offline_facts() -> bool:
    return os.environ.get("GRADER_OFFLINE_FACTS", "") == "1"


class LMSClient:
    """只读 LMS 客户端；写路径不在这里，写动作只产 HighRiskProposal。"""

    def __init__(self, seed_path: Optional[Path] = None) -> None:
        self.offline = _env_offline_facts()
        self.seed_path = seed_path or _SEED_PATH
        self._seed: Optional[dict[str, Any]] = None
        # trust_env=False：不读系统代理，避免离线测试被企业代理污染
        self._http = httpx.Client(timeout=5.0, trust_env=False)

    # ------------------------------------------------------------------
    # 离线种子加载
    # ------------------------------------------------------------------
    def _load_seed(self) -> dict[str, Any]:
        if self._seed is None:
            with open(self.seed_path, "r", encoding="utf-8") as fh:
                self._seed = json.load(fh)
        return self._seed

    def _mark_offline(self, data: Optional[dict]) -> Optional[dict]:
        if data is None:
            return None
        out = dict(data)
        out["_fact_source"] = OFFLINE_SOURCE
        return out

    def _mark_online(self, data: Optional[dict]) -> Optional[dict]:
        if data is None:
            return None
        out = dict(data)
        out["_fact_source"] = ONLINE_SOURCE
        return out

    # ------------------------------------------------------------------
    # 在线模式占位请求头（委派身份）
    # ------------------------------------------------------------------
    def _online_headers(self, acting_as_user: Optional[str] = None) -> dict[str, str]:
        headers = {
            "X-Grader-Service-Token": os.environ.get("GRADER_LMS_SERVICE_TOKEN", "dev-token"),
        }
        if acting_as_user:
            headers["X-Grader-User-Id"] = acting_as_user
        return headers

    # ------------------------------------------------------------------
    # 只读查询 API
    # ------------------------------------------------------------------
    def get_course(self, course_id: str) -> Optional[dict[str, Any]]:
        if self.offline:
            return self._mark_offline(self._load_seed()["courses"].get(course_id))
        resp = self._http.get(
            f"{self._lms_base()}/courses/{course_id}", headers=self._online_headers()
        )
        resp.raise_for_status()
        return self._mark_online(resp.json())

    def get_assignment(self, assignment_id: str) -> Optional[dict[str, Any]]:
        if self.offline:
            return self._mark_offline(self._load_seed()["assignments"].get(assignment_id))
        resp = self._http.get(
            f"{self._lms_base()}/assignments/{assignment_id}", headers=self._online_headers()
        )
        resp.raise_for_status()
        return self._mark_online(resp.json())

    def get_rubric(self, assignment_id: str, rubric_version: str) -> Optional[dict[str, Any]]:
        key = f"{assignment_id}::{rubric_version}"
        if self.offline:
            return self._mark_offline(self._load_seed()["rubrics"].get(key))
        resp = self._http.get(
            f"{self._lms_base()}/rubrics/{assignment_id}",
            params={"version": rubric_version},
            headers=self._online_headers(),
        )
        resp.raise_for_status()
        return self._mark_online(resp.json())

    def list_submissions(self, course_id: str, assignment_id: str) -> list[dict[str, Any]]:
        if self.offline:
            seed = self._load_seed()
            rows = [
                sub
                for sub in seed["submissions"].values()
                if sub.get("course_id") == course_id and sub.get("assignment_id") == assignment_id
            ]
            return [self._mark_offline(r) for r in rows]
        resp = self._http.get(
            f"{self._lms_base()}/submissions",
            params={"course_id": course_id, "assignment_id": assignment_id},
            headers=self._online_headers(),
        )
        resp.raise_for_status()
        return [self._mark_online(r) for r in resp.json().get("items", [])]

    def get_submission(self, submission_id: str) -> Optional[dict[str, Any]]:
        if self.offline:
            return self._mark_offline(self._load_seed()["submissions"].get(submission_id))
        resp = self._http.get(
            f"{self._lms_base()}/submissions/{submission_id}", headers=self._online_headers()
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._mark_online(resp.json())

    def get_student_history(self, student_id: str, course_id: str) -> list[dict[str, Any]]:
        if self.offline:
            seed = self._load_seed()
            rows = [
                sub
                for sub in seed["submissions"].values()
                if sub.get("student_id") == student_id and sub.get("course_id") == course_id
            ]
            return [self._mark_offline(r) for r in rows]
        resp = self._http.get(
            f"{self._lms_base()}/students/{student_id}/history",
            params={"course_id": course_id},
            headers=self._online_headers(),
        )
        resp.raise_for_status()
        return [self._mark_online(r) for r in resp.json().get("items", [])]

    def check_similarity(self, submission_id: str) -> dict[str, Any]:
        sub = self.get_submission(submission_id)
        score = (sub or {}).get("similarity_score", 0.0)
        return {
            "submission_id": submission_id,
            "similarity_score": float(score),
            "flagged": float(score) >= 0.8,
            "_fact_source": (sub or {}).get("_fact_source", OFFLINE_SOURCE if self.offline else ONLINE_SOURCE),
        }

    def get_submission_timestamp(self, submission_id: str) -> Optional[str]:
        sub = self.get_submission(submission_id)
        if sub is None:
            return None
        return sub.get("submitted_at")

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        if self.offline:
            return self._mark_offline(self._load_seed()["users"].get(user_id))
        resp = self._http.get(
            f"{self._lms_base()}/users/{user_id}", headers=self._online_headers()
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._mark_online(resp.json())

    def get_instructor_roster(self, course_id: str) -> dict[str, Any]:
        """返回授课名单快照：instructor_id / ta_ids / student_ids。"""
        if self.offline:
            course = self._load_seed()["courses"].get(course_id, {})
            return self._mark_offline(
                {
                    "course_id": course_id,
                    "instructor_id": course.get("instructor_id"),
                    "ta_ids": list(course.get("tas", [])),
                    "student_ids": list(course.get("enrolled_students", [])),
                }
            )
        resp = self._http.get(
            f"{self._lms_base()}/courses/{course_id}/roster", headers=self._online_headers()
        )
        resp.raise_for_status()
        return self._mark_online(resp.json())

    # ------------------------------------------------------------------
    def _lms_base(self) -> str:
        return os.environ.get("GRADER_LMS_BASE_URL", "https://lms.example.com/api")

    def close(self) -> None:
        self._http.close()
