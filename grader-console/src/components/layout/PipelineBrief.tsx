import { useState } from 'react';
import { Tag, Button } from '@arco-design/web-react';

/**
 * 首页链路简介：基于 README 与 docs/frontend-design.md 的五阶段主 loop 摘要。
 * 叙事主线：模型负责提议，规则负责否决，人类教师只在不可逆动作上被叫醒。
 */
const STAGES = [
  {
    key: 'perceive',
    label: '① perceive · 接收',
    desc: 'LMS 授课名单快照仲裁真实角色（用户自称不算数）；source_guard 把用户消息与学生作业正文一律按 Untrusted 检查，注入内容只留哈希。',
  },
  {
    key: 'plan',
    label: '② plan · 规划',
    desc: 'QueryRewrite 结构化改写 → 12 intent 语义路由（模型只提议 intent）→ rule_guard / rule_veto 一票否决横切；工具集 / 路由类型 / 风险等级由代码钉死。',
  },
  {
    key: 'act',
    label: '③ act · 执行',
    desc: '只读 ReAct 白名单 6 工具（温度 0、上限 6 步）· RAG 4+1 域 hybrid 检索（政策域直挂不召回）· 批量分片初批；4 个高风险写动作物理上不在工具表，只能产 HighRiskProposal 进 HITL。',
  },
  {
    key: 'observe',
    label: '④ observe · 观察',
    desc: 'ContextBuilder 按五级信任序组装上下文（runtime_context > 工具事实 > 记忆 > 历史 > 用户输入），Observation 按评分点压缩，成本记账。',
  },
  {
    key: 'respond',
    label: '⑤ respond · 回复',
    desc: '六种 skip-final-model 场景短路直答（安全拦截 / 缓存命中 / 等待审批…）；最终回复带 citations 与 GradingDraft，grader_trace_v1 递归脱敏后落 trace。',
  },
];

export function PipelineBrief() {
  const [open, setOpen] = useState(false);

  return (
    <div className="detail-card" style={{ margin: '12px 16px 0', flex: 'none' }}>
      <div className="head" style={{ justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <strong>Grader 决策链路</strong>
          <span className="mono small muted">
            perceive → plan → act → observe → respond
          </span>
          <Tag size="small" color="arcoblue">模型提议</Tag>
          <Tag size="small" color="orange">规则否决</Tag>
          <Tag size="small" color="green">教师拍板</Tag>
        </div>
        <Button size="mini" type="text" onClick={() => setOpen((o) => !o)}>
          {open ? '收起 ▲' : '链路说明 ▼'}
        </Button>
      </div>

      {!open && (
        <div className="small muted">
          外层五阶段是 harness 驱动的确定性骨架——模型不能跳阶段、不决定何时停；终录成绩 /
          学术不端终判 / 公开评语永远暂停等主讲教师审批。展开查看各阶段要点。
        </div>
      )}

      {open && (
        <div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
            {STAGES.map((s) => (
              <div key={s.key} className="stage-node done">
                <div className="dot" />
                <div>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{s.label}</span>
                  <div className="small muted" style={{ lineHeight: 1.6 }}>{s.desc}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="small muted" style={{ marginTop: 8, lineHeight: 1.7 }}>
            高风险动作走 ApprovalGate：冻结现场 4 字段（body_hash / rubric_version /
            similarity / timestamp）→ 教师审批 → 恢复时过审批授权闸 + 三道闸（令牌 /
            business_recheck 漂移 / 幂等键）。右栏"决策路径"逐次展示以上链路的真实运行
            trace；完整设计见仓库 <code>README.md</code> 与{' '}
            <code>docs/frontend-design.md</code>。
          </div>
        </div>
      )}
    </div>
  );
}
