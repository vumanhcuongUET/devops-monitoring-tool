import { api } from './client';
import type { SloConfig, SloDashboard, SloResult, SloApiDetail } from '../types';

export async function fetchSloDashboard(windowDays?: number): Promise<SloDashboard> {
  const params = windowDays ? { window_days: windowDays } : {};
  const { data } = await api.get<SloDashboard>('/api/v1/slo/dashboard', { params });
  return data;
}

export async function fetchServiceSlo(serviceName: string): Promise<SloResult[]> {
  const { data } = await api.get<SloResult[]>(`/api/v1/slo/service/${encodeURIComponent(serviceName)}`);
  return data;
}

export async function fetchSlowApis(serviceName: string): Promise<SloApiDetail[]> {
  const { data } = await api.get<SloApiDetail[]>(`/api/v1/slo/service/${encodeURIComponent(serviceName)}/slow-apis`);
  return data;
}

export async function fetchSloConfigs(): Promise<SloConfig[]> {
  const { data } = await api.get<SloConfig[]>('/api/v1/slo/configs');
  return data;
}

export async function createSloConfig(config: Omit<SloConfig, 'id'>): Promise<SloConfig> {
  const { data } = await api.post<SloConfig>('/api/v1/slo/configs', config);
  return data;
}

export async function updateSloConfig(id: string, config: Partial<SloConfig>): Promise<SloConfig> {
  const { data } = await api.put<SloConfig>(`/api/v1/slo/configs/${id}`, config);
  return data;
}

export async function deleteSloConfig(id: string): Promise<void> {
  await api.delete(`/api/v1/slo/configs/${id}`);
}

export async function fetchSloReport(): Promise<Record<string, unknown>> {
  const { data } = await api.get('/api/v1/slo/report');
  return data;
}
