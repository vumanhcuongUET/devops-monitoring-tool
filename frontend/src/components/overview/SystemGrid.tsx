import { useNavigate } from 'react-router-dom';
import { Box, FileText, Activity, Server } from 'lucide-react';
import type { OverviewResponse } from '../../types';
import { SystemHealthCard } from './SystemHealthCard';

export function SystemGrid({ data }: { data: OverviewResponse }) {
  const navigate = useNavigate();
  const { systems } = data;

  const cards = [
    {
      title: 'Kubernetes',
      status: systems.kubernetes.status,
      icon: <Box size={20} />,
      metrics: [
        { label: 'Pods', value: `${systems.kubernetes.pods_running}/${systems.kubernetes.pods_total}` },
        { label: 'Deployments', value: `${systems.kubernetes.deployments_available}/${systems.kubernetes.deployments_total}` },
        { label: 'Pending', value: String(systems.kubernetes.pods_pending) },
        { label: 'Failed', value: String(systems.kubernetes.pods_failed) },
      ],
      link: '/kubernetes',
    },
    {
      title: 'Elasticsearch',
      status: systems.elasticsearch.status,
      icon: <FileText size={20} />,
      metrics: [
        { label: 'Cluster', value: systems.elasticsearch.cluster_health },
        { label: 'Errors (1h)', value: String(systems.elasticsearch.error_count_1h) },
      ],
      link: '/logs',
    },
    {
      title: 'APM',
      status: systems.apm.status,
      icon: <Activity size={20} />,
      metrics: [
        { label: 'Avg Latency', value: `${systems.apm.avg_latency_ms}ms` },
        { label: 'Error Rate', value: `${systems.apm.error_rate_percent}%` },
        { label: 'TPM', value: String(systems.apm.transactions_per_minute) },
      ],
      link: '/apm',
    },
    {
      title: 'Infrastructure',
      status: systems.infrastructure.status,
      icon: <Server size={20} />,
      metrics: [
        { label: 'Nodes', value: `${systems.infrastructure.nodes_healthy}/${systems.infrastructure.nodes_total}` },
        { label: 'Avg CPU', value: `${systems.infrastructure.avg_cpu_percent}%` },
        { label: 'Avg Memory', value: `${systems.infrastructure.avg_memory_percent}%` },
      ],
      link: '/infrastructure',
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <SystemHealthCard
          key={card.title}
          title={card.title}
          status={card.status}
          icon={card.icon}
          metrics={card.metrics}
          onClick={() => navigate(card.link)}
        />
      ))}
    </div>
  );
}
