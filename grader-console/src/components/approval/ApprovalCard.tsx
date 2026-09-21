import { useState } from 'react';
import { Button, Input, Message, Tag } from '@arco-design/web-react';
import { submitApproval } from '../../api/chat';
import type { ApprovalDecision, ApprovalResponse, PendingApproval } from '../../api/types';
import { CheckpointPanel } from './CheckpointPanel';
import { StateMachineMap } from './StateMachineMap';
import { ResumeResult } from './ResumeResult';

const ACTION_LABEL: Record<string, string> = {
  record_final_grade: '录入最终成绩',
  judge_academic_misconduct: '判定学术不端',
  recommend_deferred_exam: '推荐缓考',
  publish_feedback: '公开发布评语',
};

interface Props {
  sessionId: string;
  pending: PendingApproval;
  resolvedResult?: ApprovalResponse | null;
  onResumed?: (resp: ApprovalResponse) => void;
}

export function ApprovalCard({ sessionId, pending, resolvedResult, onResumed }: Props) {
  const [instructorId, setInstructorId] = useState('ins-001');
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState<ApprovalDecision | null>(null);
  const [localResult, setLocalResult] = useState<ApprovalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const result = localResult ?? resolvedResult ?? null;

  async function decide(decision: ApprovalDecision) {
    if ((decision === 'reject' || decision === 'needs_more_info') && !reason.trim()) {
      Message.warning('请填写理由后再提交');
      return;
    }
    setLoading(decision);
    setError(null);
    try {
      const resp = await submitApproval({
        session_id: sessionId,
        submission_id: pending.submission_id,
        instructor_id: instructorId,
        decision,
        reason: reason.trim() || undefined,
        resume_token: pending.resume_token,
      });
      setLocalResult(resp);
      onResumed?.(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : '审批请求失败');
    } finally {
      setLoading(null);
    }
  }

  if (result) {
    return (
      <div className="detail-card">
        <ResumeResult result={result} />
      </div>
    );
  }

  return (
    <div className="detail-card" style={{ borderColor: 'var(--clr-warning)' }}>
      <div className="head">
        <Tag color="orange">待人工审批</Tag>
        <strong>{ACTION_LABEL[pending.action] ?? pending.action}</strong>
        <span className="mono muted small">{pending.submission_id}</span>
      </div>

      <div style={{ marginBottom: 12 }}>
        <StateMachineMap state={pending.state} />
      </div>

      <div style={{ marginBottom: 12 }}>
        <CheckpointPanel pending={pending} />
      </div>

      <div style={{ marginBottom: 8 }}>
        <span className="small muted" style={{ marginRight: 8 }}>主讲教师 ID</span>
        <Input
          style={{ width: 200 }}
          value={instructorId}
          onChange={setInstructorId}
        />
      </div>

      <div style={{ marginBottom: 12 }}>
        <Input.TextArea
          placeholder="驳回 / 补充材料时请填写理由（必填）"
          value={reason}
          onChange={setReason}
          rows={2}
        />
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <Button
          type="primary"
          style={{ background: 'var(--clr-success)', borderColor: 'var(--clr-success)' }}
          loading={loading === 'approve'}
          onClick={() => decide('approve')}
        >
          批准
        </Button>
        <Button
          status="danger"
          loading={loading === 'reject'}
          onClick={() => decide('reject')}
        >
          驳回
        </Button>
        <Button
          loading={loading === 'needs_more_info'}
          onClick={() => decide('needs_more_info')}
        >
          补充材料
        </Button>
      </div>

      {error && (
        <div style={{ marginTop: 8, color: 'var(--clr-danger)', fontSize: 13 }}>{error}</div>
      )}
    </div>
  );
}
