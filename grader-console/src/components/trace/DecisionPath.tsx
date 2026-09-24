import { Tag, Empty } from '@arco-design/web-react';
import type { ChatResponse } from '../../api/types';
import { StageTimeline } from './StageTimeline';
import { ToolCallCard } from './ToolCallCard';
import { LoopCounter } from './LoopCounter';
import { RagPanel } from './RagPanel';
import { PlanGuardPanel } from './PlanGuardPanel';
import { PerformanceCard } from './PerformanceCard';
import { GradingDraftView } from '../grading/GradingDraftView';
import { ROUTE_COLOR, signalColor, signalHint } from './tagColors';

/** 标签颜色图例：与 tagColors.ts 的语义一一对应 */
const LEGEND: { color: string; text: string }[] = [
  { color: 'red', text: '拦截' },
  { color: 'purple', text: '转人工' },
  { color: 'gold', text: '待审批' },
  { color: 'cyan', text: '检索命中' },
  { color: 'blue', text: '正常执行' },
  { color: 'orange', text: '降级/兜底' },
  { color: 'gray', text: '中性状态' },
];

export function DecisionPath({ resp }: { resp: ChatResponse | null }) {
  if (!resp) {
    return <Empty description="发送问题后这里展示完整决策路径" />;
  }

  const toolCalls = resp.tool_calls ?? [];

  return (
    <div>
      <div className="detail-card">
        <div className="head">
          <strong>本次决策</strong>
          <span title="路线种类：这次请求走的执行路线（7 选 1）">
            <Tag color={ROUTE_COLOR[resp.route_kind] ?? 'gray'}>{resp.route_kind}</Tag>
          </span>
          <span title="语义意图：系统理解出的用户诉求（12 选 1）">
            <Tag size="small" color="gray">{resp.intent}</Tag>
          </span>
          <span title="只读工具回路的循环次数，达到上限 6 会强制停止（红色）">
            <LoopCounter count={toolCalls.length} />
          </span>
        </div>
        {resp.signals.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {resp.signals.map((s) => (
              <span key={s} title={signalHint(s)}>
                <Tag size="small" color={signalColor(s)}>{s}</Tag>
              </span>
            ))}
          </div>
        )}
        <div className="small muted" style={{ marginTop: 8, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <span>颜色图例：</span>
          {LEGEND.map((l) => (
            <span key={l.text} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Tag size="small" color={l.color} style={{ margin: 0 }}>{l.text}</Tag>
            </span>
          ))}
          <span>（悬停标签可看含义）</span>
        </div>
      </div>

      <StageTimeline resp={resp} />

      <PlanGuardPanel resp={resp} />

      {toolCalls.length > 0 && (
        <div className="detail-card">
          <div className="head">
            <strong>工具调用明细</strong>
            <LoopCounter count={toolCalls.length} />
          </div>
          {toolCalls.map((c, i) => (
            <ToolCallCard key={i} call={c} index={i} />
          ))}
        </div>
      )}

      <RagPanel citations={resp.citations} cacheHit={resp.session_state.rag?.cache_hit} />

      {resp.grading_draft && <GradingDraftView draft={resp.grading_draft} />}

      <PerformanceCard resp={resp} />

      <div className="detail-card">
        <div className="head">
          <strong>大模型回复</strong>
          {resp.trace_events.some((e) => e.event === 'model_answer_skipped') && (
            <Tag size="small" color="orange">本次跳过最终模型润色</Tag>
          )}
        </div>
        <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>{resp.answer}</div>
      </div>
    </div>
  );
}
