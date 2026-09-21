"""uvicorn 便捷入口：在**项目根目录**执行 ``python -m api.main``。

ASGI 应用对象定义在 :mod:`api.routes`（即 ``api.routes:app``）。导入路由模块时
会经 ``agent.llm`` 间接导入 ``harness.config``，从而在任何单例构造前读入 ``.env``。
也可以直接运行：``python -m uvicorn api.routes:app --host 0.0.0.0 --port 8000``。
"""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.routes:app", host="0.0.0.0", port=8000, reload=True)
