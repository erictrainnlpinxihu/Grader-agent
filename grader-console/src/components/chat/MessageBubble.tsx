import { Tag } from '@arco-design/web-react';
import { useSession, type Turn } from '../../store/session';
import type { ApprovalResponse, ChatResponse } from '../../api/types';
import { ApprovalCard } from '../approval/ApprovalCard';

interface Props {
  turn: Turn;
  sessionId: string;
}

export function MessageBubble({ turn, sessionId }: Props) {
  const approvals = useSession((s) => s.approvals);
  const resolveApproval = useSession((s) => s.resolveApproval);

  if (turn.kind === 'user') {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <div
          style={{
            background: 'var(--clr-primary)',
            color: '#fff',
            borderRadius: 10,
            padding: '8px 12px',
            maxWidth: '85%',
            lineHeight: 1.6,
          }}
        >
          {turn.text}
        </div>
      </div>
    );
  }

  const { resp }: { resp: ChatResponse } = turn;
  const pending = resp.pending_approval;
  const resolvedResult: ApprovalResponse | null = pending
    ? approvals.find((a) => a.id === pending.resume_token)?.resolved ?? null
    : null;
  const showApproval = !!pending;

  function handleResumed(approvalResp: ApprovalResponse) {
    if (pending) resolveApproval(pending.resume_token, approvalResp);
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <div
        className="card"
        style={{
          padding: 12,
          background: '#fff',
          maxWidth: '100%',
        }}
      >
        <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7, marginBottom: 8 }}>
          {resp.answer}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          <Tag size="small" color="blue">{resp.route_kind}</Tag>
          {resp.signals.map((s) => (
            <Tag key={s} size="small" color="gray">{s}</Tag>
          ))}
        </div>
      </div>

      {showApproval && pending && (
        <div style={{ marginTop: 8 }}>
          <ApprovalCard
            sessionId={sessionId}
            pending={pending}
            resolvedResult={resolvedResult}
            onResumed={handleResumed}
          />
        </div>
      )}
    </div>
  );
}
