import { useState } from 'react';
import { usePolling } from '../hooks/usePolling';
import { fetchPods, fetchDeployments, fetchK8sEvents } from '../api/kubernetes';
import { DataTable, type Column } from '../components/common/DataTable';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import type { PodStatus, DeploymentStatus, K8sEvent } from '../types';

export function KubernetesPage() {
  const [tab, setTab] = useState<'pods' | 'deployments' | 'events'>('pods');

  const { data: pods, isLoading: podsLoading } = usePolling<PodStatus[]>(['k8s-pods'], fetchPods);
  const { data: deployments, isLoading: depLoading } = usePolling<DeploymentStatus[]>(['k8s-deployments'], fetchDeployments);
  const { data: events, isLoading: evtLoading } = usePolling<K8sEvent[]>(['k8s-events'], fetchK8sEvents);

  const podColumns: Column<PodStatus>[] = [
    { key: 'name', header: 'Name' },
    { key: 'namespace', header: 'Namespace' },
    {
      key: 'status',
      header: 'Status',
      render: (row) => {
        const color =
          row.status === 'Running' ? 'text-[var(--color-healthy)]' :
          row.status === 'Pending' ? 'text-[var(--color-degraded)]' :
          'text-[var(--color-down)]';
        return <span className={`font-medium ${color}`}>{row.status}</span>;
      },
    },
    { key: 'restarts', header: 'Restarts', render: (row) => row.restarts > 0 ? <span className="text-[var(--color-down)]">{row.restarts}</span> : <span>{row.restarts}</span> },
    { key: 'age', header: 'Age' },
    { key: 'node', header: 'Node' },
  ];

  const depColumns: Column<DeploymentStatus>[] = [
    { key: 'name', header: 'Name' },
    { key: 'namespace', header: 'Namespace' },
    { key: 'replicas', header: 'Replicas', render: (row) => `${row.available}/${row.replicas}` },
    { key: 'updated', header: 'Updated' },
    { key: 'image', header: 'Image', render: (row) => <span className="text-xs">{row.image}</span> },
  ];

  const evtColumns: Column<K8sEvent>[] = [
    { key: 'timestamp', header: 'Time' },
    {
      key: 'type',
      header: 'Type',
      render: (row) => (
        <span className={row.type === 'Warning' ? 'text-[var(--color-down)]' : ''}>{row.type}</span>
      ),
    },
    { key: 'reason', header: 'Reason' },
    { key: 'object', header: 'Object' },
    { key: 'message', header: 'Message', render: (row) => <span className="line-clamp-2">{row.message}</span> },
  ];

  const tabs = [
    { key: 'pods' as const, label: 'Pods' },
    { key: 'deployments' as const, label: 'Deployments' },
    { key: 'events' as const, label: 'Events' },
  ];

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Kubernetes</h2>
      <div className="flex gap-1 rounded-lg bg-[var(--color-bg-secondary)] p-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded px-4 py-1.5 text-sm ${tab === t.key ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)]'}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'pods' && (podsLoading ? <LoadingSkeleton /> : <DataTable columns={podColumns} data={pods || []} />)}
      {tab === 'deployments' && (depLoading ? <LoadingSkeleton /> : <DataTable columns={depColumns} data={deployments || []} />)}
      {tab === 'events' && (evtLoading ? <LoadingSkeleton /> : <DataTable columns={evtColumns} data={events || []} />)}
    </div>
  );
}
