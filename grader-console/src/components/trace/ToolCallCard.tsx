import { useState } from 'react';
import { Tag, Collapse } from '@arco-design/web-react';
import type { ToolCallObservation } from '../../api/types';

export function ToolCallCard({ call, index }: { call: ToolCallObservation; index: number }) {
  const ok = call.status === 'success';
  const tainted = call.safety?.tainted;
  return (
    <div className="detail-card">
      <div className="head">
        <Tag color="blue">#{index + 1}</Tag>
        <code style={{ fontWeight: 600 }}>{call.tool_name}</code>
        <Tag size="small" color={ok ? 'green' : 'red'}>{ok ? 'success' : 'error'}</Tag>
        {tainted && <Tag size="small" color="red">tainted</Tag>}
      </div>
      {call.output_summary && (
        <div className="small" style={{ marginBottom: 6, color: 'var(--clr-text-2)' }}>
          {call.output_summary}
        </div>
      )}
      {call.error && (
        <div className="small" style={{ color: 'var(--clr-danger)', marginBottom: 6 }}>{call.error}</div>
      )}
      <Collapse
        defaultActiveKey={[]}
        bordered={false}
        style={{ background: 'transparent' }}
      >
        <Collapse.Item key="args" header="入参" name="args">
          <pre className="mono" style={{ margin: 0, background: 'var(--clr-bg-page)', padding: 8, borderRadius: 4, overflow: 'auto' }}>
            {JSON.stringify(call.args, null, 2)}
          </pre>
        </Collapse.Item>
        {call.safety && (
          <Collapse.Item key="safety" header="source_guard" name="safety">
            <pre className="mono" style={{ margin: 0, background: 'var(--clr-bg-page)', padding: 8, borderRadius: 4, overflow: 'auto' }}>
              {JSON.stringify(call.safety, null, 2)}
            </pre>
          </Collapse.Item>
        )}
      </Collapse>
    </div>
  );
}
