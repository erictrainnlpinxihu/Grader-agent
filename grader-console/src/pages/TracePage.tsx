import { useState } from 'react';
import { Button, Input, Table, Message } from '@arco-design/web-react';
import { fetchSessionTrace } from '../api/trace';
import type { TraceEvent } from '../api/types';

export function TracePage() {
  const [sessionId, setSessionId] = useState('');
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!sessionId.trim()) return;
    setLoading(true);
    try {
      const evs = await fetchSessionTrace(sessionId.trim());
      setEvents(evs);
      if (evs.length === 0) Message.info('该会话暂无 trace 事件');
    } catch (e) {
      Message.error(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 1100 }}>
      <h2 style={{ marginTop: 0 }}>Trace 回放</h2>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <Input
          style={{ width: 360 }}
          placeholder="输入 session_id"
          value={sessionId}
          onChange={setSessionId}
          onPressEnter={load}
        />
        <Button type="primary" loading={loading} onClick={load}>加载</Button>
      </div>
      <Table
        rowKey={(r) => (r as { _k: string })._k}
        data={events.map((e, i) => ({ ...e, _k: `${i}-${e.timestamp}` }))}
        loading={loading}
        pagination={{ pageSize: 50 }}
        columns={[
          { title: '时间', dataIndex: 'timestamp', width: 200, render: (v) => <span className="mono small">{String(v)}</span> },
          { title: '事件', dataIndex: 'event', width: 260, render: (v) => <code>{String(v)}</code> },
          {
            title: 'payload',
            dataIndex: 'payload',
            render: (v) => (
              <pre className="mono small" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(v, null, 2)}
              </pre>
            ),
          },
        ]}
      />
    </div>
  );
}
