"""FastAPI 路由：8 端点。进程级单例注入。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.loop import GraderAgent
from api.schemas import (
    ApprovalRequest,
    ChatRequest,
    ChatResumeRequest,
    EvalRunRequest,
    FeedbackRequest,
)
from harness.trace import TraceStore, make_event

_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent / "configs" / "grader_manifest.json"
)


def load_manifest() -> dict[str, Any]:
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def create_app() -> FastAPI:
    app = FastAPI(title="grader", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 进程级单例
    grader_agent = GraderAgent()
    trace_store = TraceStore()

    # 让 agent 复用本进程 trace_store
    grader_agent.trace_store = trace_store

    # ------------------------------------------------------------------
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "project": "grader"}

    @app.get("/manifest")
    def manifest() -> dict[str, Any]:
        return load_manifest()

    @app.post("/chat")
    def chat(req: ChatRequest) -> dict[str, Any]:
        return grader_agent.chat(req.model_dump())

    @app.post("/chat/resume")
    def chat_resume(req: ChatResumeRequest) -> dict[str, Any]:
        approved_action = dict(req.approved_action)
        if req.decision and "decision" not in approved_action:
            approved_action["decision"] = req.decision
        if req.instructor_id and "instructor_id" not in approved_action:
            approved_action["instructor_id"] = req.instructor_id
        return grader_agent.resume(
            {
                "session_id": req.session_id,
                "resume_token": req.resume_token,
                "approved_action": approved_action,
            }
        )

    @app.get("/sessions/{session_id}/trace")
    def session_trace(session_id: str) -> dict[str, Any]:
        events = trace_store.list(session_id)
        return {"session_id": session_id, "events": [e.model_dump() for e in events]}

    @app.post("/eval/run")
    def eval_run(req: EvalRunRequest) -> dict[str, Any]:
        from eval.runner import EvalRunner

        runner = EvalRunner()
        return runner.run(req.case_id)

    @app.post("/feedback/submit")
    def feedback_submit(req: FeedbackRequest) -> dict[str, Any]:
        from eval.feedback import FailureAttributor

        attributor = FailureAttributor()
        events = [e.model_dump() for e in trace_store.list(req.session_id)]
        attribution = attributor.attribute(req.session_id, events, req.feedback_text)
        backfilled = attributor.build_backfilled_case(req.model_dump(), attribution)
        trace_store.add(
            make_event("feedback_received", req.session_id, {"case_id": req.case_id})
        )
        trace_store.add(
            make_event("failure_attributed", req.session_id, {"dimensions": attribution["dimensions"]})
        )
        trace_store.add(
            make_event("backfilled_case_built", req.session_id, {"case_id": backfilled.get("case_id")})
        )
        return {
            "session_id": req.session_id,
            "attribution": attribution,
            "backfilled_case": backfilled,
        }

    @app.post("/sessions/{session_id}/approval")
    def session_approval(session_id: str, req: ApprovalRequest) -> dict[str, Any]:
        resume_token = req.resume_token or grader_agent._session_resume_token.get(session_id)  # noqa: SLF001
        if not resume_token:
            return {
                "session_id": session_id,
                "status": "blocked",
                "reason": "checkpoint_not_found",
                "answer": "没有找到待审批的工作流。",
            }
        return grader_agent.resume(
            {
                "session_id": session_id,
                "resume_token": resume_token,
                "approved_action": {
                    "decision": req.decision,
                    "instructor_id": req.instructor_id,
                    "submission_id": req.submission_id,
                    "reason": req.reason,
                },
            }
        )

    return app


app = create_app()
