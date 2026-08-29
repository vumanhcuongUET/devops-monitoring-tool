"""
Relevance Scorer - Multi-factor relevance scoring for data selection.

Scores logs, metrics, and other data by relevance to incident context.

Phase 6: AI Input Optimization - Sprint 3
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RelevanceScore:
    """Relevance score for a data item."""
    item: dict[str, Any]
    score: float
    keyword_score: float
    temporal_score: float
    severity_score: float
    service_score: float


class RelevanceScorer:
    """
    Multi-factor relevance scoring for intelligent data selection.

    Combines keyword matching, temporal proximity, severity matching,
    and service relevance to score data items.
    """

    # Default weights for scoring factors
    DEFAULT_WEIGHTS = {
        'keyword': 0.4,
        'temporal': 0.3,
        'severity': 0.2,
        'service': 0.1
    }

    def __init__(self, weights: dict[str, float] | None = None):
        """
        Initialize relevance scorer.

        Args:
            weights: Optional custom weights for scoring factors
        """
        self.weights = weights or self.DEFAULT_WEIGHTS

    def score_logs(
        self,
        logs: list[dict[str, Any]],
        incident_type: str,
        alert_message: str,
        alert_keywords: list[str],
        incident_timestamp: datetime | None = None
    ) -> list[RelevanceScore]:
        """
        Score logs by relevance to incident.

        Args:
            logs: List of log entries
            incident_type: Type of incident
            alert_message: Alert message
            alert_keywords: Keywords extracted from alert
            incident_timestamp: When incident occurred

        Returns:
            List of logs sorted by relevance score
        """
        if not logs:
            return []

        # Extract keywords from alert if not provided
        if not alert_keywords:
            alert_keywords = self._extract_keywords(alert_message)

        # Get severity from incident type
        expected_severity = self._infer_severity(incident_type)

        # Score each log
        scored_logs = []
        for log in logs:
            score = self._score_log(
                log,
                alert_keywords,
                incident_timestamp,
                expected_severity
            )
            scored_logs.append(score)

        # Sort by score descending
        scored_logs.sort(key=lambda x: x.score, reverse=True)
        return scored_logs

    def score_metrics(
        self,
        metrics: dict[str, Any],
        incident_type: str
    ) -> dict[str, float]:
        """
        Score metrics by relevance to incident type.

        Args:
            metrics: Metrics dictionary
            incident_type: Type of incident

        Returns:
            Dict of metric names to scores
        """
        relevant_metrics = self._get_relevant_metrics(incident_type)
        scores = {}

        for metric_name in metrics:
            if metric_name in relevant_metrics:
                scores[metric_name] = 1.0
            else:
                scores[metric_name] = 0.3  # Low relevance for non-matching

        return scores

    def _score_log(
        self,
        log: dict[str, Any],
        keywords: list[str],
        incident_timestamp: datetime | None,
        expected_severity: str
    ) -> RelevanceScore:
        """Score a single log entry."""
        # Keyword score
        keyword_score = self._calculate_keyword_score(log, keywords)

        # Temporal score
        temporal_score = self._calculate_temporal_score(log, incident_timestamp)

        # Severity score
        severity_score = self._calculate_severity_score(log, expected_severity)

        # Service score
        service_score = self._calculate_service_score(log)

        # Weighted total
        total_score = (
            keyword_score * self.weights['keyword'] +
            temporal_score * self.weights['temporal'] +
            severity_score * self.weights['severity'] +
            service_score * self.weights['service']
        )

        return RelevanceScore(
            item=log,
            score=total_score,
            keyword_score=keyword_score,
            temporal_score=temporal_score,
            severity_score=severity_score,
            service_score=service_score
        )

    def _calculate_keyword_score(self, log: dict[str, Any], keywords: list[str]) -> float:
        """Calculate keyword matching score."""
        if not keywords:
            return 0.5  # Neutral score if no keywords

        message = str(log.get('message', log.get('msg', ''))).lower()

        matches = sum(1 for keyword in keywords if keyword.lower() in message)

        # Score based on number of matches (max 1.0)
        return min(matches / len(keywords), 1.0) if keywords else 0.5

    def _calculate_temporal_score(
        self,
        log: dict[str, Any],
        incident_timestamp: datetime | None
    ) -> float:
        """Calculate temporal proximity score."""
        if not incident_timestamp:
            return 0.5  # Neutral if no timestamp

        log_time_str = log.get('@timestamp', log.get('timestamp', ''))
        if not log_time_str:
            return 0.0

        try:
            log_time = datetime.fromisoformat(log_time_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return 0.0

        time_diff = abs((incident_timestamp - log_time).total_seconds())

        # Scoring tiers
        if time_diff <= 300:  # 5 minutes
            return 1.0
        elif time_diff <= 900:  # 15 minutes
            return 0.7
        elif time_diff <= 1800:  # 30 minutes
            return 0.4
        elif time_diff <= 3600:  # 1 hour
            return 0.2
        else:
            return 0.1

    def _calculate_severity_score(self, log: dict[str, Any], expected_severity: str) -> float:
        """Calculate severity matching score."""
        log_severity = log.get('severity', log.get('level', 'info')).lower()

        # Direct match
        if log_severity == expected_severity.lower():
            return 1.0

        # Severity hierarchy match
        severity_order = ['critical', 'error', 'warn', 'warning', 'info', 'debug']

        try:
            log_idx = severity_order.index(log_severity)
            expected_idx = severity_order.index(expected_severity.lower())

            # Score based on distance
            distance = abs(log_idx - expected_idx)
            return max(1.0 - (distance * 0.2), 0.0)
        except ValueError:
            return 0.5

    def _calculate_service_score(self, log: dict[str, Any]) -> float:
        """Calculate service relevance score."""
        # Extract service/pod information
        service = log.get('service', log.get('kubernetes', {}).get('service_name', ''))

        # If log has service info, give it higher score
        return 0.8 if service else 0.3

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text."""
        if not text:
            return []

        # Simple extraction: lowercase and split on common separators
        import re
        words = re.findall(r'\w+', text.lower())

        # Filter out common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'is'}
        keywords = [w for w in words if len(w) > 2 and w not in stopwords]

        return keywords

    def _infer_severity(self, incident_type: str) -> str:
        """Infer expected severity from incident type."""
        severity_map = {
            'pod_crashloop': 'critical',
            'high_error_rate': 'error',
            'database_slow': 'warning',
            'disk_full': 'critical',
            'resource_exhaustion': 'critical',
            'network_issue': 'warning',
            'deployment_failure': 'error'
        }
        return severity_map.get(incident_type, 'warning')

    def _get_relevant_metrics(self, incident_type: str) -> set:
        """Get relevant metrics for incident type."""
        mapping = {
            'high_latency': {'cpu_percent', 'memory_percent', 'response_time', 'latency'},
            'high_error_rate': {'error_rate', 'error_count', 'error_rate_percent'},
            'pod_crashloop': {'restart_count', 'pod_status', 'crash_loop_count'},
            'disk_full': {'disk_percent', 'disk_usage', 'disk_available'},
            'database_slow': {'db_query_time', 'db_connections', 'db_slow_queries'},
            'network_issue': {'network_io_in', 'network_io_out', 'network_latency'},
            'resource_exhaustion': {'cpu_percent', 'memory_percent', 'disk_percent'}
        }
        return mapping.get(incident_type, set())


# Singleton instance
_relevance_scorer: RelevanceScorer | None = None


def get_relevance_scorer(weights: dict[str, float] | None = None) -> RelevanceScorer:
    """Get or create the singleton RelevanceScorer instance."""
    global _relevance_scorer
    if _relevance_scorer is None:
        _relevance_scorer = RelevanceScorer(weights)
    return _relevance_scorer
