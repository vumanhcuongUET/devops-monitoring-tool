import { useWebSocket } from '../hooks/useWebSocket';
import { usePolling } from '../hooks/usePolling';
import { fetchOverview } from '../api/overview';
import { fetchAlertHistory } from '../api/alerts';
import { SystemGrid } from '../components/overview/SystemGrid';
import { RecentAlerts } from '../components/overview/RecentAlerts';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import type { OverviewResponse, AlertEvent } from '../types';

export function OverviewPage() {
  const { data: wsData, connected } = useWebSocket();
  const { data: pollingData, isLoading } = usePolling<OverviewResponse>(
    ['overview'],
    fetchOverview,
    !connected,
  );
  const { data: alertHistory } = usePolling<AlertEvent[]>(
    ['alert-history'],
    fetchAlertHistory,
  );

  const data = wsData || pollingData;

  if (isLoading && !data) {
    return <LoadingSkeleton rows={4} />;
  }

  if (!data) {
    return <div className="text-[var(--color-text-secondary)]">Unable to load overview data</div>;
  }

  return (
    <div className="space-y-6">
      <SystemGrid data={data} />
      <RecentAlerts alerts={alertHistory || data.recent_alerts || []} />
    </div>
  );
}
