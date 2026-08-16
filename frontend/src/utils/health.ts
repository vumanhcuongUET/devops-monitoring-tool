export type HealthStatus = 'healthy' | 'degraded' | 'down' | 'unknown';

export function getHealthColor(status: HealthStatus): string {
  switch (status) {
    case 'healthy': return 'var(--color-healthy)';
    case 'degraded': return 'var(--color-degraded)';
    case 'down': return 'var(--color-down)';
    case 'unknown':
    default: return 'var(--color-unknown)';
  }
}

export function getHealthLabel(status: HealthStatus): string {
  switch (status) {
    case 'healthy': return 'Healthy';
    case 'degraded': return 'Degraded';
    case 'down': return 'Down';
    case 'unknown':
    default: return 'Unknown';
  }
}
