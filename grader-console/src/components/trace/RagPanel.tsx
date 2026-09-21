import { Tag } from '@arco-design/web-react';
import type { Citation } from '../../api/types';

interface Props {
  citations: Citation[];
  cacheHit?: boolean;
}

/**
 * hybrid 召回的 score 是 RRF 双路排名融合分：向量路与关键词路各贡献
 * 1/(K+rank+1)（后端 RRF_K=60），理论上限 2/61 ≈ 0.0328。
 * 因此 0.033 不是"低分未命中"，而是两路都排第 1 的最强命中。
 * 直挂政策（pre_retrieval）不参与排名，固定 1.0。
 */
const RRF_MAX = 2 / 61;

function hitQuality(rel: number): { label: string; color: string } {
  if (rel >= 0.95) return { label: '双路第 1 · 最强命中', color: 'green' };
  if (rel >= 0.6) return { label: '双路靠前 · 强命中', color: 'blue' };
  if (rel >= 0.3) return { label: '单路命中', color: 'orange' };
  return { label: '弱命中（排名靠后）', color: 'gray' };
}

export function RagPanel({ citations, cacheHit }: Props) {
  const hasHybrid = citations.some((c) => c.retrieval_stage !== 'pre_retrieval');

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
        <>
          {citations.map((c, i) => {
            const pinned = c.retrieval_stage === 'pre_retrieval';
            const rel = pinned ? 1 : Math.min(1, c.score / RRF_MAX);
            const q = hitQuality(rel);
            return (
              <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--clr-border-light)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                  <span className="mono muted small">#{i + 1}</span>
                  <strong style={{ fontSize: 13 }}>{c.title ?? c.source}</strong>
                  <Tag size="small" color="gray">{c.source}</Tag>
                  <Tag size="small" color={pinned ? 'purple' : 'blue'}>
                    {pinned ? '直挂政策' : 'hybrid 召回'}
                  </Tag>
                  <Tag size="small" color={pinned ? 'purple' : q.color}>
                    {pinned ? '确定性直挂 · 不参与相似度排序' : q.label}
                  </Tag>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="small muted" title="RRF 双路排名融合分，理论上限约 0.033，越接近上限命中越强">
                    {pinned ? 'score 1.000（固定）' : `融合分 ${c.score.toFixed(4)} / 上限 ${RRF_MAX.toFixed(4)}`}
                  </span>
                  <div style={{ flex: 1, height: 4, background: 'var(--clr-border-light)', borderRadius: 2 }}>
                    <div
                      style={{
                        width: `${Math.round(rel * 100)}%`,
                        height: 4,
                        background: pinned ? 'var(--clr-purple)' : 'var(--clr-primary)',
                        borderRadius: 2,
                      }}
                    />
                  </div>
                </div>
              </div>
            );
          })}
          {hasHybrid && (
            <div className="small muted" style={{ marginTop: 8, lineHeight: 1.6 }}>
              说明：hybrid 召回的分数是<strong>排名融合分</strong>（向量语义 + 关键词两路排名融合，
              上限 ≈0.033），不是余弦相似度——分数越接近上限，说明该内容在两路检索里排名越靠前。
            </div>
          )}
        </>
      )}
    </div>
  );
}
