import { useState } from 'react';
import { Button, Select, Tag, Table, Statistic, Card, Spin, Message } from '@arco-design/web-react';
import { runEval, type EvalReport, type EvalCaseResult } from '../api/eval';
import type { ApprovalResponse, ChatResponse } from '../api/types';
import { DecisionPath } from '../components/trace/DecisionPath';
import { ResumeResult } from '../components/approval/ResumeResult';

// 与后端 eval/cases.yml 中的 case_id 对齐（21 个）
const CASE_OPTIONS = [
  'grader-status-query-readonly',
  'grader-rubric-query-rag-cachehit',
  'grader-syllabus-query-rag',
  'grader-deferred-exam-rag-hitl',
  'grader-general-chat-lowconf-fallback',
  'grader-route-guard-security-override',
  'grader-permission-guard-dual',
  'grader-hitl-approve-recorded',
  'grader-hitl-reject',
  'grader-hitl-needs-more-info',
  'grader-resume-invalid-token',
  'grader-resume-idempotent-replay',
  'grader-resume-missing-checkpoint',
  'grader-resume-freeze-drift',
  'grader-injection-redact',
  'grader-consistency-fairness',
  'grader-degradation-offline',
  'grader-feedback-backfill',
  'grader-high-risk-dual-track',
  'grader-high-risk-student-initiates',
  'grader-batch-grading',
];

/** resume/consistency 等 case 的 details 条目（后端结构） */
interface EvalDetailEntry {
  passed?: boolean;
  reason?: string;
  subscene?: string;
  result?: Record<string, unknown>;
  response?: Record<string, unknown> | null;
}

/** 把后端附带的响应（chat 或 resume）归一化为 DecisionPath 可渲染的 ChatResponse */
function toChatResponse(raw: Record<string, unknown>): ChatResponse {
  const r = raw as Partial<ChatResponse>;
  return {
    session_id: r.session_id ?? '',
    answer: r.answer ?? '',
    signals: r.signals ?? [],
    intent: r.intent ?? 'resume',
    route_kind: r.route_kind ?? 'workflow_human',
    grading_draft: r.grading_draft ?? null,
    pending_approval: r.pending_approval ?? null,
    trace_events: r.trace_events ?? [],
    citations: r.citations ?? [],
    tool_calls: r.tool_calls ?? [],
    next_action: r.next_action ?? 'answer_user',
    needs_human_approval: r.needs_human_approval ?? false,
    session_state: r.session_state ?? {},
    cost_summary: r.cost_summary ?? {},
  } as ChatResponse;
}

function CaseLinkPanel({ res }: { res: EvalCaseResult }) {
  const detailEntries: EvalDetailEntry[] = Array.isArray(res.details)
    ? (res.details as EvalDetailEntry[])
    : [];
  const response = res.response as unknown as Record<string, unknown> | null | undefined;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {response ? (
        <div>
          <div className="small muted" style={{ marginBottom: 8 }}>
            决策链路 · perceive → plan → act → observe → respond（grader_trace_v1 脱敏后公开视图
            {detailEntries.length > 0 ? '，start 轮' : ''}）
          </div>
          <DecisionPath resp={toChatResponse(response)} />
        </div>
      ) : (
        <div className="muted small">
          该 case 无可回放的对话链路（如 feedback 归因类），断言数据见下方原始结果。
        </div>
      )}

      {detailEntries.map((d, i) =>
        d.result ? (
          <div key={i}>
            <div className="small muted" style={{ margin: '8px 0 4px' }}>
              {d.subscene ? `子场景 ${d.subscene} · ` : 'resume 返回 · '}
              {d.passed ? (
                <Tag size="small" color="green">断言通过</Tag>
              ) : (
                <Tag size="small" color="red">断言失败</Tag>
              )}
              {d.reason && d.reason !== 'ok' ? `（${d.reason}）` : ''}
            </div>
            <ResumeResult result={d.result as unknown as ApprovalResponse} />
            {d.response && (
              <div style={{ marginTop: 8 }}>
                <DecisionPath resp={toChatResponse(d.response)} />
              </div>
            )}
          </div>
        ) : null,
      )}

      <details>
        <summary className="small muted" style={{ cursor: 'pointer' }}>
          原始断言结果（JSON）
        </summary>
        <pre className="mono small" style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }}>
          {JSON.stringify(res.details ?? res, null, 2)}
        </pre>
      </details>
    </div>
  );
}

export function EvalPage() {
  const [caseId, setCaseId] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<EvalReport | null>(null);

  async function handleRun() {
    setLoading(true);
    try {
      const r = await runEval(caseId || undefined);
      setReport(r);
      if (r.error) Message.error(r.error);
      else Message.success(`完成：${r.passed}/${r.total} 通过`);
    } catch (e) {
      Message.error(e instanceof Error ? e.message : '运行失败');
    } finally {
      setLoading(false);
    }
  }

  const passRate = report?.summary?.pass_rate;

  return (
    <div style={{ padding: 24, maxWidth: 1100 }}>
      <h2 style={{ marginTop: 0 }}>Eval 回归</h2>
      <p className="muted small">
        调用 POST /eval/run，运行离线 eval case 并查看通过情况；点击行首展开箭头可回放该 case
        的完整决策链路（五阶段时间线、工具调用、RAG 检索与 trace 事件）。
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <Select
          style={{ width: 380 }}
          placeholder="全部 case（不选则跑全集）"
          value={caseId || undefined}
          allowClear
          onChange={(v) => setCaseId(v ?? '')}
        >
          {CASE_OPTIONS.map((c) => (
            <Select.Option key={c} value={c}>{c}</Select.Option>
          ))}
        </Select>
        <Button type="primary" loading={loading} onClick={handleRun}>
          运行
        </Button>
      </div>

      {loading && (
        <div style={{ margin: '40px 0', textAlign: 'center' }}>
          <Spin size={24} /> <span className="muted small">正在运行 eval…（全集回归可能需要数分钟）</span>
        </div>
      )}

      {report && !loading && (
        <>
          <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
            <Card style={{ flex: 1 }}>
              <Statistic title="总数" value={report.total} />
            </Card>
            <Card style={{ flex: 1 }}>
              <Statistic title="通过" value={report.passed} suffix="" />
            </Card>
            <Card style={{ flex: 1 }}>
              <Statistic title="失败" value={report.failed} style={{ color: report.failed ? 'var(--clr-danger)' : undefined }} />
            </Card>
            <Card style={{ flex: 1 }}>
              <Statistic
                title="通过率"
                value={passRate !== undefined ? Math.round(passRate * 100) : 0}
                suffix="%"
              />
            </Card>
          </div>

          <Table
            rowKey={(r) => (r as EvalCaseResult).case_id}
            data={report.cases}
            loading={loading}
            pagination={{ pageSize: 50 }}
            expandedRowRender={(r) => <CaseLinkPanel res={r as EvalCaseResult} />}
            columns={[
              {
                title: 'case_id',
                dataIndex: 'case_id',
                render: (v, r) => (
                  <span>
                    <code>{String(v)}</code>
                    {(r as EvalCaseResult).response && (
                      <Tag size="small" color="arcoblue" style={{ marginLeft: 8 }}>
                        链路可回放
                      </Tag>
                    )}
                  </span>
                ),
              },
              {
                title: '结果',
                dataIndex: 'passed',
                width: 100,
                render: (v) =>
                  v ? (
                    <Tag color="green">PASS</Tag>
                  ) : (
                    <Tag color="red">FAIL</Tag>
                  ),
              },
              {
                title: '原因 / 断言',
                dataIndex: 'reason',
                render: (v) => (
                  <span className="small" style={{ color: v === 'ok' ? 'var(--clr-text-3)' : 'var(--clr-danger)' }}>
                    {String(v ?? '')}
                  </span>
                ),
              },
            ]}
          />
        </>
      )}

      {!report && !loading && (
        <div className="muted small" style={{ padding: 40, textAlign: 'center' }}>
          选择一个 case 或直接运行全集，查看回归结果与决策链路。
        </div>
      )}
    </div>
  );
}
