import { useMemo } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useQuery } from '@tanstack/react-query';
import { fetchOverview } from '../api/overview';
import { fetchAlertHistory } from '../api/alerts';
import { SystemGrid } from '../components/overview/SystemGrid';
import { RecentAlerts } from '../components/overview/RecentAlerts';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ApiDownEmptyState } from '../components/common';

export function OverviewPage() {
  const { data: wsData, connected } = useWebSocket();

  // Always poll as the safety net (slow); live updates arrive over the
  // WebSocket push and win when fresher. Phase 16 P1-7: polling used to be
  // disabled entirely once the socket connected, but nothing on the backend
  // ever sent "overview_update" — the page froze on its mount-time snapshot
  // under a "Live" badge.
  const {
    data: pollingData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['overview'],
    queryFn: fetchOverview,
    refetchInterval: connected ? 60000 : 10000,
    retry: 2,
    retryDelay: 1000,
  });

  const { data: alertHistory } = useQuery({
    queryKey: ['alert-history'],
    queryFn: fetchAlertHistory,
    enabled: !!pollingData || !!wsData,
    // Don't fail entire page if alert history fails
    retry: 1,
  });

  // Whichever source is fresher wins — a dead WS push loop degrades to the
  // poll, a fast WS event beats the stale poll snapshot.
  const data = useMemo(() => {
    if (pollingData && wsData) {
      return new Date(wsData.timestamp) >= new Date(pollingData.timestamp)
        ? wsData
        : pollingData;
    }
    return wsData ?? pollingData;
  }, [pollingData, wsData]);

  if (isLoading && !data) {
    return <LoadingSkeleton rows={4} />;
  }

  // API is down or unreachable
  if (error && !data) {
    return (
      <ApiDownEmptyState
        onRetry={() => refetch()}
      />
    );
  }

  if (!data) {
    return (
      <div className="text-[var(--color-text-secondary)]">
        No overview data available. Start monitoring to see data here.
      </div>
    );
  }

  // Use alertHistory if available, otherwise fall back to recent_alerts from overview data
  // If alertHistory query failed, we still render the page with recent_alerts
  const alerts = alertHistory || data.recent_alerts || [];

  return (
    <div className="space-y-6">
      <SystemGrid data={data} />
      <RecentAlerts alerts={alerts} />
    </div>
  );
}
