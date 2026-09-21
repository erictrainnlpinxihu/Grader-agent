import { Tag } from '@arco-design/web-react';
import type { ChatResponse, TraceEvent } from '../../api/types';

interface Stage {
  key: string;
  label: string;
  desc: (resp: ChatResponse) => string;
  events: string[];
}

const STAGES: Stage[] = [
  {
    key: 'perceive',
    label: '① Perceive · 接收',
    events: ['perceive_input_received', 'context_source_safety_checked'],
    desc: (r) => {
      const ev = r.trace_events.find((e) => e.event === 'context_source_safety_checked');
      const safety = (ev?.payload?.source_safety ?? {}) as { tainted?: boolean };
      return safety.tainted ? 'source_guard 检测到污染，已清洗' : '输入已接收，source_guard 通过';
    },
  },
  {
    key: 'plan',
    label: '② Plan · 规划',
    events: ['route_planned', 'rule_guard_overridden'],
    desc: (r) => {
      const rt = r.session_state.routing;
      const conf = rt?.confidence !== undefined ? `（置信度 ${(rt.confidence * 100).toFixed(0)}%）` : '';
      return `${r.intent} → ${r.route_kind}${conf}`;
    },
  },
  {
    key: 'act',
    label: '③ Act · 执行',
    events: ['tool_called', 'rag_retrieved', 'cache_hit', 'workflow_proposal_created', 'workflow_checkpoint_created', 'policy_citation_pinned', 'task_planned', 'shard_completed'],
    desc: (r) => {
      const parts: string[] = [];
      if (r.tool_calls?.length) parts.push(`${r.tool_calls.length} 次工具调用`);
      if (r.citations.length) parts.push(`${r.citations.length} 条检索`);
      if (r.session_state.rag?.cache_hit) parts.push('缓存命中');
      if (r.session_state.workflow) parts.push('工作流已挂起');
      return parts.length ? parts.join(' · ') : '无工具 / 检索动作';
    },
  },
  {
    key: 'observe',
    label: '④ Observe · 观察',
    events: [],
    desc: (r) => {
      const c = r.cost_summary;
      const bits: string[] = [];
      if (c.tool_calls !== undefined) bits.push(`工具 ${c.tool_calls} 次`);
      if (c.llm_calls !== undefined) bits.push(`模型 ${c.llm_calls} 次`);
      if (c.tokens !== undefined) bits.push(`${c.tokens} tokens`);
      return bits.length ? bits.join(' · ') : '上下文已构建';
    },
  },
  {
    key: 'respond',
    label: '⑤ Respond · 回复',
    events: ['model_answer_skipped', 'resume_completed'],
    desc: (r) => {
      const skip = r.trace_events.find((e) => e.event === 'model_answer_skipped');
      if (skip) return `跳过最终模型（${String((skip.payload as { reason?: string }).reason ?? '')}）`;
      return '已生成最终回复';
    },
  },
];

function eventNames(resp: ChatResponse): Set<string> {
  return new Set(resp.trace_events.map((e: TraceEvent) => e.event));
}

export function StageTimeline({ resp }: { resp: ChatResponse }) {
  const names = eventNames(resp);
  const guardOverride = resp.session_state.routing?.guard_override;

  return (
    <div className="detail-card">
      <div className="head" style={{ justifyContent: 'space-between' }}>
        <strong>决策路径 · 五阶段</strong>
        {guardOverride && (
          <Tag color="red">规则守卫已接管：{resp.session_state.routing?.guard_reason ?? ''}</Tag>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {STAGES.map((s, i) => {
          const hit = s.events.length === 0 || s.events.some((e) => names.has(e));
          const isLast = i === STAGES.length - 1;
          return (
            <div key={s.key} style={{ display: 'flex', gap: 12 }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <div style={{
                  width: 10, height: 10, borderRadius: '50%', marginTop: 6,
                  background: hit ? 'var(--clr-primary)' : '#fff',
                  border: '2px solid var(--clr-primary)',
                }} />
                {!isLast && <div style={{ width: 2, flex: 1, background: 'var(--clr-border)', minHeight: 16 }} />}
              </div>
              <div style={{ paddingBottom: 12 }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{s.label}</div>
                <div className="small muted">{s.desc(resp)}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
