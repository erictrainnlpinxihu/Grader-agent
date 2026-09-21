import type { PendingApproval } from '../../api/types';

const FIELD_LABEL: Record<string, string> = {
  submission_body_hash: '作业正文 hash',
  rubric_version: '评分标准版本',
  similarity_score: '相似度分',
  submission_timestamp: '提交时间',
};

export function CheckpointPanel({ pending }: { pending: PendingApproval }) {
  const fields = pending.frozen_fields ?? {};
  return (
    <div>
      <div className="small muted" style={{ marginBottom: 6 }}>
        冻结现场（恢复时重新拉取逐字段比对，漂移则拒绝执行）
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <tbody>
          {Object.entries(FIELD_LABEL).map(([key, label]) => {
            const v = (fields as Record<string, unknown>)[key];
            return (
              <tr key={key}>
                <td style={{ padding: '4px 8px', borderBottom: '1px solid var(--clr-border-light)', color: 'var(--clr-text-3)', width: 140 }}>
                  {label}
                </td>
                <td className="mono" style={{ padding: '4px 8px', borderBottom: '1px solid var(--clr-border-light)' }}>
                  {v === undefined || v === null || v === '' ? '—' : String(v)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
