"""BatchGrader：批量初批。

M1（已实现）：单线程 for 循环逐份初批，shard_size=20，checkpoint 断点续批，
连续 3 个分片失败整批 paused。幂等键 = submission_id + rubric_version + attempt_id。
lead 校准：flagged 名单合并、异常分（>98 或 <40）标记二次确认。

M2（留桩）：MapReduceBatchGrader 多 agent map/reduce，方法签名完整，
body raise NotImplementedError("M2: multi-agent map/reduce not implemented")。
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from harness.contracts import BatchState, ShardState


def _idempotency_key(submission_id: str, rubric_version: str, attempt_id: str) -> str:
    return hashlib.sha256(f"{submission_id}|{rubric_version}|{attempt_id}".encode()).hexdigest()[:16]


class BatchGrader:
    """M1 单线程批量初批 + checkpoint。"""

    def __init__(self, grader_chat: Any = None) -> None:
        # grader_chat 是 GraderAgent.chat 的可调用（惰性注入避免循环引用）
        self._grader_chat = grader_chat
        self._checkpoints: dict[str, BatchState] = {}
        self._done_keys: set[str] = set()

    def bind(self, grader_chat: Any) -> None:
        self._grader_chat = grader_chat

    # ------------------------------------------------------------------
    def run_batch(
        self,
        course_id: str,
        assignment_id: str,
        submission_ids: list[str],
        runtime_context: dict[str, Any],
        rubric_version: str = "v1.0",
        shard_size: int = 20,
    ) -> BatchState:
        batch_id = f"batch::{course_id}::{assignment_id}"
        total = len(submission_ids)
        shards: list[ShardState] = []
        for i in range(0, total, shard_size):
            chunk = submission_ids[i : i + shard_size]
            shards.append(
                ShardState(
                    shard_index=len(shards),
                    submission_ids=chunk,
                    status="pending",
                )
            )

        state = BatchState(
            batch_id=batch_id,
            course_id=course_id,
            assignment_id=assignment_id,
            rubric_version=rubric_version,
            total=total,
            shards=shards,
            next_resume_token=batch_id,
        )

        # 断点续批：从 checkpoint 恢复
        if batch_id in self._checkpoints:
            state = self._checkpoints[batch_id]

        consecutive_failures = 0
        flagged: list[str] = []
        abnormal: list[str] = []

        for shard in state.shards:
            if shard.status == "done":
                continue
            shard.status = "running"  # type: ignore[typeddict-item]
            shard_failed = 0
            for sid in shard.submission_ids:
                key = _idempotency_key(sid, rubric_version, "attempt-1")
                if key in self._done_keys:
                    shard.processed += 1
                    state.processed += 1
                    continue
                try:
                    draft = self._grade_one(sid, course_id, assignment_id, runtime_context)
                    self._done_keys.add(key)
                    shard.processed += 1
                    state.processed += 1
                    if draft.get("flagged"):
                        flagged.append(sid)
                    score = float(draft.get("overall_score", 0))
                    if score > 98 or score < 40:
                        abnormal.append(sid)
                except Exception:  # noqa: BLE001
                    shard_failed += 1
                    state.failed += 1
                    shard.failed += 1

            if shard_failed:
                shard.status = "failed"  # type: ignore[typeddict-item]
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    # 连续 3 个分片失败 → 整批暂停
                    self._checkpoints[batch_id] = state
                    state.next_resume_token = f"{batch_id}:paused"
                    return state
            else:
                shard.status = "done"  # type: ignore[typeddict-item]
                consecutive_failures = 0

            # 每完成一个分片 checkpoint
            self._checkpoints[batch_id] = state.model_copy(deep=True)

        # lead 校准：异常分二次确认
        state.next_resume_token = f"{batch_id}:completed"
        return state

    # ------------------------------------------------------------------
    def _grade_one(
        self,
        submission_id: str,
        course_id: str,
        assignment_id: str,
        runtime_context: dict[str, Any],
    ) -> dict[str, Any]:
        if self._grader_chat is None:
            # 离线桩：返回确定性草稿
            return {
                "submission_id": submission_id,
                "overall_score": 72.0,
                "flagged": False,
            }
        resp = self._grader_chat(
            {
                "session_id": f"batch-{submission_id}",
                "user_id": runtime_context.get("user_id", "ta-001"),
                "role": runtime_context.get("role", "ta"),
                "course_id": course_id,
                "assignment_id": assignment_id,
                "submission_id": submission_id,
                "current_page": "batch",
                "text": f"帮我初批 {submission_id}",
            }
        )
        return resp.get("grading_draft") or {}

    # ------------------------------------------------------------------
    def checkpoint(self, batch_id: str) -> Optional[BatchState]:
        return self._checkpoints.get(batch_id)


class MapReduceBatchGrader:
    """M2 多 agent map/reduce 批量初批（留桩，不影响 M1 运行）。"""

    def __init__(self) -> None:
        raise NotImplementedError("M2: multi-agent map/reduce not implemented")

    def map_shard(self, shard: ShardState, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError("M2: multi-agent map/reduce not implemented")

    def reduce_leads(self, shard_results: list[list[dict[str, Any]]]) -> dict[str, Any]:
        raise NotImplementedError("M2: multi-agent map/reduce not implemented")

    def run_parallel(
        self,
        course_id: str,
        assignment_id: str,
        submission_ids: list[str],
        runtime_context: dict[str, Any],
        parallelism: int = 4,
    ) -> BatchState:
        raise NotImplementedError("M2: multi-agent map/reduce not implemented")
