# Grader —— 工程指南

> 面向 agentic coding 助手的精简工程约定，只规定开发语言、框架与目录。

## 1. 开发语言

- **Python 3.11+**
- 全量 type hints，公共函数签名必须标注
- 数据校验统一用 **Pydantic v2**；跨字段校验用 `model_validator(mode="after")`

## 2. 框架

| 用途 | 框架 / 约定 |
|---|---|
| HTTP 接入 | FastAPI（8 端点，只做收发与契约校验） |
| 数据契约 | Pydantic v2（`harness/contracts.py`） |
| 高风险状态机 + 批量 map/reduce | LangGraph（仅 ApprovalGate 与 M2 批量分片） |
| 只读工具回路 | 普通函数 + `create_agent` 白名单，**不走 graph** |
| 测试 | pytest；所有测试须在 `GRADER_DISABLE_LLM=1` + fake_embedding 下可跑 |

**命名约定**：模块名 / 函数名与目录结构一致，不做同义改名（如 `route_guard` 不写成 `router_guard`，`ApprovalGate` 不写成 `ApprovalWorkflow`，`HighRiskProposal` 不写成 `GradeAction`）。

## 3. 目录说明

```
grader/
├── api/                          # HTTP 接入层
│   ├── main.py                  # FastAPI 入口（uvicorn 0.0.0.0:8000）
│   ├── routes.py                # 8 端点路由
│   └── schemas.py               # HTTP 请求/响应 Pydantic 契约
├── agent/                        # 模型回路（模型被调用的地方）
│   ├── loop.py                  # 五阶段主 loop GraderAgent
│   ├── intent_router.py         # 语义意图路由（LLM + with_structured_output）
│   ├── query_rewrite.py         # QueryRewrite 结构化改写
│   ├── react_loop.py            # 只读 ReAct 工具回路（白名单对账）
│   ├── batch_mapreduce.py       # 批量 map/reduce（M1 单线程 / M2 分片并行）
│   └── final_answer.py          # 最终答案生成（六种 skip 边界）
├── rag/                          # 知识检索
│   ├── build_index.py           # 索引构建（切块 + 向量入库）
│   ├── hybrid_retrieval.py      # 向量 + 关键词 hybrid 召回
│   ├── rerank.py                # 合并重排
│   ├── cache.py                 # 索引缓存 + 检索缓存
│   ├── embedding.py             # embedding 双轨（在线 / 离线替身）
│   └── knowledge/               # 知识文档（4 索引域 md + 政策直挂 md）
├── harness/                      # 确定性脚手架
│   ├── route_guard.py           # rule_guard / rule_veto 一票否决
│   ├── permissions.py           # 三级权限矩阵 + LMS 身份快照仲裁
│   ├── source_guard.py          # 防注入（三级信任标 + 注入正则）
│   ├── approval_gate.py         # ApprovalGate + 冻结字段 + 审批授权 + resume 三道闸
│   ├── context_builder.py       # ContextBuilder + 记忆 + 历史压缩
│   ├── trace.py                 # grader_trace_v1 递归脱敏
│   ├── hooks.py                 # 生命周期 hook（工具前后 / 错误 / 完成）
│   ├── cost.py                  # 成本治理
│   ├── tool_runtime.py          # 只读工具运行时 + HighRiskProposal 提案器
│   ├── lms_client.py            # LMS 只读客户端（实连 / mock 双轨）
│   ├── config.py                # .env 自动加载 + get_bool/get_str
│   ├── prompts/                 # 8 片段 registry（prompt_registry.yml + loader.py + 片段 md）
│   └── contracts.py             # 领域 Pydantic 契约
├── eval/                         # 评测与反馈
│   ├── cases.yml                # 21 个离线 eval case
│   ├── runner.py                # EvalRunner（含一致性双跑等 5 项扩展）
│   └── feedback.py              # 负反馈归因 + 回归 case 回填
├── docs/                         # 面向使用者的文档
│   ├── getting_started.md       # 安装 / 环境变量 / 离线三开关 / 启动 / FAQ
│   ├── api.md                   # 8 端点 HTTP 契约
│   ├── agent.md                 # Agent 模型回路专题
│   ├── rag.md                   # RAG 检索专题
│   ├── harness.md               # Harness 安全骨架专题
│   └── engineering.md           # 生产化升级方案
├── configs/                      # .env.example / grader_manifest.json / seed_data.json
├── tests/                        # 单元测试
├── pyproject.toml               # 项目依赖与元数据
├── CLAUDE.md                    # 本文件（agentic coding 工程指南）
└── README.md                    # 开源首页
```