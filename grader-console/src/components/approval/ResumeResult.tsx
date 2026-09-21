import { Alert, Tag } from '@arco-design/web-react';
import type { ApprovalResponse } from '../../api/types';

const STATUS_MAP: Record<string, { type: 'success' | 'warning' | 'error' | 'info'; title: string }> = {
  recorded: { type: 'success', title: '审批通过 · 已录分' },
  rejected: { type: 'error', title: '已驳回' },
  paused: { type: 'warning', title: '已暂停 · 等待补充材料' },
  blocked: { type: 'error', title: '审批被阻断' },
  idempotent_replay: { type: 'info', title: '幂等重放 · 无重复副作用' },
};

export function ResumeResult({ result }: { result: ApprovalResponse }) {
  const meta = STATUS_MAP[result.status] ?? { type: 'info' as const, title: result.status };

  return (
    <div style={{ marginTop: 12 }}>
      <Alert type={meta.type} content={
        <div>
          <div style={{ fontWeight: 600 }}>{meta.title}</div>
          <div style={{ marginTop: 4 }}>{result.answer}</div>
          {result.idempotent_replay && (
            <div className="small muted" style={{ marginTop: 4 }}>重复提交命中幂等键，未再次执行副作用。</div>
          )}
          {result.status === 'blocked' && result.reason === 'business_fact_drift' && (
            <div style={{ marginTop: 4 }}>
              漂移字段：
              {(result.business_recheck?.drift_fields ?? []).map((f) => (
                <Tag key={f} size="small" color="red" style={{ marginLeft: 4 }}>{f}</Tag>
              ))}
              <span className="small muted">（已回到 draft_graded 重新初批）</span>
            </div>
          )}
          {result.status === 'recorded' && result.recorded_actions?.length ? (
            <div style={{ marginTop: 4 }} className="small muted">
              执行动作：{result.recorded_actions.join('、')}
            </div>
          ) : null}
        </div>
      } />
    </div>
  );
}
