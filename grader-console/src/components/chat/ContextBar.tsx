import { Select, Input, Grid } from '@arco-design/web-react';
import { useSession } from '../../store/session';
import type { Role } from '../../api/types';

const { Row, Col } = Grid;

export function ContextBar() {
  const { ctx, setRole, setCtx, sessionId } = useSession();

  return (
    <div className="card" style={{ padding: 12, marginBottom: 12 }}>
      <Row gutter={[12, 12]}>
        <Col span={8}>
          <div className="small muted" style={{ marginBottom: 4 }}>角色</div>
          <Select
            style={{ width: '100%' }}
            value={ctx.role}
            onChange={(v) => setRole(v as Role)}
            options={[
              { label: '学生 student', value: 'student' },
              { label: '助教 ta', value: 'ta' },
              { label: '主讲 instructor', value: 'instructor' },
            ]}
          />
        </Col>
        <Col span={8}>
          <div className="small muted" style={{ marginBottom: 4 }}>用户 ID</div>
          <Input
            value={ctx.user_id}
            onChange={(v) => setCtx({ user_id: v })}
          />
        </Col>
        <Col span={8}>
          <div className="small muted" style={{ marginBottom: 4 }}>会话 ID</div>
          <Input readOnly value={sessionId} />
        </Col>
        <Col span={8}>
          <div className="small muted" style={{ marginBottom: 4 }}>课程</div>
          <Input
            value={ctx.course_id}
            onChange={(v) => setCtx({ course_id: v })}
          />
        </Col>
        <Col span={8}>
          <div className="small muted" style={{ marginBottom: 4 }}>作业</div>
          <Input
            value={ctx.assignment_id ?? ''}
            onChange={(v) => setCtx({ assignment_id: v })}
          />
        </Col>
        <Col span={8}>
          <div className="small muted" style={{ marginBottom: 4 }}>提交 submission</div>
          <Input
            value={ctx.submission_id ?? ''}
            onChange={(v) => setCtx({ submission_id: v })}
          />
        </Col>
      </Row>
    </div>
  );
}
