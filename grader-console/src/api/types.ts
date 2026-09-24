// 与后端 api/schemas.py、harness/contracts.py 对齐的类型定义

export type Role = 'student' | 'ta' | 'instructor';

export type RouteKind =
  | 'tool_readonly'
  | 'rag'
  | 'workflow_human'
  | 'deterministic'
  | 'deterministic_fallback'
  | 'deterministic_block'
  | 'task_planner';

export type ApprovalDecision = 'approve' | 'reject' | 'needs_more_info';

export type SubmissionState =
  | 'received'
  | 'draft_graded'
  | 'flagged'
  | 'approved'
  | 'recorded'
  | 'rejected'
  | 'paused';

export interface ChatRequest {
  session_id: string;
  user_id: string;
  role: Role;
  course_id: string;
  assignment_id?: string;
  submission_id?: string;
  current_page?: string;
  text: string;
  claimed_role?: string;
}

export interface Citation {
  source: string;
  title?: string;
  score: number;
  retrieval_stage: 'pre_retrieval' | 'tool_retrieval';
}

export interface ToolCallObservation {
  tool_name: string;
  args: Record<string, unknown>;
  output_summary?: string;
  status: 'success' | 'error';
  error?: string;
  safety?: {
    tainted?: boolean;
    matched_pattern?: string;
    sha256?: string;
  };
}

export interface GradingDraftItem {
  rubric_item_id: string;
  score: number;
  max_score: number;
  reason: string;
  cited_chunk_hash?: string;
}

export interface GradingDraft {
  submission_id: string;
  rubric_version: string;
  items: GradingDraftItem[];
  overall_score: number;
  draft_feedback: string;
  flagged: boolean;
  flagged_reasons: string[];
}

export interface PendingApproval {
  resume_token: string;
  submission_id: string;
  action: string;
  state: SubmissionState;
  frozen_fields: {
    submission_body_hash?: string;
    rubric_version?: string;
    similarity_score?: number;
    submission_timestamp?: string;
  };
}

export interface TraceEvent {
  event: string;
  timestamp: string;
  session_id: string;
  payload: Record<string, unknown>;
  schema_version: string;
}

/** 守卫链单条记录：plan → act 之间的确定性闸（后端 harness/cost.py grader_cost_v1） */
export interface GuardCheck {
  check: 'protected_intent_net' | 'rule_guard' | 'veto_intent' | 'rule_veto';
  verdict: 'pass' | 'override' | 'escalate' | 'veto' | 'block';
  reason: string;
}

/** plan 阶段结构化改写 + 最终计划（后端 agent/loop.py session_state.plan） */
export interface PlanInfo {
  rewritten_query: string;
  sub_questions: string[];
  entities?: {
    submission_id?: string | null;
    course_id?: string | null;
    assignment_id?: string | null;
  };
  confidence: number;
  source?: string;
  candidate_applied?: boolean;
  required_tools?: string[];
  knowledge_domains?: string[];
  risk_level?: string;
  fallback_policy?: string | null;
}

/** 请求级时延（后端 agent/loop.py grader_latency_v1） */
export interface LatencyInfo {
  total_ms: number;
  llm_ms: number;
  llm_calls?: number;
  phases?: Record<string, number>;
}

/** 与后端 harness/cost.py grader_cost_v1 字段对齐（离线 / 缺 key 时模型开销为 0） */
export interface CostSummary {
  tool_call_count?: number;
  llm_call_count?: number;
  tokens_used?: number;
  tokens_budget?: number;
  budget_ratio?: number;
  llm_latency_ms?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_llm_tokens?: number;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  signals: string[];
  intent: string;
  route_kind: RouteKind;
  grading_draft?: GradingDraft | null;
  pending_approval?: PendingApproval | null;
  trace_events: TraceEvent[];
  citations: Citation[];
  tool_calls?: ToolCallObservation[];
  next_action: string;
  needs_human_approval: boolean;
  latency?: LatencyInfo;
  session_state: {
    routing?: {
      intent: string;
      route_kind: RouteKind;
      guard_override: boolean;
      guard_reason?: string;
      guard_chain?: GuardCheck[];
      confidence: number;
      source?: string;
      candidate_applied?: boolean;
    };
    plan?: PlanInfo;
    rag?: { cache_hit: boolean };
    workflow?: {
      state: SubmissionState;
      pending_action?: string;
      resume_token?: string;
    } | null;
    batch?: Record<string, unknown>;
    cost_summary?: CostSummary;
  };
  cost_summary: CostSummary;
}

export interface ApprovalRequest {
  session_id: string;
  submission_id?: string;
  instructor_id: string;
  decision: ApprovalDecision;
  reason?: string;
  resume_token?: string;
}

export interface ApprovalResponse {
  session_id: string;
  answer: string;
  status: 'recorded' | 'rejected' | 'paused' | 'blocked' | 'idempotent_replay';
  reason?: string;
  idempotent_replay: boolean;
  recorded_actions?: string[];
  workflow?: { state: SubmissionState };
  business_recheck?: { passed: boolean; drift_fields: string[] };
}
