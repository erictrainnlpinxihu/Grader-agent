"""business_recheck 漂移：body hash / rubric version / similarity 更新。"""

from __future__ import annotations

from agent.loop import GraderAgent


def _start_grading(agent: GraderAgent):
    r = agent.chat(
        {
            "session_id": "drift",
            "user_id": "ta-001",
            "role": "ta",
            "course_id": "CS101-2026spring",
            "assignment_id": "A3",
            "submission_id": "S1001",
            "text": "帮我批一下 S1001",
        }
    )
    return r["pending_approval"]["resume_token"]


def test_submission_body_hash_drift():
    agent = GraderAgent()
    token = _start_grading(agent)
    # 学生补交新版本：改 seed 里的 body_hash
    agent.lms._seed["submissions"]["S1001"]["body_hash"] = "sha256:S1001-body-v2"  # noqa: SLF001
    res = agent.resume(
        {
            "session_id": "drift",
            "resume_token": token,
            "approved_action": {"decision": "approve", "instructor_id": "ins-001"},
        }
    )
    assert res["status"] == "blocked"
    assert res["reason"] == "business_fact_drift"
    assert res["business_recheck"]["passed"] is False
    assert "submission_body_hash" in res["business_recheck"]["drift_fields"]


def test_rubric_version_drift():
    agent = GraderAgent()
    token = _start_grading(agent)
    # 教师改了 rubric 版本
    agent.lms._seed["submissions"]["S1001"]["rubric_version"] = "v2.0"  # noqa: SLF001
    res = agent.resume(
        {
            "session_id": "drift",
            "resume_token": token,
            "approved_action": {"decision": "approve", "instructor_id": "ins-001"},
        }
    )
    assert res["status"] == "blocked"
    assert res["reason"] == "business_fact_drift"


def test_similarity_score_update():
    agent = GraderAgent()
    token = _start_grading(agent)
    # 查重报告更新：相似度升高
    agent.lms._seed["submissions"]["S1001"]["similarity_score"] = 0.91  # noqa: SLF001
    res = agent.resume(
        {
            "session_id": "drift",
            "resume_token": token,
            "approved_action": {"decision": "approve", "instructor_id": "ins-001"},
        }
    )
    assert res["status"] == "blocked"
    assert res["reason"] == "business_fact_drift"
