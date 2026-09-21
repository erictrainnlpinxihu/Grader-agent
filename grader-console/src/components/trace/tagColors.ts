/**
 * 标签统一语义配色：决策路径面板（DecisionPath）与对话气泡（MessageBubble）
 * 对同名概念使用同一颜色，避免"有的蓝有的灰但没有含义"的困惑。
 *
 * 颜色语义（图例见 DecisionPath 卡片底部）：
 * - 红   = 安全 / 权限拦截（security_blocked、rule_veto、batch_denied…）
 * - 紫   = 转人工工作流（workflow_human、needs_human_approval）
 * - 金   = 等待教师审批（draft_graded、require_approval）
 * - 青   = 知识检索命中（rag_hit、cache_hit、domain:*）
 * - 蓝   = 只读工具 / 批量正常执行（tool_readonly、task_planner、batch_grading）
 * - 橙   = 降级 / 兜底 / 追问澄清（degraded、tool_empty_or_error、low_confidence…）
 * - 灰   = 中性状态（general_chat、deterministic、assignment_status_query…）
 */

/** route_kind → 颜色（与 CLAUDE.md §6.1 七种路线对应） */
export const ROUTE_COLOR: Record<string, string> = {
  tool_readonly: 'blue',
  rag: 'cyan',
  workflow_human: 'purple',
  deterministic: 'gray',
  deterministic_fallback: 'orange',
  deterministic_block: 'red',
  task_planner: 'arcoblue',
};

const SIGNAL_COLOR_RULES: { test: RegExp; color: string }[] = [
  {
    test: /^(security_blocked|deterministic_block|permission_denied|rule_veto|batch_denied|guard_override|tainted)/,
    color: 'red',
  },
  { test: /^(workflow_human|needs_human_approval)$/, color: 'purple' },
  { test: /^(draft_graded|require_approval|awaiting_human_approval)$/, color: 'gold' },
  { test: /^(rag_hit|cache_hit|domain:)/, color: 'cyan' },
  { test: /^(tool_readonly|task_planner|batch_grading)$/, color: 'blue' },
  {
    test: /^(degraded|tool_empty_or_error|low_confidence|ask_clarification|deterministic_fallback)$/,
    color: 'orange',
  },
];

/** signal → 语义颜色；未知 signal 落灰色（中性） */
export function signalColor(signal: string): string {
  for (const r of SIGNAL_COLOR_RULES) {
    if (r.test.test(signal)) return r.color;
  }
  return 'gray';
}

/** signal → 悬停解释（业务语言，未收录的 signal 用通用文案兜底） */
const SIGNAL_HINT: Record<string, string> = {
  tool_readonly: '本次只调用了只读查询工具，没有触碰任何写动作',
  draft_graded: '已产出初批草稿（rubric 逐条分数 + 评语），不是最终成绩',
  require_approval: '等待主讲教师审批；审批通过前不会录入成绩',
  workflow_human: '高风险事项，已转人工工作流（立案 + 暂停等审批）',
  needs_human_approval: '需要主讲教师本人处理，系统不自动执行',
  rag_hit: '命中知识库检索，引用见下方 RAG 面板',
  cache_hit: '命中缓存，跳过最终模型生成（成本治理，不跳过审批）',
  security_blocked: '被安全策略拦截，不调用最终模型',
  deterministic_block: '确定性拦截路线：规则直接否决，模型无发言权',
  permission_denied: '三级权限矩阵拒绝了该动作',
  rule_veto: '规则守卫一票否决（横切在 plan 与 act 之间）',
  guard_override: '规则守卫强制改道（如冒充身份的越权请求）',
  batch_denied: '批量初批被权限规则拦截：仅助教 / 主讲教师可发起',
  batch_grading: '批量初批（分片执行，每份草稿仍需教师审批）',
  task_planner: '批量分片规划已执行（进度可查、断点可恢复）',
  deterministic: '确定性固定话术直答，不让模型自由发挥',
  deterministic_fallback: '低置信兜底：拿不准就追问，不硬猜意图',
  general_chat: '寒暄 / 闲聊',
  grading_request_forwarded: '学生发起的批改请求已转交教学人员（发起权 ≠ 审批权）',
  low_confidence: '意图置信度低于阈值',
  ask_clarification: '正在向用户追问澄清',
  degraded: '外部系统不可用，已切换离线降级模式；不编造分数',
  tool_empty_or_error: '工具返回为空或报错，走降级话术',
  deferred_exam: '缓考 / 补考咨询',
  assignment_status_query: '查询作业状态（只读）',
};

export function signalHint(signal: string): string {
  if (SIGNAL_HINT[signal]) return SIGNAL_HINT[signal];
  if (signal.startsWith('domain:')) return `命中知识域：${signal.slice('domain:'.length)}`;
  return '运行信号（公开 trace 语义，悬停无更多说明）';
}
