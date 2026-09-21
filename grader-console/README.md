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

- **首页链路简介**：顶部可展开卡片，用业务语言讲五阶段固定流程
  （认身份 → 定路线 → 查证取料 → 核对材料 → 给出草稿）与"模型只提议 · 规则可否决 · 教师拍板"的护栏叙事，避开技术缩写。
- **调试台**：顶部上下文条（角色/课程/作业/submission）+ 示例问题 chips（**按当前角色过滤**，可开"全部角色"；
  点击自动切角色；含一键跑通 RAG + 工具 + HITL 的**多轮综合场景**）；
  左栏对话，右栏完整决策路径（五阶段时间线、工具调用明细、ReAct 循环 n/6、RAG 检索与引用、大模型回复、初批草稿）。
- **RAG 命中质量**：引用分数按 RRF 排名融合上限（≈0.0328）归一化展示，
  标注"双路第 1 · 最强命中"等档位——`score 0.033` 是最强命中而非未命中。
- **HITL 审批**：`needs_human_approval` 时内联审批卡，支持批准 / 驳回 / 补充材料，
  展示冻结现场 4 字段与状态机图，恢复后按 recorded / rejected / paused / drift / 幂等分支渲染。
- **Trace 回放**：按 session_id 查看完整事件流。
- **Eval 回归**：跑单个 case 或全集（请求超时 180s），每个 case 附业务语言的**"测试目标"介绍**
  （下拉选项、明细表列、展开面板三处展示），逐 case 展开可回放决策链路
  （复用 DecisionPath 渲染后端附带的脱敏公开响应）。

构建产物与依赖（`node_modules/`、`dist/` 等）不入 git，见仓库根 `.gitignore`。

## 目录

```text
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
