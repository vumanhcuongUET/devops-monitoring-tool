import { api } from './client';
import type { SloDashboard, SloApiDetail } from '../types';

export async function fetchSloDashboard(windowDays?: number): Promise<SloDashboard> {
  const params = windowDays ? { window_days: windowDays } : {};
  const { data } = await api.get<SloDashboard>('/api/v1/slo/dashboard', { params });
  return data;
}

export async function fetchSlowApis(serviceName: string): Promise<SloApiDetail[]> {
  const { data } = await api.get<SloApiDetail[]>(`/api/v1/slo/service/${encodeURIComponent(serviceName)}/slow-apis`);
  return data;
}
