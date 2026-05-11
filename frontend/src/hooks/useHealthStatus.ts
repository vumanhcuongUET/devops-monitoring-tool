import type { HealthStatus } from '../types';
import { getHealthColor, getHealthLabel } from '../utils/health';

export function useHealthStatus(status: HealthStatus) {
  return {
    color: getHealthColor(status),
    label: getHealthLabel(status),
  };
}
