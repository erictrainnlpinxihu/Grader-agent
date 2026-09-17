"""uvicorn 入口：python api/main.py 启动。

flat layout：入口为 ``api.main:app``。
"""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
