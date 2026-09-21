import { Tag, Empty } from '@arco-design/web-react';
import type { ChatResponse } from '../../api/types';
import { StageTimeline } from './StageTimeline';
import { ToolCallCard } from './ToolCallCard';
import { LoopCounter } from './LoopCounter';
import { RagPanel } from './RagPanel';
import { GradingDraftView } from '../grading/GradingDraftView';

const ROUTE_COLOR: Record<string, string> = {
  tool_readonly: 'blue',
  rag: 'cyan',
  workflow_human: 'purple',
  deterministic: 'gray',
  deterministic_fallback: 'orange',
  deterministic_block: 'red',
  task_planner: 'arcoblue',
};

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
          <Tag color={ROUTE_COLOR[resp.route_kind] ?? 'gray'}>{resp.route_kind}</Tag>
          <Tag size="small" color="gray">{resp.intent}</Tag>
          <LoopCounter count={toolCalls.length} />
        </div>
        {resp.signals.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {resp.signals.map((s) => (
              <Tag key={s} size="small" color="gray">{s}</Tag>
            ))}
          </div>
        )}
      </div>

      <StageTimeline resp={resp} />

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
