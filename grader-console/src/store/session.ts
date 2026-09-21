import { create } from 'zustand';
import type {
  ApprovalResponse,
  ChatRequest,
  ChatResponse,
  PendingApproval,
  Role,
  SubmissionState,
} from '../api/types';

function newSessionId() {
  return `sess-${Date.now().toString(36)}`;
}

function defaultUserId(role: Role): string {
  if (role === 'instructor') return 'ins-001';
  if (role === 'ta') return 'ta-001';
  return 'stu-001';
}

export type Turn =
  | { kind: 'user'; text: string }
  | { kind: 'assistant'; resp: ChatResponse };

export interface ApprovalItem {
  id: string; // resume_token
  sessionId: string;
  submissionId: string;
  action: string;
  state: SubmissionState;
  pending: PendingApproval;
  resp: ChatResponse;
  resolved: ApprovalResponse | null;
}

interface SessionState {
  sessionId: string;
  ctx: Omit<ChatRequest, 'text'>;
  turns: Turn[];
  approvals: ApprovalItem[];
  selectedResp: ChatResponse | null;
  setRole: (role: Role) => void;
  setCtx: (patch: Partial<Omit<ChatRequest, 'text'>>) => void;
  pushUserTurn: (text: string) => void;
  pushAssistantTurn: (resp: ChatResponse) => void;
  resolveApproval: (resumeToken: string, approvalResp: ApprovalResponse) => void;
  setSelected: (resp: ChatResponse | null) => void;
  reset: () => void;
}

const baseCtx: Omit<ChatRequest, 'text'> = {
  session_id: '',
  user_id: 'stu-001',
  role: 'student',
  course_id: 'CS101-2026spring',
  assignment_id: 'A3',
  submission_id: 'S1001',
  current_page: 'home',
};

export const useSession = create<SessionState>((set) => ({
  sessionId: newSessionId(),
  ctx: { ...baseCtx, session_id: '' },
  turns: [],
  approvals: [],
  selectedResp: null,

  setRole: (role) =>
    set((s) => ({
      ctx: { ...s.ctx, role, user_id: defaultUserId(role) },
    })),

  setCtx: (patch) => set((s) => ({ ctx: { ...s.ctx, ...patch } })),

  pushUserTurn: (text) => set((s) => ({ turns: [...s.turns, { kind: 'user', text }] })),

  pushAssistantTurn: (resp) =>
    set((s) => {
      const next: Partial<SessionState> = {
        turns: [...s.turns, { kind: 'assistant', resp }],
        selectedResp: resp,
      };
      const pending = resp.pending_approval;
      if (pending) {
        const exists = s.approvals.some((a) => a.id === pending.resume_token);
        if (!exists) {
          const item: ApprovalItem = {
            id: pending.resume_token,
            sessionId: resp.session_id,
            submissionId: pending.submission_id,
            action: pending.action,
            state: pending.state,
            pending,
            resp,
            resolved: null,
          };
          next.approvals = [...s.approvals, item];
        }
      }
      return next as SessionState;
    }),

  resolveApproval: (resumeToken, approvalResp) =>
    set((s) => ({
      approvals: s.approvals.map((a) =>
        a.id === resumeToken ? { ...a, resolved: approvalResp } : a,
      ),
    })),

  setSelected: (resp) => set({ selectedResp: resp }),

  reset: () =>
    set({
      sessionId: newSessionId(),
      ctx: { ...baseCtx, session_id: '' },
      turns: [],
      approvals: [],
      selectedResp: null,
    }),
}));
