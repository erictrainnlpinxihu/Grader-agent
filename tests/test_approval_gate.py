"""ApprovalGate 三道闸 + 状态机单元测试。"""

from __future__ import annotations

from harness.approval_gate import ApprovalGate
from harness.contracts import HighRiskProposal


def _proposal(submission_id: str = "S1001") -> HighRiskProposal:
    return HighRiskProposal(
        action="record_final_grade",
        submission_id=submission_id,
        proposed_payload={"total_score": 66},
        frozen_fields={
            "submission_body_hash": "sha256:S1001-body-v1",
            "rubric_version": "v1.0",
            "similarity_score": 0.25,
            "submission_timestamp": "2026-07-10T14:30:00",
        },
    )


def _gate_with_checkpoint() -> tuple[ApprovalGate, str]:
    gate = ApprovalGate()
    cp = gate.create_checkpoint("S1001", "draft_graded", _proposal().frozen_fields, _proposal())
    return gate, cp["resume_token"]


def test_invalid_resume_token():
    gate = ApprovalGate()
    res = gate.resume(
        "bogus-token", "approved",
        approved_instructor_id="ins-001", current_frozen={}, timestamp_bucket="2026-09-17",
    )
    assert res["status"] == "blocked"
    assert res["reason"] == "invalid_resume_token"


def test_business_fact_drift():
    gate, token = _gate_with_checkpoint()
    drifted = {
        "submission_body_hash": "sha256:S1001-body-v2",  # 学生换了版本
        "rubric_version": "v1.0",
        "similarity_score": 0.25,
        "submission_timestamp": "2026-07-10T14:30:00",
    }
    res = gate.resume(
        token, "approved",
        approved_instructor_id="ins-001", current_frozen=drifted, timestamp_bucket="2026-09-17",
    )
    assert res["status"] == "blocked"
    assert res["reason"] == "business_fact_drift"
    assert res["drift_field"] == "submission_body_hash"


def test_idempotent_replay():
    gate, token = _gate_with_checkpoint()
    frozen = _proposal().frozen_fields
    r1 = gate.resume(
        token, "approved",
        approved_instructor_id="ins-001", current_frozen=frozen, timestamp_bucket="2026-09-17",
    )
    assert r1["status"] == "recorded"
    assert r1["idempotent_replay"] is False
    # 重复 resume
    r2 = gate.resume(
        token, "approved",
        approved_instructor_id="ins-001", current_frozen=frozen, timestamp_bucket="2026-09-17",
    )
    assert r2["idempotent_replay"] is True


def test_state_transitions():
    gate = ApprovalGate()
    assert gate.transition("received", "draft_graded") == "draft_graded"
    assert gate.transition("draft_graded", "flagged") == "flagged"
    assert gate.transition("flagged", "approved") == "approved"
    assert gate.transition("approved", "recorded") == "recorded"


def test_rejected_path():
    gate, token = _gate_with_checkpoint()
    frozen = _proposal().frozen_fields
    res = gate.resume(
        token, "rejected",
        approved_instructor_id="ins-001", current_frozen=frozen, timestamp_bucket="2026-09-17",
    )
    assert res["status"] == "rejected"
    assert res["accepted"] is False
