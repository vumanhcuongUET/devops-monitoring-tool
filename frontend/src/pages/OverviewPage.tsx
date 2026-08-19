import { useWebSocket } from '../hooks/useWebSocket';
import { usePolling } from '../hooks/usePolling';
import { useQuery } from '@tanstack/react-query';
import { fetchOverview } from '../api/overview';
import { fetchAlertHistory } from '../api/alerts';
import { SystemGrid } from '../components/overview/SystemGrid';
import { RecentAlerts } from '../components/overview/RecentAlerts';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ApiDownEmptyState } from '../components/common';
import type { OverviewResponse, AlertEvent } from '../types';

export function OverviewPage() {
  const { data: wsData, connected } = useWebSocket();

  // Use TanStack Query for better error handling
  const {
    data: pollingData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['overview'],
    queryFn: fetchOverview,
    enabled: !connected,
    retry: 2,
    retryDelay: 1000,
  });

  const {
    data: alertHistory,
    error: alertHistoryError,
    isError: alertHistoryIsError,
  } = useQuery({
    queryKey: ['alert-history'],
    queryFn: fetchAlertHistory,
    enabled: !!pollingData || !!wsData,
    // Don't fail entire page if alert history fails
    retry: 1,
    onError: (err) => {
      // Log error but don't crash the page
      console.error('Failed to fetch alert history:', err);
    },
  });

  const data = wsData || pollingData;

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
