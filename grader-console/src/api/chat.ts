import { api } from './client';
import type { ApprovalRequest, ApprovalResponse, ChatRequest, ChatResponse } from './types';

export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>('/chat', req);
  return data;
}

export async function submitApproval(req: ApprovalRequest): Promise<ApprovalResponse> {
  const { data } = await api.post<ApprovalResponse>(
    `/sessions/${req.session_id}/approval`,
    req,
  );
  return data;
}
