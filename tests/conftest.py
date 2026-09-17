"""pytest 全局夹具：强制离线三开关。"""

from __future__ import annotations

import os

os.environ.setdefault("GRADER_DISABLE_LLM", "1")
os.environ.setdefault("GRADER_OFFLINE_RAG", "1")
os.environ.setdefault("GRADER_OFFLINE_FACTS", "1")
