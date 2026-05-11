import { api } from './client';
import type { NodeMetrics } from '../types';

export async function fetchInfrastructureMetrics(params?: { start?: string; end?: string }): Promise<NodeMetrics[]> {
  const { data } = await api.get<NodeMetrics[]>('/api/v1/infrastructure/metrics', { params });
  return data;
}
