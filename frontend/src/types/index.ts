export type HealthStatus = 'healthy' | 'degraded' | 'down';
export type AlertSeverity = 'info' | 'warning' | 'critical';

export interface KubernetesHealth {
  status: HealthStatus;
  pods_total: number;
  pods_running: number;
  pods_pending: number;
  pods_failed: number;
  deployments_total: number;
  deployments_available: number;
}

export interface ElasticsearchHealth {
  status: HealthStatus;
  error_count_1h: number;
  cluster_health: string;
}

export interface ApmHealth {
  status: HealthStatus;
  avg_latency_ms: number;
  error_rate_percent: number;
  transactions_per_minute: number;
}

export interface InfrastructureHealth {
  status: HealthStatus;
  nodes_total: number;
  nodes_healthy: number;
  avg_cpu_percent: number;
  avg_memory_percent: number;
}

export interface OverviewResponse {
  timestamp: string;
  systems: {
    kubernetes: KubernetesHealth;
    elasticsearch: ElasticsearchHealth;
    apm: ApmHealth;
    infrastructure: InfrastructureHealth;
  };
  active_alerts: number;
  recent_alerts: AlertEvent[];
}

export interface LogEntry {
  timestamp: string;
  level: string;
  service: string;
  message: string;
  metadata?: Record<string, unknown>;
}

export interface LogQueryParams {
  q?: string;
  level?: string;
  service?: string;
  start?: string;
  end?: string;
  page?: number;
  size?: number;
}

export interface LogsResponse {
  total: number;
  page: number;
  size: number;
  items: LogEntry[];
}

export interface Transaction {
  name: string;
  type: string;
  result: string;
  latency_p50: number;
  latency_p95: number;
  latency_p99: number;
  throughput: number;
}

export interface ApmError {
  grouping_key: string;
  message: string;
  type: string;
  count: number;
  last_seen: string;
}

export interface ApmSummary {
  latency_p50: number;
  latency_p95: number;
  latency_p99: number;
  error_rate_percent: number;
  throughput: number;
}

export interface MetricSeries {
  timestamp: string;
  value: number;
}

export interface NodeMetrics {
  name: string;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  cpu_history: MetricSeries[];
  memory_history: MetricSeries[];
}

export interface PodStatus {
  name: string;
  namespace: string;
  status: string;
  restarts: number;
  age: string;
  node: string;
}

export interface DeploymentStatus {
  name: string;
  namespace: string;
  replicas: number;
  available: number;
  updated: number;
  image: string;
}

export interface K8sEvent {
  timestamp: string;
  type: string;
  reason: string;
  message: string;
  object: string;
}

export interface AlertRule {
  id: string;
  name: string;
  source: string;
  metric: string;
  condition: string;
  threshold: number;
  duration_seconds: number;
  severity: AlertSeverity;
  enabled: boolean;
  notify_slack: boolean;
  notify_email: boolean;
  notify_webhook: boolean;
  labels: Record<string, string>;
}

export interface AlertEvent {
  id: string;
  rule_id: string;
  rule_name: string;
  severity: AlertSeverity;
  status: 'firing' | 'resolved';
  value: number;
  threshold: number;
  message: string;
  timestamp: string;
}

export interface TimeRange {
  start: string;
  end: string;
  label: string;
}

export type SloStatus = 'healthy' | 'warning' | 'critical' | 'breached';

export interface SloConfig {
  id: string;
  service_name: string;
  slo_type: 'availability' | 'latency';
  target: number;
  latency_threshold_ms?: number;
  window_days: number;
  enabled: boolean;
}

export interface SloResult {
  config_id: string;
  service_name: string;
  slo_type: string;
  target: number;
  current_value: number;
  total_requests: number;
  good_requests: number;
  bad_requests: number;
  error_budget_remaining_percent: number;
  error_budget_total: number;
  error_budget_consumed: number;
  status: SloStatus;
  window_days: number;
  latency_p50?: number;
  latency_p95?: number;
  latency_p99?: number;
}

export interface SloApiDetail {
  transaction_name: string;
  total_requests: number;
  error_count: number;
  availability_percent: number;
  latency_p50: number;
  latency_p95: number;
  latency_p99: number;
  slo_met: boolean;
  slo_type: string;
  target: number;
}

export interface SloDashboard {
  timestamp: string;
  total_slos: number;
  healthy_count: number;
  warning_count: number;
  breached_count: number;
  avg_budget_remaining: number;
  results: SloResult[];
}
