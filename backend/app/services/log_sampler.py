"""
Log Sampler Service - Priority-based log sampling for token optimization.

This module implements intelligent log sampling that prioritizes critical
and relevant log entries while staying within token budget.

Phase 6: AI Input Optimization & Cost Efficiency
Enhanced for Day 3: Temporal scoring, keyword extraction, 4-factor relevance
"""

from datetime import datetime, timedelta, timezone
from typing import Any, List, Tuple, Dict, Optional, Set
from dataclasses import dataclass
from enum import Enum
import re


class LogSeverity(str, Enum):
    """Log severity levels."""
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


@dataclass
class SamplingQuotas:
    """Quotas for log sampling by severity."""
    critical: int = 5
    error: int = 10
    warning: int = 10
    info: int = 5


@dataclass
class LogScore:
    """Score for a log entry."""
    log: dict
    score: float
    reasons: List[str]


@dataclass
class RelevanceScore:
    """Comprehensive relevance score with breakdown (NEW for Day 3)."""
    total_score: float
    keyword_score: float      # 0.4 weight
    temporal_score: float      # 0.3 weight
    severity_score: float      # 0.2 weight
    service_score: float       # 0.1 weight

    def to_dict(self) -> Dict:
        return {
            'total': self.total_score,
            'keyword': self.keyword_score,
            'temporal': self.temporal_score,
            'severity': self.severity_score,
            'service': self.service_score
        }


class KeywordExtractor:
    """Extract relevant keywords from alert messages (NEW for Day 3)."""

    # Common stop words to filter out
    STOP_WORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
        'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were',
        'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'should', 'could', 'may', 'might', 'can', 'cannot',
        'alert', 'detected', 'found', 'observed', 'monitoring'
    }

    # Technical term patterns
    TECHNICAL_PATTERNS = [
        r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b',  # CamelCase (e.g., ApiServer)
        r'\b[a-z]+_[a-z_]+\b',                 # snake_case (e.g., api_server)
        r'\b[A-Z]{2,}\b',                      # Abbreviations (e.g., CPU, OOM)
        r'\b\d{1,5}\b',                        # Numbers (port numbers, etc)
        r'\b\d+\.\d+\.\d+\.\d+\b',            # IP addresses
        r'\b\w+@\w+\.\w+\b',                  # Email addresses
    ]

    def extract_keywords(self, alert_message: str) -> List[str]:
        """
        Extract relevant keywords from alert message.

        Process:
        1. Tokenize message
        2. Filter stop words
        3. Extract technical terms
        4. Score by relevance
        5. Return top keywords

        Args:
            alert_message: Alert text to parse

        Returns:
            List of 5-10 relevant keywords
        """
        keywords = set()

        # 1. Extract technical terms using patterns
        for pattern in self.TECHNICAL_PATTERNS:
            matches = re.findall(pattern, alert_message, re.IGNORECASE)
            keywords.update(matches)

        # 2. Tokenize and filter
        words = re.findall(r'\b\w+\b', alert_message.lower())

        # 3. Filter stop words and short words BEFORE adding to keywords
        significant_words = [
            w for w in words
            if w not in self.STOP_WORDS and len(w) > 2 and w not in ['was', 'were', 'been']
        ]
        keywords.update(significant_words)

        # 4. Extract service names (common patterns)
        service_keywords = self._extract_service_names(alert_message)
        keywords.update(service_keywords)

        # 5. Extract error types
        error_keywords = self._extract_error_types(alert_message)
        keywords.update(error_keywords)

        # 6. Filter stop words from final keywords and limit
        keyword_list = [kw for kw in keywords if kw.lower() not in self.STOP_WORDS][:10]

        return keyword_list

    def _extract_service_names(self, text: str) -> Set[str]:
        """Extract service/component names."""
        services = set()

        # Common service patterns
        service_patterns = [
            r'(\w+-service)',
            r'(\w+-worker)',
            r'(\w+-api)',
            r'(\w+-scheduler)',
            r'(pod/\w+)',
            r'(deployment/\w+)'
        ]

        for pattern in service_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            services.update(matches)

        return services

    def _extract_error_types(self, text: str) -> Set[str]:
        """Extract error types and status codes."""
        errors = set()

        # HTTP status codes
        status_codes = re.findall(r'\b[45]\d{2}\b', text)
        errors.update(status_codes)

        # Error types
        error_patterns = [
            r'(timeout)',
            r'(connection refused)',
            r'(OOMKilled)',
            r'(CrashLoopBackOff)',
            r'(502 Bad Gateway)',
            r'(503 Service Unavailable)',
            r'(connection timeout)',
            r'(dns error)'
        ]

        for pattern in error_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            errors.update(matches)

        return errors


class LogSampler:
    """
    Intelligent log sampler for token optimization.

    Prioritizes logs based on:
    - Severity level (critical > error > warning > info)
    - Relevance to incident (keyword matching)
    - Temporal proximity (closer to incident = higher score)
    """

    def __init__(self, config):
        """Initialize log sampler with configuration."""
        self.quotas = SamplingQuotas(
            critical=config.log_sampling_critical,
            error=config.log_sampling_error,
            warning=config.log_sampling_warning,
            info=config.log_sampling_info,
        )

        # NEW for Day 3: Enhanced relevance scoring
        self.keyword_extractor = KeywordExtractor()
        self.incident_timestamp = None
        self.incident_keywords = []
        self.incident_service = None
        self.incident_severity = None

    async def sample_logs(
        self,
        logs: List[dict],
        incident_type: str,
        max_results: int = 20,
        alert_keywords: List[str] = None,
        incident_timestamp: datetime = None
    ) -> List[dict]:
        """
        Sample logs based on priority and relevance.

        Args:
            logs: Raw log entries
            incident_type: Type of incident for relevance scoring
            max_results: Maximum number of logs to return
            alert_keywords: Keywords from alert for matching
            incident_timestamp: Timestamp of incident for temporal scoring

        Returns:
            Sampled logs within quota
        """
        if not logs:
            return []

        # Categorize logs by severity
        categorized = self._categorize_by_severity(logs)

        # Sample from each category based on quota
        sampled = []

        # Critical logs (highest priority)
        critical_logs = categorized.get(LogSeverity.CRITICAL, [])
        sampled.extend(self._select_top_logs(
            critical_logs,
            self.quotas.critical,
            alert_keywords,
            incident_timestamp
        ))

        # Error logs
        error_logs = categorized.get(LogSeverity.ERROR, [])
        sampled.extend(self._select_top_logs(
            error_logs,
            self.quotas.error,
            alert_keywords,
            incident_timestamp
        ))

        # Warning logs
        warning_logs = categorized.get(LogSeverity.WARNING, [])
        sampled.extend(self._select_top_logs(
            warning_logs,
            self.quotas.warning,
            alert_keywords,
            incident_timestamp
        ))

        # Info logs (minimal)
        info_logs = categorized.get(LogSeverity.INFO, [])
        sampled.extend(self._select_top_logs(
            info_logs,
            self.quotas.info,
            alert_keywords,
            incident_timestamp
        ))

        # Sort by combined score and limit
        scored_logs = self._score_logs(sampled, alert_keywords, incident_timestamp)
        scored_logs.sort(key=lambda x: x.score, reverse=True)

        # Return top logs up to max_results
        return [log.log for log in scored_logs[:max_results]]

    async def sample_apm_errors(
        self,
        apm_errors: List[dict],
        max_results: int = 10
    ) -> List[dict]:
        """
        Sample APM errors by occurrence count and relevance.

        Args:
            apm_errors: APM error entries
            max_results: Maximum number to return

        Returns:
            Sampled APM errors
        """
        if not apm_errors:
            return []

        # Sort by occurrence count (descending)
        sorted_errors = sorted(
            apm_errors,
            key=lambda x: x.get("occurrences", x.get("count", 0)),
            reverse=True
        )

        return sorted_errors[:max_results]

    def _categorize_by_severity(self, logs: List[dict]) -> dict[LogSeverity, List[dict]]:
        """Categorize logs by severity level."""
        categorized = {
            LogSeverity.CRITICAL: [],
            LogSeverity.ERROR: [],
            LogSeverity.WARNING: [],
            LogSeverity.INFO: [],
            LogSeverity.DEBUG: [],
        }

        for log in logs:
            severity = self._extract_severity(log)
            categorized[severity].append(log)

        return categorized

    def _extract_severity(self, log: dict) -> LogSeverity:
        """Extract severity level from log entry."""
        # Check common severity fields
        for field in ["level", "severity", "log_level"]:
            if field in log:
                level_str = str(log[field]).lower()
                if "crit" in level_str:
                    return LogSeverity.CRITICAL
                elif "err" in level_str:
                    return LogSeverity.ERROR
                elif "warn" in level_str:
                    return LogSeverity.WARNING
                elif "info" in level_str:
                    return LogSeverity.INFO
                elif "debug" in level_str:
                    return LogSeverity.DEBUG

        # Check message content
        message = str(log.get("message", log.get("msg", ""))).lower()
        if any(keyword in message for keyword in ["critical", "fatal", "panic"]):
            return LogSeverity.CRITICAL
        elif any(keyword in message for keyword in ["error", "exception", "fail"]):
            return LogSeverity.ERROR
        elif "warning" in message or "warn" in message:
            return LogSeverity.WARNING

        # Default to info
        return LogSeverity.INFO

    def _select_top_logs(
        self,
        logs: List[dict],
        quota: int,
        alert_keywords: List[str],
        incident_timestamp: datetime
    ) -> List[dict]:
        """Select top logs from a category."""
        if not logs:
            return []

        # Score and sort
        scored = self._score_logs(logs, alert_keywords, incident_timestamp)
        scored.sort(key=lambda x: x.score, reverse=True)

        # Return top logs up to quota
        return [log.log for log in scored[:quota]]

    def _score_logs(
        self,
        logs: List[dict],
        alert_keywords: List[str],
        incident_timestamp: datetime
    ) -> List[LogScore]:
        """Score logs based on multiple factors."""
        scored = []
        keywords = alert_keywords or []
        timestamp = incident_timestamp or datetime.now(timezone.utc)

        for log in logs:
            score = 0.0
            reasons = []

            # Base score from severity
            severity = self._extract_severity(log)
            if severity == LogSeverity.CRITICAL:
                score += 1.0
                reasons.append("critical_severity")
            elif severity == LogSeverity.ERROR:
                score += 0.8
                reasons.append("error_severity")
            elif severity == LogSeverity.WARNING:
                score += 0.5
                reasons.append("warning_severity")
            else:
                score += 0.2
                reasons.append("info_severity")

            # Keyword matching (0.3 weight)
            if keywords:
                message = str(log.get("message", log.get("msg", ""))).lower()
                matched_keywords = [kw for kw in keywords if kw.lower() in message]
                if matched_keywords:
                    keyword_score = (len(matched_keywords) / len(keywords)) * 0.3
                    score += keyword_score
                    reasons.append(f"keyword_match:{len(matched_keywords)}")

            # Temporal proximity (0.2 weight)
            if "timestamp" in log or "@timestamp" in log:
                try:
                    log_timestamp_str = log.get("timestamp") or log.get("@timestamp", "")
                    if isinstance(log_timestamp_str, str):
                        log_timestamp = datetime.fromisoformat(
                            log_timestamp_str.replace("Z", "+00:00")
                        )
                        time_diff = abs((timestamp - log_timestamp).total_seconds())

                        if time_diff < 300:  # 5 minutes
                            score += 0.2
                            reasons.append("recent_timestamp")
                        elif time_diff < 1800:  # 30 minutes
                            score += 0.1
                            reasons.append("recentish_timestamp")
                except (ValueError, AttributeError):
                    pass  # Ignore timestamp parsing errors

            scored.append(LogScore(log=log, score=score, reasons=reasons))

        return scored

    def get_sampling_summary(self, original_count: int, sampled_count: int) -> dict:
        """Get summary of sampling operation."""
        reduction_percent = (
            ((original_count - sampled_count) / original_count * 100)
            if original_count > 0 else 0
        )

        return {
            "original_count": original_count,
            "sampled_count": sampled_count,
            "reduction_percent": round(reduction_percent, 1),
            "token_savings_estimated": round(reduction_percent * 0.4, 1),  # ~40% per entry
        }

    # ========== Day 3: Enhanced Relevance Scoring ==========

    def configure_incident(
        self,
        timestamp: Optional[datetime],
        alert_message: str = "",
        service: Optional[str] = None,
        severity: Optional[str] = None
    ):
        """
        Configure incident context for relevance scoring (NEW for Day 3).

        Args:
            timestamp: Incident occurrence time
            alert_message: Alert message for keyword extraction
            service: Affected service name
            severity: Incident severity level
        """
        self.incident_timestamp = timestamp or datetime.now(timezone.utc)
        self.incident_keywords = self.keyword_extractor.extract_keywords(
            alert_message
        )
        self.incident_service = service
        self.incident_severity = severity

    def calculate_relevance_score(self, log: Dict) -> RelevanceScore:
        """
        Calculate comprehensive relevance score (NEW for Day 3).

        Factors:
        - Keyword match (0.4 weight)
        - Temporal proximity (0.3 weight)
        - Severity match (0.2 weight)
        - Service relevance (0.1 weight)

        Returns:
            RelevanceScore object with breakdown
        """
        keyword_score = self._calculate_keyword_score(log)
        temporal_score = self._calculate_temporal_score(log)
        severity_score = self._calculate_severity_score(log)
        service_score = self._calculate_service_score(log)

        total_score = (
            keyword_score + temporal_score +
            severity_score + service_score
        )

        return RelevanceScore(
            total_score=round(total_score, 3),
            keyword_score=round(keyword_score, 3),
            temporal_score=round(temporal_score, 3),
            severity_score=round(severity_score, 3),
            service_score=round(service_score, 3)
        )

    def _calculate_keyword_score(self, log: Dict) -> float:
        """Calculate keyword match score (0.4 weight)."""
        if not self.incident_keywords:
            return 0.0

        log_message = log.get('message', '').lower()
        matched = sum(
            1 for kw in self.incident_keywords
            if kw.lower() in log_message
        )

        return (matched / len(self.incident_keywords)) * 0.4

    def _calculate_temporal_score(self, log: Dict) -> float:
        """Calculate temporal proximity score (0.3 weight)."""
        if not self.incident_timestamp:
            return 0.0

        base_score = self._score_temporal_proximity(
            log, self.incident_timestamp
        )
        return base_score * 0.3

    def _calculate_severity_score(self, log: Dict) -> float:
        """Calculate severity match score (0.2 weight)."""
        if not self.incident_severity:
            return 0.0

        log_severity = log.get('severity', 'info').lower()
        incident_severity = self.incident_severity.lower()

        severity_rank = {
            'critical': 5, 'error': 4, 'warning': 3,
            'warn': 3, 'info': 2, 'debug': 1
        }

        log_rank = severity_rank.get(log_severity, 0)
        incident_rank = severity_rank.get(incident_severity, 0)

        if log_rank == incident_rank:
            return 0.2
        elif log_rank > incident_rank:
            return 0.15
        elif log_rank > 0:
            return 0.1
        else:
            return 0.0

    def _calculate_service_score(self, log: Dict) -> float:
        """Calculate service relevance score (0.1 weight)."""
        if not self.incident_service:
            return 0.0

        log_service = log.get('service', '')
        log_namespace = log.get('namespace', '')

        if log_service == self.incident_service:
            return 0.1
        elif log_namespace:
            # Same namespace gets partial credit
            return 0.05

        return 0.0

    def _score_temporal_proximity(
        self,
        log: Dict,
        incident_timestamp: datetime
    ) -> float:
        """
        Score log based on temporal proximity to incident (NEW for Day 3).

        Scoring:
        - Within 5 min:  1.0 score
        - Within 15 min: 0.7 score
        - Within 30 min: 0.4 score
        - Within 1 hour: 0.2 score
        - Beyond 1 hour: 0.1 score
        - Future: 0.0 score
        """
        try:
            log_time_str = log.get('@timestamp', log.get('timestamp', ''))
            if not log_time_str:
                return 0.0

            log_time = datetime.fromisoformat(
                log_time_str.replace('Z', '+00:00')
            ).replace(tzinfo=None)

            incident_time = incident_timestamp.replace(tzinfo=None)

            # Future logs get zero score
            if log_time > incident_time:
                return 0.0

            time_diff = incident_time - log_time

            # Score based on time windows
            if time_diff <= timedelta(minutes=5):
                return 1.0
            elif time_diff <= timedelta(minutes=15):
                return 0.7
            elif time_diff <= timedelta(minutes=30):
                return 0.4
            elif time_diff <= timedelta(hours=1):
                return 0.2
            else:
                return 0.1

        except (ValueError, KeyError):
            return 0.0  # Default score for parsing errors

    def sample_logs_smart(
        self,
        logs: List[Dict],
        incident_config: Dict,
        max_results: int = 50
    ) -> List[Dict]:
        """
        Sample logs using comprehensive relevance scoring (NEW for Day 3).

        Args:
            logs: List of log entries
            incident_config: Incident configuration
                - timestamp: datetime
                - alert_message: str
                - service: str (optional)
                - severity: str (optional)
            max_results: Maximum logs to return

        Returns:
            List of sampled logs with relevance scores
        """
        if not logs:
            return []

        # Configure incident
        self.configure_incident(
            timestamp=incident_config.get('timestamp'),
            alert_message=incident_config.get('alert_message', ''),
            service=incident_config.get('service'),
            severity=incident_config.get('severity')
        )

        # Score all logs
        scored_logs = []
        for log in logs:
            score = self.calculate_relevance_score(log)
            scored_logs.append({
                **log,
                '_relevance_score': score.total_score,
                '_relevance_breakdown': score.to_dict()
            })

        # Sort by relevance score (descending)
        scored_logs.sort(
            key=lambda x: x['_relevance_score'],
            reverse=True
        )

        # Return top results
        return scored_logs[:max_results]

    def sample_apm_errors_smart(
        self,
        apm_errors: List[Dict],
        incident_config: Dict,
        max_results: int = 10
    ) -> List[Dict]:
        """
        Sample APM errors with relevance scoring (NEW for Day 3).

        Consider:
        - Error frequency (more frequent = more important)
        - Keyword matching with alert
        - Impact (transaction count affected)
        - Temporal proximity

        Args:
            apm_errors: List of APM error entries
            incident_config: Incident configuration
            max_results: Maximum errors to return

        Returns:
            List of sampled APM errors with scores
        """
        if not apm_errors:
            return []

        # Configure incident
        self.configure_incident(
            timestamp=incident_config.get('timestamp'),
            alert_message=incident_config.get('alert_message', ''),
            service=incident_config.get('service'),
            severity=incident_config.get('severity')
        )

        scored_errors = []

        for error in apm_errors:
            score = self._calculate_apm_error_score(error)
            scored_errors.append({
                **error,
                '_error_score': score
            })

        # Sort by score (descending)
        scored_errors.sort(
            key=lambda x: x['_error_score'],
            reverse=True
        )

        return scored_errors[:max_results]

    def _calculate_apm_error_score(self, error: Dict) -> float:
        """
        Calculate APM error importance score (NEW for Day 3).

        Factors:
        - Frequency (0-0.4): More frequent = higher score
        - Keyword match (0-0.3): Based on alert keywords
        - Impact (0-0.2): Transactions affected
        - Temporal (0-0.1): Proximity to incident
        """
        score = 0.0

        # 1. Frequency score
        frequency = error.get('occurrences', error.get('count', 0))
        if frequency >= 100:
            score += 0.4
        elif frequency >= 50:
            score += 0.3
        elif frequency >= 10:
            score += 0.2
        elif frequency >= 5:
            score += 0.1

        # 2. Keyword match score
        error_message = error.get('error_message', '').lower()
        transaction_name = error.get('transaction_name', '').lower()

        for keyword in self.incident_keywords:
            if keyword.lower() in error_message:
                score += 0.15
                break

        # Check transaction name too
        for keyword in self.incident_keywords:
            if keyword.lower() in transaction_name:
                score += 0.15
                break

        # Cap keyword score at 0.3
        score = min(score, 0.7)  # 0.4 frequency + 0.3 keyword

        # 3. Impact score (transactions affected)
        transactions = error.get('affected_transactions', 0)
        if transactions >= 1000:
            score += 0.2
        elif transactions >= 500:
            score += 0.15
        elif transactions >= 100:
            score += 0.1
        elif transactions >= 10:
            score += 0.05

        # Cap at 0.9
        score = min(score, 0.9)

        # 4. Temporal score
        error_time = error.get('@timestamp', '')
        if error_time and self.incident_timestamp:
            try:
                error_dt = datetime.fromisoformat(
                    error_time.replace('Z', '+00:00')
                ).replace(tzinfo=None)

                incident_dt = self.incident_timestamp.replace(tzinfo=None)
                time_diff = abs(incident_dt - error_dt)

                if time_diff <= timedelta(minutes=5):
                    score += 0.1
                elif time_diff <= timedelta(minutes=15):
                    score += 0.05
            except Exception:
                pass

        return min(score, 1.0)
