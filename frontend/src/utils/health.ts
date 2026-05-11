export type HealthStatus = 'healthy' | 'degraded' | 'down';

export function getHealthColor(status: HealthStatus): string {
  switch (status) {
    case 'healthy': return 'var(--color-healthy)';
    case 'degraded': return 'var(--color-degraded)';
    case 'down': return 'var(--color-down)';
  }
}

export function getHealthLabel(status: HealthStatus): string {
  switch (status) {
    case 'healthy': return 'Healthy';
    case 'degraded': return 'Degraded';
    case 'down': return 'Down';
  }
}
