"""
Test Data Generator - Realistic incident data for validation.

Phase 6: AI Input Optimization & Cost Efficiency
Day 2: Create test data generator for comprehensive testing
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import numpy as np

IncidentType = Literal[
    'high_latency', 'error_spike', 'pod_crashloop', 'resource_exhaustion',
    'database_slow', 'network_issue', 'disk_full', 'memory_leak',
    'cpu_throttling', 'connection_pool_exhausted', 'queue_backing_up',
    'cache_failure', 'ssl_expiry', 'dns_failure'
]


class TestDataGenerator:
    """
    Generate realistic test data for optimization validation.

    Creates complete incident context including:
    - Logs with proper severity distribution
    - Metrics with realistic values and anomalies
    - APM data with transaction details
    - Kubernetes state
    - Alert configurations
    """

    METRIC_TYPES = {
        'cpu': {'unit': 'percent', 'high': 80, 'critical': 90},
        'memory': {'unit': 'percent', 'high': 85, 'critical': 95},
        'disk': {'unit': 'percent', 'high': 90, 'critical': 95},
        'network_io': {'unit': 'bytes/sec', 'high_multiplier': 3.0, 'critical_multiplier': 5.0},
        'disk_io': {'unit': 'iops', 'high_multiplier': 3.0, 'critical_multiplier': 5.0},
        'error_rate': {'unit': 'percent', 'high': 5, 'critical': 10},
    }

    def __init__(self, seed: int = 42):
        """Initialize with seed for reproducibility."""
        random.seed(seed)
        np.random.seed(seed)

    def generate_incident(
        self,
        incident_type: IncidentType,
        severity: Literal['low', 'medium', 'high', 'critical'] = 'medium',
        complexity: float = 0.5,
        duration_minutes: int = 60
    ) -> dict[str, Any]:
        """
        Generate realistic incident data.

        Args:
            incident_type: Type of incident to generate
            severity: Severity level (affects data volume and impact)
            complexity: 0.0 (simple) to 1.0 (complex with multiple symptoms)
            duration_minutes: Duration of incident data

        Returns:
            Complete incident context with logs, metrics, APM data, K8s state
        """
        incident = {
            'metadata': {
                'type': incident_type,
                'severity': severity,
                'complexity': complexity,
                'duration_minutes': duration_minutes,
                'generated_at': datetime.now(timezone.utc).isoformat()
            },
            'incident_timestamp': (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
            'logs': self._generate_logs(incident_type, severity, complexity, duration_minutes),
            'metrics': self._generate_metrics(incident_type, severity, complexity, duration_minutes),
            'apm_data': self._generate_apm_data(incident_type, severity, complexity),
            'kubernetes_state': self._generate_k8s_state(incident_type, severity),
            'alerts': self._generate_alerts(incident_type, severity)
        }

        return incident

    def _generate_logs(
        self,
        incident_type: str,
        severity: str,
        complexity: float,
        duration_minutes: int
    ) -> dict[str, Any]:
        """Generate realistic log entries."""
        # Base log count by severity and duration
        base_count = int(1000 * (1 + duration_minutes / 60) * self._severity_multiplier(severity))

        # Add complexity noise
        noise_count = int(base_count * complexity * 0.5)
        total_count = base_count + noise_count

        logs = []
        severity_dist = {'critical': 0, 'error': 0, 'warning': 0, 'info': 0, 'debug': 0}

        # Incident-specific log patterns
        log_templates = self._get_log_templates_for_incident(incident_type)

        # Generate logs across time window
        start_time = datetime.now(timezone.utc) - timedelta(minutes=duration_minutes)

        for _i in range(total_count):
            timestamp = start_time + timedelta(
                seconds=random.randint(0, duration_minutes * 60)
            )

            # Select severity based on incident type
            if incident_type in ['error_spike', 'database_slow', 'pod_crashloop']:
                sev = 'error' if random.random() < 0.3 else 'warning'
            else:
                sev = 'info'
                if random.random() < 0.1:
                    sev = 'warning'
                if random.random() < 0.02:
                    sev = 'error'

            severity_dist[sev] += 1

            # Select template
            templates = log_templates.get(sev, log_templates['info'])
            template = random.choice(templates)

            # Generate service and pod
            service = random.choice(['api', 'worker', 'scheduler', 'gateway'])
            pod = f"pod-{random.randint(1, 10)}"
            node = f"node-{random.randint(1, 5)}"

            logs.append({
                '@timestamp': timestamp.isoformat(),
                'severity': sev,
                'level': sev,
                'message': template.format(
                    service=service,
                    pod=pod,
                    node=node,
                    error_code=random.choice(['500', '502', '503', '504']) if sev == 'error' else '200'
                ),
                'kubernetes': {
                    'pod_name': pod,
                    'namespace': random.choice(['production', 'staging']),
                    'node_name': node,
                    'service_name': service
                },
                'service': service
            })

        return {
            'total': len(logs),
            'logs': logs[:100] if len(logs) > 100 else logs,  # Return sample
            'severity_distribution': severity_dist
        }

    def _get_log_templates_for_incident(self, incident_type: str) -> dict[str, list[str]]:
        """Get log templates specific to incident type."""
        templates = {
            'critical': [
                "CRITICAL: Service {service} on {pod} - unable to serve requests",
                "CRITICAL: Database connection lost on {service}",
                "CRITICAL: Pod {pod} in CrashLoopBackOff state"
            ],
            'error': [
                "ERROR: Connection timeout to {service} on {pod}",
                "ERROR: Database query exceeded 5000ms: {service}",
                "ERROR: Failed to process request: timeout in {pod}",
                "ERROR: HTTP {error_code} in {service} - Connection reset"
            ],
            'warning': [
                "WARN: High memory usage on {pod}: 85%",
                "WARN: Slow query detected on {service}: 2300ms",
                "WARN: Retrying connection to {service}",
                "WARN: Queue depth increasing: {pod}"
            ],
            'info': [
                "INFO: Request processed successfully by {service}",
                "INFO: Health check passed for {pod}",
                "INFO: Scheduled task completed",
                "INFO: Metrics collection from {node}"
            ]
        }

        # Customize for specific incident types
        if incident_type == 'database_slow':
            templates['error'].append(
                "ERROR: Query execution time exceeded threshold in {service}"
            )
        elif incident_type == 'pod_crashloop':
            templates['critical'].append(
                "CRITICAL: Pod {pod} restarted 5 times in last 10 minutes"
            )
        elif incident_type == 'network_issue':
            templates['warning'].append(
                "WARN: Network latency between {service} and {node} > 200ms"
            )

        return templates

    def _severity_multiplier(self, severity: str) -> float:
        """Get multiplier for data volume based on severity."""
        return {
            'low': 0.5,
            'medium': 1.0,
            'high': 2.0,
            'critical': 3.0
        }.get(severity, 1.0)

    def _generate_metrics(
        self,
        incident_type: str,
        severity: str,
        complexity: float,
        duration_minutes: int
    ) -> dict[str, Any]:
        """Generate Prometheus-style metrics data."""
        metrics = {}

        # Determine which metrics are affected by incident
        affected_metrics = self._get_affected_metrics(incident_type)

        # Generate each metric type
        for metric_name, config in self.METRIC_TYPES.items():
            if metric_name in ['network_io', 'disk_io']:
                # These are rate-based metrics
                metrics[f"{metric_name}_in"] = self._generate_metric_series(
                    baseline=1000000,  # 1MB/sec baseline
                    incident_type=incident_type,
                    severity=severity,
                    duration_minutes=duration_minutes,
                    affected=f"{metric_name}_in" in affected_metrics
                )
                metrics[f"{metric_name}_out"] = self._generate_metric_series(
                    baseline=500000,  # 500KB/sec baseline
                    incident_type=incident_type,
                    severity=severity,
                    duration_minutes=duration_minutes,
                    affected=f"{metric_name}_out" in affected_metrics
                )
            else:
                # Percentage/absolute metrics
                baseline = config.get('high', 80) * 0.6  # 60% of high threshold as baseline
                metrics[f"{metric_name}_percent"] = self._generate_metric_series(
                    baseline=baseline,
                    incident_type=incident_type,
                    severity=severity,
                    duration_minutes=duration_minutes,
                    affected=metric_name in affected_metrics,
                    unit='percent'
                )

        # Add rate metrics
        metrics['rate_http_requests_total'] = self._generate_metric_series(
            baseline=150.0,
            incident_type=incident_type,
            severity=severity,
            duration_minutes=duration_minutes,
            affected=True,
            unit='requests_per_second'
        )

        metrics['rate_http_requests_error_total'] = self._generate_metric_series(
            baseline=2.0,
            incident_type=incident_type,
            severity=severity,
            duration_minutes=duration_minutes,
            affected=incident_type in ['error_spike', 'database_slow'],
            unit='requests_per_second'
        )

        return metrics

    def _generate_metric_series(
        self,
        baseline: float,
        incident_type: str,
        severity: str,
        duration_minutes: int,
        affected: bool = False,
        unit: str = 'percent'
    ) -> dict[str, Any]:
        """Generate time series data for a metric."""
        points = 60  # One point per minute
        timestamps = []
        values = []

        start = datetime.now(timezone.utc) - timedelta(minutes=duration_minutes)

        for i in range(points):
            ts = start + timedelta(minutes=i)
            timestamps.append(ts.isoformat())

            # Add random noise to baseline
            noise = np.random.normal(0, baseline * 0.1)
            value = baseline + noise

            # Inject incident pattern if affected
            if affected and i > 20 and i < 50:  # Incident in middle
                severity_factor = self._severity_multiplier(severity)
                if incident_type in ['cpu_throttling', 'memory_leak', 'resource_exhaustion']:
                    # Gradual increase
                    factor = 1 + ((i - 20) / 30) * severity_factor
                    value *= factor
                else:
                    # Sudden spike
                    value *= (1 + severity_factor * 0.5)

            values.append(max(0, value))

        return {
            'unit': unit,
            'baseline': baseline,
            'current': values[-1],
            'timestamps': timestamps[:10],  # Sample for token optimization
            'values': values[:10],
            'affected': affected,
            'anomaly_detected': affected and values[-1] > baseline * 1.5
        }

    def _get_affected_metrics(self, incident_type: str) -> list[str]:
        """Get list of metrics affected by incident type."""
        mapping = {
            'high_latency': ['cpu', 'memory', 'network_io'],
            'error_spike': ['error_rate', 'network_io'],
            'pod_crashloop': ['cpu', 'memory', 'error_rate'],
            'resource_exhaustion': ['cpu', 'memory', 'disk'],
            'database_slow': ['cpu', 'memory', 'disk_io'],
            'network_issue': ['network_io'],
            'disk_full': ['disk', 'disk_io'],
            'memory_leak': ['memory'],
            'cpu_throttling': ['cpu']
        }
        return mapping.get(incident_type, [])

    def _generate_apm_data(
        self,
        incident_type: str,
        severity: str,
        complexity: float
    ) -> dict[str, Any]:
        """Generate APM-style data."""
        return {
            'latency_history': self._generate_metric_series(
                baseline=150.0,
                incident_type=incident_type,
                severity=severity,
                duration_minutes=60,
                affected=incident_type in ['high_latency', 'database_slow'],
                unit='ms'
            ),
            'throughput_history': self._generate_metric_series(
                baseline=1000.0,
                incident_type=incident_type,
                severity=severity,
                duration_minutes=60,
                affected=True,
                unit='requests_per_minute'
            ),
            'error_rate_history': self._generate_metric_series(
                baseline=2.0,
                incident_type=incident_type,
                severity=severity,
                duration_minutes=60,
                affected=incident_type in ['error_spike', 'database_slow'],
                unit='percent'
            ),
            'top_errors': self._generate_apm_errors(incident_type, severity),
            'slow_transactions': self._generate_slow_transactions(incident_type, severity)
        }

    def _generate_apm_errors(self, incident_type: str, severity: str) -> list[dict]:
        """Generate APM error entries."""
        error_templates = {
            'high_latency': ['TimeoutError', 'SlowQueryError'],
            'error_spike': ['ConnectionError', 'HTTPError', 'DatabaseError'],
            'pod_crashloop': ['ContainerKilledError', 'OOMKilledError'],
            'database_slow': ['QueryTimeoutError', 'DeadlockError'],
            'network_issue': ['NetworkError', 'DNSError']
        }

        templates = error_templates.get(incident_type, ['GenericError'])

        errors = []
        for _i in range(5):
            error_type = random.choice(templates)
            errors.append({
                'error': error_type,
                'occurrences': random.randint(10, 100) if severity == 'critical' else random.randint(5, 50),
                'transaction_name': f"/api/{random.choice(['users', 'orders', 'payments', 'products'])}",
                'service_name': random.choice(['api-service', 'worker-service', 'payment-service'])
            })

        return sorted(errors, key=lambda x: x['occurrences'], reverse=True)

    def _generate_slow_transactions(self, incident_type: str, severity: str) -> list[dict]:
        """Generate slow transaction entries."""
        if incident_type not in ['high_latency', 'database_slow']:
            return []

        transactions = []
        endpoints = ['/api/users', '/api/orders', '/api/payments', '/api/products']

        for endpoint in endpoints:
            base_latency = random.randint(100, 500)
            latency_multiplier = self._severity_multiplier(severity)

            transactions.append({
                'transaction_name': endpoint,
                'current_latency_ms': base_latency * latency_multiplier,
                'p95_latency_ms': base_latency * latency_multiplier * 1.5,
                'p99_latency_ms': base_latency * latency_multiplier * 2.0,
                'service_name': 'api-service'
            })

        return sorted(transactions, key=lambda x: x['current_latency_ms'], reverse=True)

    def _generate_k8s_state(self, incident_type: str, severity: str) -> dict[str, Any]:
        """Generate Kubernetes state data."""
        state = {
            'pods_total': 10,
            'pods_healthy': 8,
            'pods_unhealthy': 2,
            'deployments_total': 3,
            'unhealthy_deployments': [],
            'nodes': []
        }

        # Customize based on incident type
        if incident_type == 'pod_crashloop':
            state['pods_unhealthy'] = 5 if severity == 'critical' else 3
            state['pods_healthy'] = 10 - state['pods_unhealthy']
            state['unhealthy_deployments'] = ['api-deployment']

        elif incident_type == 'resource_exhaustion':
            state['nodes'] = [
                {
                    'name': f'node-{i}',
                    'cpu_percent': 90 + random.randint(0, 10),
                    'memory_percent': 85 + random.randint(0, 15),
                    'disk_percent': 70 + random.randint(0, 20)
                }
                for i in range(3)
            ]

        return state

    def _generate_alerts(self, incident_type: str, severity: str) -> list[dict]:
        """Generate alert configurations."""
        alert_count = 3 if severity == 'low' else 5 if severity == 'medium' else 8

        alerts = []
        for i in range(alert_count):
            alerts.append({
                'rule_name': f"{incident_type.replace('_', ' ').title()} Alert {i+1}",
                'severity': severity,
                'message': f"{incident_type.replace('_', ' ')} detected in cluster",
                'triggered_at': (datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 60))).isoformat(),
                'status': 'firing'
            })

        return alerts

    # ========== Batch Generation ==========

    def generate_batch(
        self,
        incident_types: list[IncidentType],
        count_per_type: int = 5
    ) -> list[dict[str, Any]]:
        """
        Generate a batch of incidents across multiple types.

        Args:
            incident_types: List of incident types to generate
            count_per_type: Number of incidents per type

        Returns:
            List of generated incidents
        """
        incidents = []

        for incident_type in incident_types:
            for i in range(count_per_type):
                severity = ['low', 'medium', 'high', 'critical'][i % 4]
                complexity = 0.3 + (i * 0.1)  # 0.3 to 0.7

                incident = self.generate_incident(
                    incident_type=incident_type,
                    severity=severity,
                    complexity=complexity
                )

                incidents.append(incident)

        return incidents

    def get_incident_types(self) -> list[str]:
        """Get list of available incident types."""
        return list(IncidentType.__args__)


# Convenience function for easy import
def get_test_data_generator(seed: int = 42) -> TestDataGenerator:
    """Get or create TestDataGenerator instance."""
    return TestDataGenerator(seed=seed)
