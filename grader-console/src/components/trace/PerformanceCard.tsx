import { Tag } from '@arco-design/web-react';
import type { ChatResponse } from '../../api/types';
import { fmtMs } from './PlanGuardPanel';

const PHASE_ORDER = ['perceive_ms', 'plan_ms', 'act_ms', 'observe_ms', 'respond_ms'];
const PHASE_LABEL: Record<string, string> = {
  perceive_ms: 'perceive 认身份',
  plan_ms: 'plan 定路线',
  act_ms: 'act 查证取料',
  observe_ms: 'observe 核对材料',
  respond_ms: 'respond 给出草稿',
};

/**
 * 性能与成本：请求总耗时 / 真实模型耗时 / 模型调用数 / token 消耗，
 * 以及五阶段分段耗时（按相对最长阶段等比展示）。
 * 数据来自后端 grader_latency_v1 与 grader_cost_v1；
 * 离线模式（GRADER_DISABLE_LLM=1 / 缺 key）下模型开销恒为 0。
 */
export function PerformanceCard({ resp }: { resp: ChatResponse }) {
  const latency = resp.latency;
  const cost = resp.cost_summary ?? resp.session_state.cost_summary;
  const phases = (latency?.phases ?? {}) as Record<string, number | undefined>;
  const maxPhase = Math.max(0.001, ...PHASE_ORDER.map((k) => phases[k] ?? 0));
  const llmCalls = latency?.llm_calls ?? cost?.llm_call_count ?? 0;

  return (
    <div className="detail-card">
      <div className="head">
        <strong>性能与成本 · latency / tokens</strong>
        {llmCalls === 0 && (
          <Tag
            size="small"
            color="orange"
            title="离线模式或缺少 API key：所有语义调用走确定性规则替身，模型耗时与 token 为 0"
          >
            离线模式 · 0 次模型调用
          </Tag>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        <div className="stat-tile">
          <div className="small muted">总耗时</div>
          <div className="mono" style={{ fontSize: 15, fontWeight: 600 }}>{fmtMs(latency?.total_ms)}</div>
        </div>
        <div className="stat-tile">
          <div className="small muted">模型耗时</div>
          <div className="mono" style={{ fontSize: 15, fontWeight: 600 }}>
            {fmtMs(latency?.llm_ms ?? cost?.llm_latency_ms)}
          </div>
        </div>
        <div className="stat-tile">
          <div className="small muted">模型调用</div>
          <div className="mono" style={{ fontSize: 15, fontWeight: 600 }}>{llmCalls} 次</div>
        </div>
        <div className="stat-tile">
          <div className="small muted">模型 token</div>
          <div className="mono" style={{ fontSize: 15, fontWeight: 600 }}>
            {(cost?.total_llm_tokens ?? 0).toLocaleString()}
          </div>
          <div className="small muted">
            输入 {(cost?.prompt_tokens ?? 0).toLocaleString()} / 输出 {(cost?.completion_tokens ?? 0).toLocaleString()}
          </div>
        </div>
        <div className="stat-tile">
          <div className="small muted">只读工具</div>
          <div className="mono" style={{ fontSize: 15, fontWeight: 600 }}>{cost?.tool_call_count ?? 0} 次</div>
        </div>
      </div>

      {PHASE_ORDER.some((k) => (phases[k] ?? 0) > 0) && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {PHASE_ORDER.map((k) => {
            const ms = phases[k] ?? 0;
            return (
              <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="small muted" style={{ width: 130, flex: 'none' }}>{PHASE_LABEL[k]}</span>
                <div style={{ flex: 1, height: 6, background: 'var(--clr-border-light)', borderRadius: 3 }}>
                  <div
                    style={{
                      width: `${Math.max(1, Math.round((ms / maxPhase) * 100))}%`,
                      height: 6,
                      borderRadius: 3,
                      background: k === 'respond_ms' ? 'var(--clr-primary)' : 'var(--clr-purple)',
                    }}
                  />
                </div>
                <span className="small mono" style={{ width: 70, flex: 'none', textAlign: 'right' }}>{fmtMs(ms)}</span>
              </div>
            );
          })}
          <div className="small muted" style={{ lineHeight: 1.6 }}>
            分段耗时按相对最长阶段等比展示；模型耗时包含在对应阶段内（改写 / 路由 / 初批 / 润色）。
          </div>
        </div>
      )}
    </div>
  );
}
