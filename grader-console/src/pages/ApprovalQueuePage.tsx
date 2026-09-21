import { useNavigate } from 'react-router-dom';
import { Button, Tag, Table, Empty } from '@arco-design/web-react';
import { useSession, type ApprovalItem } from '../store/session';

const ACTION_LABEL: Record<string, string> = {
  record_final_grade: '录入最终成绩',
  judge_academic_misconduct: '判定学术不端',
  recommend_deferred_exam: '推荐缓考',
  publish_feedback: '公开发布评语',
};

const STATE_COLOR: Record<string, string> = {
  draft_graded: 'orange',
  flagged: 'orange',
  approved: 'green',
  recorded: 'green',
  rejected: 'red',
  paused: 'orange',
};

export function ApprovalQueuePage() {
  const navigate = useNavigate();
  const approvals = useSession((s) => s.approvals);
  const setSelected = useSession((s) => s.setSelected);

  function handleReview(item: ApprovalItem) {
    setSelected(item.resp);
    navigate('/');
  }

  const pending = approvals.filter((a) => !a.resolved);

  return (
    <div style={{ padding: 24, maxWidth: 1100 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <h2 style={{ margin: 0 }}>审批队列</h2>
        {pending.length > 0 && <Tag color="orange">{pending.length} 项待处理</Tag>}
      </div>
      <p className="muted small" style={{ marginTop: 8 }}>
        初批 / 高风险工作流产生的待人工审批项会自动进入此队列（由前端会话收集；后端待补 GET /approvals/pending）。
      </p>

      {approvals.length === 0 ? (
        <Empty description="暂无待审批项。去调试台发起一次“帮我批一下 S1001”试试。" />
      ) : (
        <Table
          rowKey={(r) => (r as ApprovalItem).id}
          data={approvals}
          pagination={false}
          columns={[
            {
              title: '待办动作',
              dataIndex: 'action',
              render: (v) => <strong>{ACTION_LABEL[String(v)] ?? String(v)}</strong>,
            },
            {
              title: '提交',
              dataIndex: 'submissionId',
              render: (v) => <code>{String(v)}</code>,
            },
            {
              title: '当前状态',
              dataIndex: 'state',
              render: (v) => <Tag size="small" color={STATE_COLOR[String(v)] ?? 'gray'}>{String(v)}</Tag>,
            },
            {
              title: '结果',
              dataIndex: 'resolved',
              render: (v) =>
                v ? (
                  <Tag size="small" color="green">{String((v as { status: string }).status)}</Tag>
                ) : (
                  <Tag size="small" color="orange">待审批</Tag>
                ),
            },
            {
              title: '操作',
              dataIndex: 'id',
              render: (_v, record) => (
                <Button size="small" type="primary" onClick={() => handleReview(record as ApprovalItem)}>
                  {record.resolved ? '查看决策路径' : '去审批'}
                </Button>
              ),
            },
          ]}
        />
      )}
    </div>
  );
}
