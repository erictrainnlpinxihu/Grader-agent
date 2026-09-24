# Getting Started — Grader 上手指南

> 本文是 Grader 的安装、配置与启动手册。项目是什么、为什么这么设计，见 [../README.md](../README.md)；HTTP 端点的完整字段与示例，见 [api.md](./api.md)。

---

## 1. 安装

要求 **Python 3.11+**。仓库根目录自带 `pyproject.toml`，建议以可编辑模式安装：

```bash
cd grader   # clone 后的仓库根目录（pyproject.toml 所在目录）
pip install -e .
```

核心依赖（`pip install -e .` 会自动装好）：

| 依赖 | 用途 |
|---|---|
| `fastapi` / `uvicorn` | HTTP 层（`api/main.py`） |
| `pydantic` v2 | 所有请求 / 响应 / 领域模型的数据校验（`model_validator` 跨字段校验） |
| `langchain-openai` | 在线模式的 `ChatOpenAI`（结构化输出 / 生成；离线不导入） |
| `httpx` | LMS 只读客户端与在线 embedding / rerank 调用 |
| `pyyaml` | `eval/cases.yml` 与 prompts registry 读取 |
| `pytest` | 单元测试 |

> `langchain` 与 `langgraph` 已在 `pyproject.toml` 声明，预留给多 agent map/reduce 与图式工作流；当前版本的只读工具回路与审批状态机均为手写确定性实现，运行时只延迟导入 `langchain-openai`。

> 离线回归**不需要**任何真实模型服务：三个 `GRADER_OFFLINE_*` / `GRADER_DISABLE_LLM` 开关打开后，模型与 LMS 全部走内置替身。

---

## 2. 环境变量总览

Grader 的设计目标是：**不依赖真实 LLM、不依赖真实 LMS，也能端到端跑通主链路并断言行为。** 在线/离线由下表开关切换。所有变量均以 `GRADER_` 前缀命名；`harness/config.py` 会在启动时自动加载项目根 `.env`，优先级为 **shell 已导出的环境变量 ＞ `.env` ＞ 代码默认值**（`.env` 只用 setdefault 填补缺失项，不覆盖 shell 里已有的同名变量）。

| 环境变量 | 作用 | 默认值 |
|---|---|---|
| `GRADER_DISABLE_LLM` | `=1` 时禁用所有 LLM，意图路由 / query 改写 / 批改草稿全部走规则兜底 | 未设置 = 在线（调用真实 LLM） |
| `GRADER_OFFLINE_RAG` | `=1` 时 RAG 用本地确定性 token embedding 替身 | 未设置 = 在线 embedding |
| `GRADER_OFFLINE_FACTS` | `=1` 时允许 LMS 数据回退到内置 seed mirror | 未设置 = 不回退（实连 LMS） |
| `GRADER_LLM_API_KEY` | 对话模型 API key；占位串会被识别为缺失 | 无（未配置时在线模式拒绝发起模型调用） |
| `GRADER_LLM_BASE_URL` | OpenAI 兼容模型服务端点 | `https://api.siliconflow.cn/v1` |
| `GRADER_LLM_MODEL` | 对话模型名 | `Qwen/Qwen3-8B` |
| `GRADER_EMBEDDING_MODEL` | embedding 模型名 | `BAAI/bge-m3` |
| `GRADER_RERANK_MODEL` | 在线重排模型名（`POST {GRADER_LLM_BASE_URL}/rerank`；`GRADER_OFFLINE_RAG=1` 或调用失败时走确定性来源权重重排） | `BAAI/bge-reranker-v2-m3` |
| `GRADER_LMS_BASE_URL` | 在线 LMS 只读 API 根地址（仅在线事实用） | `https://lms.example.com/api` |
| `GRADER_LMS_SERVICE_TOKEN` | 委派头 `X-Grader-Service-Token`（仅在线事实用） | `dev-token` |

**用 `.env` 管理配置（推荐）**：把示例文件复制到项目根即可，启动服务或跑 eval 时自动加载，无需逐个 `export`：

```bash
cp configs/.env.example .env
# 离线三开关默认置 1；要接真实模型时填 GRADER_LLM_API_KEY，并把对应开关关掉（删除或置 0）
```

- 加载器从当前工作目录**向上逐级**查找第一个 `.env`，所以在项目根或其子目录启动都能命中；
- 想把配置放在别处，可在 shell 里 `export GRADER_ENV_FILE=/path/your.env` 指定（该变量决定 `.env` 自身的位置，必须由 shell 给定）；
- shell 里已经 `export` 的同名变量优先级更高、不会被 `.env` 覆盖；命令行前缀（如 `GRADER_DISABLE_LLM=1 python ...`）同样优先；
- 支持 `#` 注释、`export` 前缀与成对单 / 双引号；修改 `.env` 后需**重启进程**生效（不做热更新）。

`GRADER_FIXED_DATE`（固定基准日期）是预留的演进项、尚未实现，也未放进示例文件；需要复现时间相关 case 时请在系统层固定日期（见 [生产化升级方案](./engineering.md#6-模型回路强化)）。

---

## 3. 跑测试：eval 回归与 pytest

Grader 有两层测试：**eval 回归**（`eval/cases.yml` 的 21 个 case，进程内直调 `GraderAgent.chat()/resume()` 驱动真实主链路，断言路由 / 守卫 / HITL / 幂等 / 缓存等行为）与 **pytest 单测**（`tests/` 下 47 个，按模块覆盖 ApprovalGate、权限、注入脱敏等）。两者都只断言公开信号，不读 hidden CoT。

**eval 全量回归**——不需要任何 API key、不联网：

```bash
GRADER_DISABLE_LLM=1 GRADER_OFFLINE_RAG=1 GRADER_OFFLINE_FACTS=1 python -m eval.runner
# 输出：total=21 passed=21 failed=0，逐行 [PASS]/[FAIL] <case_id> 与失败原因
```

三个离线开关的含义：

- `GRADER_DISABLE_LLM=1`：所有 LLM 调用替换为规则替身；
- `GRADER_OFFLINE_RAG=1`：RAG 检索走本地 token embedding 替身（同文本永远同向量，可字节级复跑）；
- `GRADER_OFFLINE_FACTS=1`：LMS 数据回退到内置 seed mirror 虚构数据。

三者组合即可在一台干净机器上端到端跑通 21 个离线 case；离线路径是确定性的，重复运行结果一致。

**跑单个 case**——命令行只支持全量，单个 case 起服务后经 HTTP 触发（`case_id` 留空即全量；也可在前端控制台 Eval 页点选）：

```bash
curl -s -X POST http://localhost:8000/eval/run \
  -H 'Content-Type: application/json' -d '{"case_id": "grader-hitl-reject"}'
```

**pytest 单元测试**——`tests/conftest.py` 在收集阶段已强制离线三开关，直接跑即可，无需加环境变量前缀：

```bash
python -m pytest tests/ -q    # 47 passed
```

> 改动任何 `.py` 后，两层都要重跑（eval 21/21 + pytest 47 passed）才算回归通过；`/eval/run` 的字段级说明见 [api.md](./api.md#8-离线评测-post-evalrun)。

### 3.1 评测覆盖了什么

21 个 case（`eval/cases.yml`）按目的分六组：

| 组 | case | 核心验证 |
|---|---|---|
| 基础链路（5） | 状态查询 / rubric 两轮缓存命中 / 大纲检索 / 缓考升级 HITL / 寒暄与低置信兜底 | 只读工具走对、RAG 命中对应域、缓存命中跳模型、低置信追问不调工具 |
| 守卫（2） | 注入越权钉死 / 自称老师与学生查他人 | `deterministic_block`、`identity_claim_override_rejected`、参数级拦截 |
| HITL（7） | approve / reject / needs_more_info / 假令牌 / 幂等重放 / 无 checkpoint / 冻结漂移 | 三道闸逐闸拦截、recorded 不重复执行、漂移字段正确 |
| 安全与公平（2） | 作业正文注入脱敏 / 一致性双跑 | 仍按 rubric 打分不回显原文；同文换署名分差 ≤ 2 |
| 降级与反馈（2） | 服务不可用降级 / 负反馈回填 | 不编造分数、离线话术连跑 3 次字节级一致；反馈归因生成回归 case |
| 高风险与批量（3） | 讲师双分支 / 学生发起学术不端 / 批量 200 份 | 直挂政策 citation 转人工；分片 / checkpoint / parallelism=1 |

runner 支持的断言能力：intent / route_kind / 信号词 / trace 事件名与 payload 点路径（如 `source_safety.tainted=true`）/ session_state 点路径 / citation 来源与检索阶段 / 期望与禁止工具 / 禁止文本；case 类型含多轮（子 session 隔离记忆）、resume（重复恢复与 fixture 变异子场景）、一致性双跑（`score_regex` 抽分 + `max_variance`）、反馈回填，以及同一 case 连跑 N 次字节级一致。反馈闭环：`POST /feedback/submit` 归因后自动生成 `feedback-00N` 回归 case。单测 47 个 pytest 覆盖 ApprovalGate、权限三角色、注入脱敏、幂等与断点续批、路由加固与高风险发起。

边界：**离线只验证工程控制流**（路由、守卫、审批、幂等、缓存），不验证模型语言质量——后者需在线真实 key 实测（见 FAQ Q9）。

---

## 4. 在线模式配置真实模型

要把 Grader 接到真实 LLM，至少配置 key 与模型名：

```bash
export GRADER_LLM_API_KEY="sk-..."
export GRADER_LLM_BASE_URL="https://api.siliconflow.cn/v1"   # 或任意 OpenAI 兼容端点
export GRADER_LLM_MODEL="Qwen/Qwen3-8B"
export GRADER_EMBEDDING_MODEL="BAAI/bge-m3"
# 不设置 GRADER_DISABLE_LLM / GRADER_OFFLINE_RAG，即为在线模式
```

也可以不逐条 `export`，直接把这些键写进项目根 `.env`（`cp configs/.env.example .env` 后编辑），启动时自动加载；shell 已导出的同名变量优先级更高（见 §2）。

> 在线模式仍**不直连真实 LMS 写成绩**：4 个高风险写动作永远只到 `HighRiskProposal`，等讲师审批。

---

## 5. 启动 HTTP 服务

在仓库根目录（`pyproject.toml` 所在目录）启动，离线三开关下无需任何 key：

```bash
GRADER_DISABLE_LLM=1 GRADER_OFFLINE_RAG=1 GRADER_OFFLINE_FACTS=1 \
  python -m uvicorn api.routes:app --host 0.0.0.0 --port 8000
```

等价写法：在仓库根执行 `python -m api.main`（同样启动 `api.routes:app`、固定 8000 端口；请始终在仓库根运行，不要 `cd api` 后直接跑脚本）。默认监听 `0.0.0.0:8000`，启动后访问 `http://localhost:8000`；端口被占用时改 `--port`。8 个端点与请求/响应字段见 [api.md](./api.md)。

最小冒烟：

```bash
curl -s http://localhost:8000/health
# {"status": "ok", "project": "grader"}

curl -s http://localhost:8000/manifest | python -m json.tool
```

---

## 6. seed mirror 虚构数据约定 ID

离线或 `GRADER_OFFLINE_FACTS=1` 时，Grader 回退到内置 seed mirror——一小份代码内置的虚构教学数据。下面这些 ID 可直接用于 curl 示例与调试，**均为虚构样本，不对应任何真实学生 / 课程 / 院校**。

| 约定 ID | 含义 |
|---|---|
| `CS101-2026spring` | 课程 ID（`course_id`） |
| `A3` | 第三次作业（`assignment_id`） |
| `S1001` | 学生 `stu-001`（张三）对 A3 的提交，已收到、可进入初批 |
| `S1002` | 学生 `stu-002`（李四）对 A3 的提交，已审批录入 88/100 |
| `S1003–S1025` | 其余 23 份虚构提交（均 `received`），与 S1001 同模板；批量初批 `shard_size=20` 时切 2 分片（20+5） |
| `stu-001` | 学生账号（student） |
| `ta-001` | 助教账号（TA），可发起初批、可查授课班内学生成绩 |
| `ins-001` | 主讲教师账号（instructor），唯一可审批录分 / 判不端 / 公开评语的角色 |

每条 seed mirror 记录都带 `_fact_source=grader_seed_mirror` 标记，明确"这是离线替身，不是在线事实"。替身数据**默认不启用**，只有设置 `GRADER_OFFLINE_FACTS=1` 才允许回退，且永远不冒充在线 LMS 数据。

---

## 7. 常见问题（FAQ）

**Q1：我没有任何 LLM key，能跑起来吗？**
能。用离线三开关即可：`GRADER_DISABLE_LLM=1 GRADER_OFFLINE_RAG=1 GRADER_OFFLINE_FACTS=1 python -m eval.runner`。模型、embedding、LMS 全部走确定性替身，重复运行结果一致。

**Q2：在线模式启动后一调 `/chat` 就报缺 key？**
说明 `GRADER_LLM_API_KEY` 未设置或被识别为占位串。在线模式下 Grader 不会伪造模型输出；要么配上真实 key，要么加 `GRADER_DISABLE_LLM=1` 走规则兜底。

**Q3：设置了 `GRADER_OFFLINE_FACTS=1`，为什么查不到真实 LMS 里的作业？**
因为这个开关的语义就是"**允许**回退到 seed mirror 替身"，而不是"切换数据源"。要连真实 LMS，请**不要**设置它，并在 `harness/lms_client.py` 里配置真实只读端点。替身永远不冒充在线数据。

**Q4：学生在聊天里自称"我是老师"，Grader 会信吗？**
不会。`claimed_role` 仅用于展示，授权一律以 LMS 授课名单快照仲裁；自称讲师但快照不是讲师的请求，记 `identity_claim_override_rejected` 并按学生权限处理。详见 [api.md 角色与鉴权](./api.md#1-角色与鉴权约定)。

**Q5：审批时提示 `blocked/business_fact_drift` 是什么意思？**
ApprovalGate 恢复时会重新拉一次现场，与暂停时冻结的四个字段（`submission_body_hash` / `rubric_version` / `similarity_score` / `submission_timestamp`）逐字段比对。审批期间学生补交了新版本、rubric 升级或相似度报告更新，都会触发漂移——这是**故意**的安全行为：拒绝执行过期决策，打回重新初批、重新排队等讲师。机制详解见 [Harness · 业务事实漂移与回退](./harness.md#53-业务事实漂移与回退)，HTTP 错误形态见 [api.md 错误情形](./api.md#10-错误情形blocked漂移与幂等)。

**Q6：trace 里为什么看不到学生学号 / 姓名 / 聊天原文？**
`grader_trace_v1` 递归脱敏是强制的：学号 / 姓名 / 邮箱 / 手机号掩码，`system_prompt` 与 hidden reasoning 删除，注入攻击原文只记位置 + 长度 + sha256 + 命中正则名。这是红线，不提供关闭开关。

**Q7：时间相关的 case 在不同日期跑结果不一样怎么办？**
当前版本时间取系统日期；`GRADER_FIXED_DATE` 是预留的演进项、尚未实现、也未放进 `.env.example`。如需复现时间相关判定，请在系统层固定日期（见 [生产化升级方案](./engineering.md#6-模型回路强化)）。

**Q8：`pip install -e .` 之后 `python -m eval.runner` 找不到模块？**
确认当前工作目录在仓库根目录（与 `pyproject.toml` 同级），且已激活装过依赖的虚拟环境。`eval/` 是包，必须从仓库根以 `python -m eval.runner` 运行，而不是 `python eval/runner.py`。

**Q9：没有 LLM / embedding / LMS 时，"离线"到底是怎么模拟出来的？**
三个确定性替身彼此独立、都可字节级复跑：

1. **LLM 替身**：`LLMClient.structured / generate` 一律返回 `None`。意图走关键词路由表、`QueryRewrite` 走正则提取实体、`GradingDraft` 走 `deterministic_score()` 按 rubric 关键词给分、RAG 答案走"依据{域}：{top chunk}"模板。
2. **embedding 替身**：`_offline_embedding` 把文本 SHA-256 摘要反复哈希扩展成 256 维，每字节线性映射到 `[-1,1]` 后 L2 归一化——**同文同向量**，无语义理解但可字节复跑。
3. **LMS 替身**：`GRADER_OFFLINE_FACTS=1` 时回退到 `configs/seed_data.json` 种子镜像（`_fact_source=grader_seed_mirror`），只读返回虚构的课程/作业/提交/成绩数据。

边界要讲清：**离线只验证工程控制流**（路由是否正确、是否走 RAG / 工具 / 审批 / 守卫 / 幂等 / 漂移 / 缓存命中），**不验证模型语言质量与打分合理性**——后者必须切在线真实 key 实测。

**Q10：学生能举报学术不端 / 申诉成绩吗？**
能**发起**，但不能终判——发起权与审批权是分开的。学生 / ta 问"这份作业算不算学术不端"或发起成绩申诉，都会立案（进 `workflow_human`、直挂学术诚信政策 citation、产出提案并暂停等审批），系统不自动处分、不改分；终录 / 终判只有该课主讲教师（种子数据里是 `ins-001`）审批后才落地。学生 / ta 即便拿到审批令牌去调 `/approval`，也会被恢复入口的**审批授权闸（闸 0）**以 `blocked/approver_not_authorized` 拒绝，立案保留、不迁移状态。
