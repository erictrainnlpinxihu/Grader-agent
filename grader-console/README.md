# Grader Console（前端调试台）

React 18 + TypeScript + Vite + Arco Design，对接后端 `grader`（FastAPI）。

## 启动

```bash
npm install
npm run dev        # http://localhost:5173
```

后端需在 `http://localhost:8000` 运行（`python -m api.routes:app` 或 `uvicorn api.routes:app --port 8000`）。
Vite 已配置 `/api` 代理到 `http://localhost:8000`。

## 功能

- **首页链路简介**：顶部可展开卡片，一览五阶段主 loop（perceive → plan → act → observe → respond）
  与"模型提议 · 规则否决 · 教师拍板"的护栏叙事。
- **调试台**：顶部上下文条（角色/课程/作业/submission）+ 示例问题 chips；
  左栏对话，右栏完整决策路径（五阶段时间线、工具调用明细、ReAct 循环 n/6、RAG 检索与引用、大模型回复、初批草稿）。
- **HITL 审批**：`needs_human_approval` 时内联审批卡，支持批准 / 驳回 / 补充材料，
  展示冻结现场 4 字段与状态机图，恢复后按 recorded / rejected / paused / drift / 幂等分支渲染。
- **Trace 回放**：按 session_id 查看完整事件流。
- **Eval 回归**：跑单个 case 或全集（请求超时 180s），逐 case 展开可回放决策链路
  （复用 DecisionPath 渲染后端附带的脱敏公开响应）。

构建产物与依赖（`node_modules/`、`dist/` 等）不入 git，见仓库根 `.gitignore`。

## 目录

```
src/
├── api/        # 类型 + axios + 端点
├── store/      # zustand 会话状态
├── components/
│   ├── layout/  # 侧栏 + 顶栏
│   ├── chat/    # 上下文条 / 示例 / 对话
│   ├── trace/   # 决策路径时间线 / 工具卡 / RAG
│   ├── approval/# HITL 审批卡 / 状态机 / 冻结现场 / 恢复结果
│   └── grading/ # 初批草稿
├── pages/
└── examples/   # 示例问题（源自 eval/cases.yml）
```

设计说明见 `../docs/frontend-design.md`。
