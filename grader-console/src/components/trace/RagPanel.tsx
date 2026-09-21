import { Tag } from '@arco-design/web-react';
import type { Citation } from '../../api/types';

interface Props {
  citations: Citation[];
  cacheHit?: boolean;
}

export function RagPanel({ citations, cacheHit }: Props) {
  return (
    <div className="detail-card">
      <div className="head">
        <strong>RAG 检索结果</strong>
        {cacheHit && <Tag size="small" color="green">缓存命中 · 跳过最终模型</Tag>}
        <Tag size="small">{citations.length} 条引用</Tag>
      </div>
      {citations.length === 0 ? (
        <div className="small muted">本次未产生检索引用。</div>
      ) : (
        citations.map((c, i) => (
          <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--clr-border-light)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span className="mono muted small">#{i + 1}</span>
              <strong style={{ fontSize: 13 }}>{c.title ?? c.source}</strong>
              <Tag size="small" color="gray">{c.source}</Tag>
              <Tag size="small" color={c.retrieval_stage === 'pre_retrieval' ? 'purple' : 'blue'}>
                {c.retrieval_stage === 'pre_retrieval' ? '直挂政策' : 'hybrid 召回'}
              </Tag>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="small muted">score {c.score.toFixed(3)}</span>
              <div style={{ flex: 1, height: 4, background: 'var(--clr-border-light)', borderRadius: 2 }}>
                <div style={{ width: `${Math.min(100, c.score * 100)}%`, height: 4, background: 'var(--clr-primary)', borderRadius: 2 }} />
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
