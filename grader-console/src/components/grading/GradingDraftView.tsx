import { Tag } from '@arco-design/web-react';
import type { GradingDraft } from '../../api/types';

export function GradingDraftView({ draft }: { draft: GradingDraft }) {
  return (
    <div className="detail-card">
      <div className="head">
        <strong>初批草稿</strong>
        <Tag size="small" color="gray">{draft.rubric_version}</Tag>
        {draft.flagged && <Tag size="small" color="red">flagged</Tag>}
      </div>
      <div style={{ marginBottom: 8, fontSize: 13 }}>
        总分 <strong style={{ color: 'var(--clr-primary)' }}>{draft.overall_score}</strong> / 100
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--clr-text-3)' }}>
            <th style={{ padding: '4px 8px', borderBottom: '1px solid var(--clr-border)' }}>条目</th>
            <th style={{ padding: '4px 8px', borderBottom: '1px solid var(--clr-border)' }}>得分</th>
            <th style={{ padding: '4px 8px', borderBottom: '1px solid var(--clr-border)' }}>说明</th>
          </tr>
        </thead>
        <tbody>
          {draft.items.map((it) => (
            <tr key={it.rubric_item_id}>
              <td className="mono" style={{ padding: '6px 8px', borderBottom: '1px solid var(--clr-border-light)' }}>{it.rubric_item_id}</td>
              <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--clr-border-light)' }}>{it.score}/{it.max_score}</td>
              <td className="small" style={{ padding: '6px 8px', borderBottom: '1px solid var(--clr-border-light)', color: 'var(--clr-text-2)' }}>{it.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {draft.flagged_reasons.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {draft.flagged_reasons.map((r) => (
            <Tag key={r} size="small" color="red" style={{ marginRight: 4 }}>{r}</Tag>
          ))}
        </div>
      )}
    </div>
  );
}
