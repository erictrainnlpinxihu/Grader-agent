import { Tag } from '@arco-design/web-react';
import type { ChatResponse, GuardCheck } from '../../api/types';
import { ROUTE_COLOR } from './tagColors';

/** 毫秒 → 人读格式 */
export function fmtMs(ms?: number): string {
  if (ms === undefined) return '-';
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms.toFixed(1)} ms`;
}

/** check 名 → 业务语义（与后端 agent/intent_router.py 守卫链一一对应） */
const CHECK_LABEL: Record<string, string> = {
  protected_intent_net: '受保护意图安全网',
  rule_guard: 'rule_guard 正向锁定',
  veto_intent: '逆向否决（显式语义纠偏）',
  rule_veto: 'rule_veto 角色复核',
};

const CHECK_HINT: Record<string, string> = {
  protected_intent_net: '安全 / 学术不端 / 申诉关键词命中而模型给了更弱意图时，强制纠偏（宁可信其有）',
  rule_guard: '安全 / 权限 / 高风险边界一票否决；高风险意图强制升级为待审批工作流',
  veto_intent: '消息显式语义与模型意图矛盾时采纳显式信号（如"不是让你批，只是问 rubric"）',
  rule_veto: 'route_kind × 风险 × 角色执行前复核，越权动作降级为安全路由',
};

/** verdict → 展示（颜色对齐图例：红=拦截，橙=纠偏/降级，金=升级待审批，绿=通过） */
const VERDICT_VIEW: Record<GuardCheck['verdict'], { label: string; color: string }> = {
  pass: { label: '通过', color: 'green' },
  override: { label: '强制纠偏', color: 'orange' },
  escalate: { label: '升级 workflow', color: 'gold' },
  veto: { label: '否决降级', color: 'red' },
  block: { label: '一票拦截', color: 'red' },
};

export function PlanGuardPanel({ resp }: { resp: ChatResponse }) {
  const plan = resp.session_state.plan;
  const routing = resp.session_state.routing;
  const chain = routing?.guard_chain ?? [];
  const overridden = chain.filter((c) => c.verdict !== 'pass');

  return (
    <>
      <div className="detail-card">
        <div className="head">
          <strong>意图与规划 · plan</strong>
          <Tag size="small" color="gray">{resp.intent}</Tag>
          <Tag size="small" color={ROUTE_COLOR[resp.route_kind] ?? 'gray'}>{resp.route_kind}</Tag>
          {plan?.risk_level === 'high' && <Tag size="small" color="red">高风险</Tag>}
          {plan?.candidate_applied ? (
            <Tag size="small" color="green" title="在线 LLM 候选通过了权威映射的策略约束校验后细化生效（工具/知识域收窄）">
              LLM 候选已采纳
            </Tag>
          ) : (
            <Tag size="small" color="gray" title="计划来自权威 intent 映射（离线 / 模型缺失 / 候选被否时的确定性路线）">
              规则映射
            </Tag>
          )}
        </div>

        {plan ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }}>
              <span className="small muted" style={{ flex: 'none' }}>置信度</span>
              <div style={{ flex: 1, height: 6, background: 'var(--clr-border-light)', borderRadius: 3 }}>
                <div
                  style={{
                    width: `${Math.round(Math.min(1, Math.max(0, plan.confidence)) * 100)}%`,
                    height: 6,
                    borderRadius: 3,
                    background: plan.confidence >= 0.7 ? 'var(--clr-primary)' : 'var(--clr-warning)',
                  }}
                />
              </div>
              <span className="small mono" style={{ flex: 'none' }}>
                {(plan.confidence * 100).toFixed(0)}%
                {plan.confidence < 0.7 ? '（低于阈值 0.7 → 兜底）' : ''}
              </span>
            </div>

            <div className="small" style={{ lineHeight: 1.8 }}>
              <div>
                <span className="muted">结构化改写：</span>
                <span className="mono">{plan.rewritten_query}</span>
              </div>
              {plan.entities && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span className="muted">抽取实体：</span>
                  {plan.entities.submission_id && <Tag size="small" color="arcoblue">submission {plan.entities.submission_id}</Tag>}
                  {plan.entities.course_id && <Tag size="small" color="arcoblue">course {plan.entities.course_id}</Tag>}
                  {plan.entities.assignment_id && <Tag size="small" color="arcoblue">assignment {plan.entities.assignment_id}</Tag>}
                  {!plan.entities.submission_id && !plan.entities.course_id && !plan.entities.assignment_id && (
                    <span className="muted">未识别到课程 / 作业 / 提交实体</span>
                  )}
                </div>
              )}
              {plan.sub_questions?.length > 0 && (
                <div>
                  <span className="muted">子问题分解：</span>
                  {plan.sub_questions.map((q, i) => (
                    <span key={i} className="mono">{i > 0 ? '；' : ''}{q}</span>
                  ))}
                </div>
              )}
            </div>

            {(plan.required_tools?.length ?? 0) > 0 && (
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                <span className="small muted" style={{ lineHeight: '22px' }}>计划工具：</span>
                {plan.required_tools!.map((t) => (
                  <Tag key={t} size="small" color="blue">{t}</Tag>
                ))}
              </div>
            )}
            {(plan.knowledge_domains?.length ?? 0) > 0 && (
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                <span className="small muted" style={{ lineHeight: '22px' }}>知识域：</span>
                {plan.knowledge_domains!.map((d) => (
                  <Tag key={d} size="small" color="cyan">{d}</Tag>
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="small muted">本次响应未携带 plan 明细（早退 / 降级路径）。</div>
        )}
      </div>

      <div className="detail-card">
        <div className="head">
          <strong>守卫链 · guard / veto</strong>
          {overridden.length === 0 ? (
            <Tag size="small" color="green">四道闸全部通过</Tag>
          ) : (
            <Tag size="small" color="red">计划被守卫改写</Tag>
          )}
        </div>
        {chain.length === 0 ? (
          <div className="small muted">
            本次响应未携带守卫链明细（早退 / 降级路径）；
            {routing?.guard_override
              ? `守卫已接管：${routing.guard_reason ?? ''}`
              : '守卫未触发改写。'}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {chain.map((c) => {
              const v = VERDICT_VIEW[c.verdict] ?? { label: c.verdict, color: 'gray' };
              return (
                <div
                  key={c.check}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}
                >
                  <span
                    className="small"
                    style={{ minWidth: 190, fontWeight: 500 }}
                    title={CHECK_HINT[c.check] ?? ''}
                  >
                    {c.verdict === 'pass' ? '✓' : c.verdict === 'block' || c.verdict === 'veto' ? '✕' : '⚠'}
                    {' '}{CHECK_LABEL[c.check] ?? c.check}
                  </span>
                  <Tag size="small" color={v.color}>{v.label}</Tag>
                  {c.reason && <span className="small mono muted">{c.reason}</span>}
                </div>
              );
            })}
            <div className="small muted" style={{ lineHeight: 1.6 }}>
              守卫链是写在代码里的确定性闸（不靠 prompt 提醒）：任何一道命中都会改写 / 否决模型提议的路线。
            </div>
          </div>
        )}
      </div>
    </>
  );
}
