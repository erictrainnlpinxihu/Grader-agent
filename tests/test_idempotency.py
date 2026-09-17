"""幂等性：重复审批不重复录分；批量 checkpoint 断点续批。"""

from __future__ import annotations

from agent.loop import GraderAgent
from agent.batch_mapreduce import BatchGrader


def _grade_and_approve(agent: GraderAgent):
    r = agent.chat(
        {
            "session_id": "idem",
            "user_id": "ta-001",
            "role": "ta",
            "course_id": "CS101-2026spring",
            "assignment_id": "A3",
            "submission_id": "S1001",
            "text": "帮我批一下 S1001",
        }
    )
    token = r["pending_approval"]["resume_token"]
    return agent.resume(
        {
            "session_id": "idem",
            "resume_token": token,
            "approved_action": {"decision": "approve", "instructor_id": "ins-001"},
        }
    )


def test_duplicate_approval_no_double_record():
    agent = GraderAgent()
    r1 = _grade_and_approve(agent)
    assert r1["status"] == "recorded"
    # 第二次重复 resume 走幂等
    token = agent._session_resume_token["idem"]  # noqa: SLF001
    r2 = agent.resume(
        {
            "session_id": "idem",
            "resume_token": token,
            "approved_action": {"decision": "approve", "instructor_id": "ins-001"},
        }
    )
    assert r2["idempotent_replay"] is True


def test_batch_checkpoint_resume():
    grader = GraderAgent()
    bg = BatchGrader()
    # 跑第一轮
    state = bg.run_batch(
        "CS101-2026spring", "A3", ["S1001", "S1002"],
        {"user_id": "ta-001", "role": "ta"},
    )
    assert state.processed == 2
    assert state.failed == 0
    # 断点续批：已完成的 key 应被跳过（幂等）
    state2 = bg.run_batch(
        "CS101-2026spring", "A3", ["S1001", "S1002"],
        {"user_id": "ta-001", "role": "ta"},
    )
    # 重新进入时 completed 分片跳过，processed 仍为 2（不重复打分）
    assert state2.processed == 2
