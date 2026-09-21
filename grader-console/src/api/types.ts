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

export interface CostSummary {
  tool_calls?: number;
  llm_calls?: number;
  tokens?: number;
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
  session_state: {
    routing?: {
      intent: string;
      route_kind: RouteKind;
      guard_override: boolean;
      guard_reason?: string;
      confidence: number;
    };
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
