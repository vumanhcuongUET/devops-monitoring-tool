import { api } from './client';
import type { Transaction, ApmError, ApmSummary } from '../types';

export async function fetchTransactions(params?: { service?: string; start?: string; end?: string }): Promise<Transaction[]> {
  const { data } = await api.get<Transaction[]>('/api/v1/apm/transactions', { params });
  return data;
}

export async function fetchApmErrors(params?: { service?: string; start?: string; end?: string }): Promise<ApmError[]> {
  const { data } = await api.get<ApmError[]>('/api/v1/apm/errors', { params });
  return data;
}

export async function fetchApmSummary(params?: { start?: string; end?: string }): Promise<ApmSummary> {
  const { data } = await api.get<ApmSummary>('/api/v1/apm/summary', { params });
  return data;
}
