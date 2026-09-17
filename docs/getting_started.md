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
| `pydantic` v2 | 所有请求/响应/领域契约（`model_validator` 跨字段校验） |
| `langchain` / `langchain-openai` / `langgraph` | 只读 ReAct 回路与 ApprovalGate StateGraph |
| `httpx` | LMS 只读客户端与在线 embedding 调用 |
| `pyyaml` | `eval/cases.yml` 与 prompts registry 读取 |
| `pytest` | 单元测试 |

> 离线回归**不需要**任何真实模型服务：三个 `GRADER_OFFLINE_*` / `GRADER_DISABLE_LLM` 开关打开后，模型与 LMS 全部走内置替身。

---

## 2. 环境变量总览（9 个 GRADER_* 变量）

Grader 的设计目标是：**不依赖真实 LLM、不依赖真实 LMS，也能端到端跑通主链路并断言行为。** 在线/离线由下表 9 个开关切换。所有变量均以 `GRADER_` 前缀命名。

| 环境变量 | 作用 | 默认值 |
|---|---|---|
| `GRADER_DISABLE_LLM` | `=1` 时禁用所有 LLM，意图路由 / query 改写 / 批改草稿全部走规则兜底 | 未设置 = 在线（调用真实 LLM） |
| `GRADER_OFFLINE_RAG` | `=1` 时 RAG 用本地确定性 token embedding 替身 | 未设置 = 在线 embedding |
| `GRADER_OFFLINE_FACTS` | `=1` 时允许 LMS 数据回退到内置 seed mirror | 未设置 = 不回退（实连 LMS） |
| `GRADER_LLM_API_KEY` | 对话模型 API key；占位串会被识别为缺失 | 无（未配置时在线模式拒绝发起模型调用） |
| `GRADER_LLM_BASE_URL` | OpenAI 兼容模型服务端点 | `https://api.siliconflow.cn/v1` |
| `GRADER_LLM_MODEL` | 对话模型名 | `Qwen/Qwen3-8B` |
| `GRADER_EMBEDDING_MODEL` | embedding 模型名 | `BAAI/bge-m3` |
| `GRADER_ENV_FILE` | 自定义 env 文件路径，可覆盖默认加载位置 | 项目上级目录的 `course.env` |
| `GRADER_FIXED_DATE` | 覆盖系统基准日期，便于时间相关 case 可复现 | 未设置 = 使用默认基准日 |

**加载顺序**：`GRADER_ENV_FILE` 指定的 env 文件 → 进程环境变量（覆盖文件值）。命令行临时变量优先于文件。

---

## 3. 30 秒跑通离线回归

不需要任何 API key、不联网：

```bash
GRADER_DISABLE_LLM=1 GRADER_OFFLINE_RAG=1 GRADER_OFFLINE_FACTS=1 python -m eval.runner
```

- `GRADER_DISABLE_LLM=1`：所有 LLM 调用替换为规则替身；
- `GRADER_OFFLINE_RAG=1`：RAG 检索走本地 token embedding 替身（同文本永远同向量，可字节级复跑）；
- `GRADER_OFFLINE_FACTS=1`：LMS 数据回退到内置 seed mirror 虚构数据。

三者组合即可在一台干净机器上端到端跑通 20 个离线 case；离线模式连跑 3 次结果字节级一致。

> 也可以不经 HTTP、直接由 API 触发：启动服务后 `POST /eval/run`，详见 [api.md](./api.md#6-离线评测-post-evalrun)。

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

也可把上述写进 `course.env`（或 `GRADER_ENV_FILE` 指向的文件），避免每次 export。

> 在线模式仍**不直连真实 LMS 写成绩**：4 个高风险写动作永远只到 `HighRiskProposal`，等讲师审批。

---

## 5. 启动 HTTP 服务

在仓库根目录（`pyproject.toml` 所在目录）启动，离线三开关下无需任何 key：

```bash
GRADER_DISABLE_LLM=1 GRADER_OFFLINE_RAG=1 GRADER_OFFLINE_FACTS=1 \
  python -m uvicorn api.routes:app --host 0.0.0.0 --port 8000
```

等价写法：`cd api && python main.py`（内部同样启动 `api.routes:app`，固定 8000 端口）。默认监听 `0.0.0.0:8000`，启动后访问 `http://localhost:8000`；端口被占用时改 `--port`。8 个端点与请求/响应字段见 [api.md](./api.md)。

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
| `stu-001` | 学生账号（student） |
| `ta-001` | 助教账号（TA），可发起初批、可查授课班内学生成绩 |
| `ins-001` | 主讲教师账号（instructor），唯一可审批录分 / 判不端 / 公开评语的角色 |

每条 seed mirror 记录都带 `_fact_source=grader_seed_mirror` 标记，明确"这是离线替身，不是在线事实"。替身数据**默认不启用**，只有设置 `GRADER_OFFLINE_FACTS=1` 才允许回退，且永远不冒充在线 LMS 数据。

---

## 7. 常见问题（FAQ）

**Q1：我没有任何 LLM key，能跑起来吗？**
能。用离线三开关即可：`GRADER_DISABLE_LLM=1 GRADER_OFFLINE_RAG=1 GRADER_OFFLINE_FACTS=1 python -m eval.runner`。模型、embedding、LMS 全部走确定性替身，连跑 3 次字节级一致。

**Q2：在线模式启动后一调 `/chat` 就报缺 key？**
说明 `GRADER_LLM_API_KEY` 未设置或被识别为占位串。在线模式下 Grader 不会伪造模型输出；要么配上真实 key，要么加 `GRADER_DISABLE_LLM=1` 走规则兜底。

**Q3：设置了 `GRADER_OFFLINE_FACTS=1`，为什么查不到真实 LMS 里的作业？**
因为这个开关的语义就是"**允许**回退到 seed mirror 替身"，而不是"切换数据源"。要连真实 LMS，请**不要**设置它，并在 `harness/lms_client.py` 里配置真实只读端点。替身永远不冒充在线数据。

**Q4：学生在聊天里自称"我是老师"，Grader 会信吗？**
不会。`claimed_role` 仅用于展示，授权一律以 LMS 授课名单快照仲裁；自称讲师但快照不是讲师的请求，记 `identity_claim_override_rejected` 并按学生权限处理。详见 [api.md 角色与鉴权](./api.md#1-角色与鉴权约定)。

**Q5：审批时提示 `blocked/business_fact_drift` 是什么意思？**
ApprovalGate 恢复时会重新拉一次现场，与暂停时冻结的四个字段（`submission_body_hash` / `rubric_version` / `similarity_score` / `submission_timestamp`）逐字段比对。审批期间学生补交了新版本、rubric 升级或相似度报告更新，都会触发漂移——这是**故意**的安全行为：拒绝执行过期决策，重新排队等讲师。详见 [api.md 错误情形](./api.md#8-错误情形漂移与幂等)。

**Q6：trace 里为什么看不到学生学号 / 姓名 / 聊天原文？**
`grader_trace_v1` 递归脱敏是强制的：学号 / 姓名 / 邮箱 / 手机号掩码，`system_prompt` 与 hidden reasoning 删除，注入攻击原文只记位置 + 长度 + sha256 + 命中正则名。这是红线，不提供关闭开关。

**Q7：时间相关的 case 在不同日期跑结果不一样怎么办？**
用 `GRADER_FIXED_DATE=2026-09-15` 锁定基准日期，即可让"距截止还有几天""本次提交时间戳"等时间相关判定可复现。

**Q8：`pip install -e .` 之后 `python -m eval.runner` 找不到模块？**
确认当前工作目录在仓库根目录（与 `pyproject.toml` 同级），且已激活装过依赖的虚拟环境。`eval/` 是包，必须从仓库根以 `python -m eval.runner` 运行，而不是 `python eval/runner.py`。
