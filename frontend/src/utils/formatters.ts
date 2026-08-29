export function formatTimestamp(ts?: string): string {
  return new Date(ts ?? '').toLocaleString('vi-VN');
}

export function formatBytes(bytes?: number): string {
  if (bytes === 0) return '0 B';
  if (bytes == null || Number.isNaN(bytes)) return 'NaN B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export function formatDuration(ms?: number): string {
  if (ms == null || Number.isNaN(ms)) return 'NaNms';
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function formatPercent(value?: number): string {
  if (value == null || Number.isNaN(value)) return 'NaN%';
  return `${value.toFixed(1)}%`;
}
