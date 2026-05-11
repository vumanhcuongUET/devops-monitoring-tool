import { useQuery } from '@tanstack/react-query';
import { POLL_INTERVAL } from '../utils/constants';

export function usePolling<T>(key: string[], fetcher: () => Promise<T>, enabled = true) {
  return useQuery<T>({
    queryKey: key,
    queryFn: fetcher,
    refetchInterval: POLL_INTERVAL,
    enabled,
  });
}
