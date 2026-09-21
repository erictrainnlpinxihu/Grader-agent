import { useState } from 'react';
import { Switch, Tag } from '@arco-design/web-react';
import { EXAMPLE_GROUPS, type ExampleQuestion } from '../../examples/questions';
import { useSession } from '../../store/session';

interface Props {
  onPick: (q: ExampleQuestion) => void | Promise<void>;
}

const ROLE_LABEL: Record<string, string> = {
  student: '学生',
  ta: '助教',
  instructor: '讲师',
};

export function ExampleQuestions({ onPick }: Props) {
  const role = useSession((s) => s.ctx.role);
  const [showAll, setShowAll] = useState(false);

  return (
    <div style={{ marginBottom: 12 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 8,
        }}
      >
        <span className="small muted">
          示例问题（当前角色：{ROLE_LABEL[role] ?? role}
          {!showAll && '，仅展示该角色视角'}）
        </span>
        <span className="small muted">全部角色</span>
        <Switch size="small" checked={showAll} onChange={setShowAll} />
      </div>

      {EXAMPLE_GROUPS.map((g) => {
        const items = g.items.filter((q) => showAll || !q.role || q.role === role);
        if (items.length === 0) return null;
        return (
          <div key={g.group} style={{ marginBottom: 10 }}>
            <div className="small muted" style={{ marginBottom: 6 }}>{g.group}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {items.map((q) => (
                <button
                  key={`${q.role ?? 'any'}-${q.text}`}
                  onClick={() => onPick(q)}
                  style={{
                    border: q.texts
                      ? '1px solid var(--clr-primary)'
                      : '1px solid var(--clr-border)',
                    background: q.texts ? 'var(--clr-primary-light)' : '#fff',
                    borderRadius: 999,
                    padding: '5px 12px',
                    fontSize: 13,
                    cursor: 'pointer',
                    color: 'var(--clr-text-1)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                  title={q.note}
                >
                  {showAll && q.role && q.role !== role && (
                    <Tag size="small" color="gray" style={{ marginRight: 0 }}>
                      {ROLE_LABEL[q.role]}
                    </Tag>
                  )}
                  {q.text}
                </button>
              ))}
            </div>
            {items.some((q) => q.hint) && (
              <div className="small muted" style={{ marginTop: 6, lineHeight: 1.6 }}>
                {items.find((q) => q.hint)?.hint}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
