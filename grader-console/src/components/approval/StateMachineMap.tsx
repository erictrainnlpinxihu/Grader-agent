import type { SubmissionState } from '../../api/types';

const MAIN_FLOW: SubmissionState[] = [
  'received',
  'draft_graded',
  'flagged',
  'approved',
  'recorded',
];

const LABEL: Record<string, string> = {
  received: '已接收',
  draft_graded: '初批完成',
  flagged: '待审批',
  approved: '已批准',
  recorded: '已录分',
  rejected: '已驳回',
  paused: '已暂停',
};

export function StateMachineMap({ state }: { state?: SubmissionState | null }) {
  if (!state) return null;
  const terminal = ['rejected', 'recorded'].includes(state);
  const currentIdx = MAIN_FLOW.indexOf(state);

  return (
    <div>
      <div className="sm-flow">
        {MAIN_FLOW.map((s, i) => {
          const cls =
            s === state
              ? 'sm-node active'
              : currentIdx >= 0 && i < currentIdx
                ? 'sm-node reached'
                : 'sm-node';
          return (
            <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <span className={cls}>{LABEL[s]}</span>
              {i < MAIN_FLOW.length - 1 && <span className="sm-arrow">→</span>}
            </span>
          );
        })}
      </div>
      {(state === 'rejected' || state === 'paused') && (
        <div style={{ marginTop: 8 }}>
          <span className="sm-node active" style={{ background: 'var(--clr-warning)', borderColor: 'var(--clr-warning)' }}>
            {LABEL[state]}
          </span>
          {terminal && <span className="small muted" style={{ marginLeft: 8 }}>终态</span>}
        </div>
      )}
    </div>
  );
}
