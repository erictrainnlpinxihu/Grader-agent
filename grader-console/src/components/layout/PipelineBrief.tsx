import { Tag } from '@arco-design/web-react';

/**
 * 首页链路简介：一行讲清 Grader 处理一条请求的大体流程。
 * 叙事主线：模型负责提议，规则负责否决，人类教师只在不可逆动作上被叫醒。
 */
const STEPS = ['认身份', '定路线', '查证取料', '核对材料', '给出草稿'];

export function PipelineBrief() {
  return (
    <div className="detail-card" style={{ margin: '12px 16px 0', flex: 'none' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <strong>Grader 是怎么处理一条请求的</strong>
        <Tag size="small" color="arcoblue">模型只提议</Tag>
        <Tag size="small" color="orange">规则可否决</Tag>
        <Tag size="small" color="green">教师拍板</Tag>
      </div>
      <div
        className="small muted"
        style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}
      >
        {STEPS.map((label, i) => (
          <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            {i > 0 && <span className="sm-arrow">→</span>}
            <span>{label}</span>
          </span>
        ))}
        <span>—— 终录成绩 / 学术不端定性 / 公开评语，永远等主讲教师本人批准。</span>
      </div>
    </div>
  );
}
