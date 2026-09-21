import { api } from './client';

export async function fetchHealth(): Promise<{ status: string; project: string }> {
  const { data } = await api.get('/health');
  return data;
}

export async function fetchManifest(): Promise<Record<string, unknown>> {
  const { data } = await api.get('/manifest');
  return data;
}
