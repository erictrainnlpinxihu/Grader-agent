import { api } from './client';
import type { TraceEvent } from './types';

export async function fetchSessionTrace(sessionId: string): Promise<TraceEvent[]> {
  const { data } = await api.get<{ session_id: string; events: TraceEvent[] }>(
    `/sessions/${sessionId}/trace`,
  );
  return data.events ?? [];
}
