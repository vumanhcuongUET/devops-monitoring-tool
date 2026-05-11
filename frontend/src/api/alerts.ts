import { api } from './client';
import type { AlertRule, AlertEvent } from '../types';

export async function fetchAlertRules(): Promise<AlertRule[]> {
  const { data } = await api.get<AlertRule[]>('/api/v1/alerts/rules');
  return data;
}

export async function createAlertRule(rule: Omit<AlertRule, 'id'>): Promise<AlertRule> {
  const { data } = await api.post<AlertRule>('/api/v1/alerts/rules', rule);
  return data;
}

export async function updateAlertRule(id: string, rule: Partial<AlertRule>): Promise<AlertRule> {
  const { data } = await api.put<AlertRule>(`/api/v1/alerts/rules/${id}`, rule);
  return data;
}

export async function deleteAlertRule(id: string): Promise<void> {
  await api.delete(`/api/v1/alerts/rules/${id}`);
}

export async function fetchAlertHistory(): Promise<AlertEvent[]> {
  const { data } = await api.get<AlertEvent[]>('/api/v1/alerts/history');
  return data;
}
