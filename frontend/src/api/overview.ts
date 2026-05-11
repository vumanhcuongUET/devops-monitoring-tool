import { api } from './client';
import type { OverviewResponse } from '../types';

export async function fetchOverview(): Promise<OverviewResponse> {
  const { data } = await api.get<OverviewResponse>('/api/v1/overview');
  return data;
}
