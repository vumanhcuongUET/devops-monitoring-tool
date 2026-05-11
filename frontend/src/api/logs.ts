import { api } from './client';
import type { LogsResponse, LogQueryParams } from '../types';

export async function fetchLogs(params: LogQueryParams): Promise<LogsResponse> {
  const { data } = await api.get<LogsResponse>('/api/v1/logs', { params });
  return data;
}
