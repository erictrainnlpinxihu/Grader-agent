import { api } from './client';
import type { ChatResponse } from './types';

export interface EvalCaseResult {
  case_id: string;
  passed: boolean;
  reason?: string;
  details?: unknown;
  /**
   * 后端附带的公开响应（trace 已脱敏；chat case 为多轮聚合链路，
   * resume case 为 start 轮）。用于在 Eval 页回放决策链路。
   */
  response?: ChatResponse | null;
}

export interface EvalReport {
  total: number;
  passed: number;
  failed: number;
  cases: EvalCaseResult[];
  summary?: { pass_rate: number };
  error?: string;
}

export async function runEval(caseId?: string): Promise<EvalReport> {
  const { data } = await api.post<EvalReport>('/eval/run', caseId ? { case_id: caseId } : {});
  return data;
}
