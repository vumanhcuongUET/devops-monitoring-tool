import { api } from './client';
import type { PodStatus, DeploymentStatus, K8sEvent } from '../types';

export async function fetchPods(params?: { namespace?: string }): Promise<PodStatus[]> {
  const { data } = await api.get<PodStatus[]>('/api/v1/kubernetes/pods', { params });
  return data;
}

export async function fetchDeployments(params?: { namespace?: string }): Promise<DeploymentStatus[]> {
  const { data } = await api.get<DeploymentStatus[]>('/api/v1/kubernetes/deployments', { params });
  return data;
}

export async function fetchK8sEvents(params?: { namespace?: string }): Promise<K8sEvent[]> {
  const { data } = await api.get<K8sEvent[]>('/api/v1/kubernetes/events', { params });
  return data;
}
