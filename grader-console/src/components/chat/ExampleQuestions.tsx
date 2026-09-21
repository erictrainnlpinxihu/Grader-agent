import { EXAMPLE_GROUPS, type ExampleQuestion } from '../../examples/questions';

interface Props {
  onPick: (q: ExampleQuestion) => void;
}

export function ExampleQuestions({ onPick }: Props) {
  return (
    <div style={{ marginBottom: 12 }}>
      {EXAMPLE_GROUPS.map((g) => (
        <div key={g.group} style={{ marginBottom: 10 }}>
          <div className="small muted" style={{ marginBottom: 6 }}>{g.group}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {g.items.map((q) => (
              <button
                key={q.text}
                onClick={() => onPick(q)}
                style={{
                  border: '1px solid var(--clr-border)',
                  background: '#fff',
                  borderRadius: 999,
                  padding: '5px 12px',
                  fontSize: 13,
                  cursor: 'pointer',
                  color: 'var(--clr-text-1)',
                }}
                title={q.note}
              >
                {q.text}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
