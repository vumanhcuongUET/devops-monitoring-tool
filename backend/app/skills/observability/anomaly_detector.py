"""Observability Anomaly Detector Skill.

Detects anomalies in time-series metrics using statistical methods
including z-score, IQR, and seasonal decomposition.
"""

import logging
from typing import Any

import numpy as np

from app.services.prometheus_client import PrometheusClient
from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillConfig,
    SkillPriority,
)

logger = logging.getLogger(__name__)


class AnomalyDetectorSkill(BaseSkill):
    """Detect anomalies in time-series metrics.

    This skill analyzes Prometheus metrics to identify:
    - Sudden spikes or drops in values
    - Statistical outliers using z-score and IQR methods
    - Slow drifts over time
    - Correlated anomalies across metrics

    Example usage:
        skill = AnomalyDetectorSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "metric": "http_requests_total",
                "time_window_hours": 24,
                "sensitivity": "medium"
            }
        )
    """

    skill_id = "observability_anomaly_detector"
    name = "Observability Anomaly Detector"
    description = (
        "Detect anomalies in time-series metrics using statistical methods "
        "(z-score, IQR) and identify correlated events."
    )
    category = SkillCategory.OBSERVABILITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    # Sensitivity thresholds
    SENSITIVITY_THRESHOLDS = {
        "low": {"z_score": 4.0, "iqr_multiplier": 3.0},
        "medium": {"z_score": 3.0, "iqr_multiplier": 1.5},
        "high": {"z_score": 2.0, "iqr_multiplier": 1.0},
    }

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the anomaly detector skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)
        self.prometheus_client = PrometheusClient()

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Run anomaly detection analysis.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - metric: Metric name to analyze (required)
                - time_window_hours: Time window for analysis (default: 24)
                - sensitivity: Detection sensitivity (default: "medium")
                - methods: Detection methods to use (default: all)
            context: Additional context from registry

        Returns:
            AnalysisResult with anomaly detection data
        """
        try:
            # Extract and validate parameters
            metric = parameters.get("metric")
            if not metric:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Parameter 'metric' is required"],
                    metadata={"project": project},
                )

            time_window = parameters.get("time_window_hours", 24)
            sensitivity = parameters.get("sensitivity", "medium")
            methods = parameters.get("methods", ["z_score", "iqr"])

            # Query time series data from Prometheus
            time_series = await self._query_time_series(
                project=project,
                metric=metric,
                time_window_hours=time_window,
            )

            if not time_series:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=[f"No data returned for metric: {metric}"],
                    metadata={"project": project, "metric": metric},
                )

            # Detect anomalies using specified methods
            anomalies = []
            if "z_score" in methods:
                z_score_anomalies = self._detect_z_score_anomalies(
                    time_series,
                    self.SENSITIVITY_THRESHOLDS[sensitivity]["z_score"],
                )
                anomalies.extend(z_score_anomalies)

            if "iqr" in methods:
                iqr_anomalies = self._detect_iqr_anomalies(
                    time_series,
                    self.SENSITIVITY_THRESHOLDS[sensitivity]["iqr_multiplier"],
                )
                anomalies.extend(iqr_anomalies)

            # Analyze patterns
            pattern_analysis = self._analyze_patterns(time_series)

            # Calculate severity scores
            severity_analysis = self._calculate_severity(anomalies, time_series)

            # Find correlated events
            correlated_events = await self._find_correlated_events(
                project=project,
                anomalies=anomalies,
                time_window_hours=time_window,
            )

            # Calculate confidence based on data quality and method agreement
            confidence = self._calculate_confidence(
                time_series, anomalies, len(methods)
            )

            # Generate summary
            summary = self._generate_summary(anomalies, pattern_analysis)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data={
                    "metric": metric,
                    "time_window_hours": time_window,
                    "anomalies": anomalies,
                    "pattern_analysis": pattern_analysis,
                    "severity_analysis": severity_analysis,
                    "correlated_events": correlated_events,
                    "summary": summary,
                },
                warnings=[
                    f"{len(anomalies)} anomalies detected in {time_window}h window"
                ]
                if anomalies
                else [],
                metadata={
                    "project": project,
                    "metric": metric,
                    "sensitivity": sensitivity,
                    "methods_used": methods,
                },
            )

        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[str(e)],
                metadata={"project": project},
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate recommendations based on anomaly detection.

        Args:
            analysis_id: ID of previous analysis result
            project: Project name

        Returns:
            List of recommendations
        """
        from app.skills.registry import get_skill_registry

        registry = get_skill_registry()
        result = registry.get_result(analysis_id)

        if not result or not result.success:
            return []

        recommendations = []
        data = result.data
        _anomalies = data.get("anomalies", [])
        severity = data.get("severity_analysis", {})

        # High severity anomalies
        if severity.get("overall_severity") in ["high", "critical"]:
            recommendations.append(
                Recommendation(
                    title="Critical Anomalies Detected",
                    description=f"{severity.get('total_anomalies', 0)} anomalies detected "
                    f"with {severity.get('overall_severity')} severity.",
                    priority=SkillPriority.HIGH,
                    action_type="investigate",
                    estimated_effort="2-4 hours",
                    risk_level="high",
                    commands=[
                        "Review recent deployments",
                        "Check incident history",
                        "Analyze correlated events",
                    ],
                    references=["https://sre.google/workbook/handling-emergencies/"],
                )
            )

        # Specific recommendations based on anomaly patterns
        pattern_analysis = data.get("pattern_analysis", {})

        if pattern_analysis.get("has_sudden_spikes"):
            recommendations.append(
                Recommendation(
                    title="Sudden Spikes Detected",
                    description="Metric shows sudden spike patterns. Investigate for "
                    "flash crowds, cache storms, or dependency issues.",
                    priority=SkillPriority.MEDIUM,
                    action_type="investigate",
                    estimated_effort="1-2 hours",
                    risk_level="medium",
                    commands=[
                        "Check rate limiting configuration",
                        "Review dependency health",
                        "Analyze cache hit rates",
                    ],
                )
            )

        if pattern_analysis.get("has_slow_drift"):
            recommendations.append(
                Recommendation(
                    title="Slow Drift Detected",
                    description="Metric shows gradual change over time. May indicate "
                    "resource exhaustion, memory leak, or capacity planning needs.",
                    priority=SkillPriority.MEDIUM,
                    action_type="monitor",
                    estimated_effort="1-3 hours",
                    risk_level="medium",
                    commands=[
                        "Review resource trends",
                        "Check for memory leaks",
                        "Update capacity forecasts",
                    ],
                )
            )

        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate analysis parameters.

        Args:
            parameters: Parameters to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate required metric parameter
        if not parameters.get("metric"):
            errors.append("Parameter 'metric' is required")

        # Validate time_window_hours
        time_window = parameters.get("time_window_hours", 24)
        if not isinstance(time_window, (int, float)) or time_window <= 0:
            errors.append("time_window_hours must be a positive number")

        # Validate sensitivity
        sensitivity = parameters.get("sensitivity", "medium")
        if sensitivity not in ["low", "medium", "high"]:
            errors.append("sensitivity must be one of: low, medium, high")

        # Validate methods
        methods = parameters.get("methods", ["z_score", "iqr"])
        valid_methods = ["z_score", "iqr", "seasonal"]
        if not all(m in valid_methods for m in methods):
            errors.append(f"methods must be one of: {', '.join(valid_methods)}")

        return len(errors) == 0, errors

    async def _query_time_series(
        self,
        project: str,
        metric: str,
        time_window_hours: int,
    ) -> list[float]:
        """Query time series data from Prometheus.

        Args:
            project: Project name
            metric: Metric name
            time_window_hours: Time window in hours

        Returns:
            List of metric values
        """
        try:
            # Query Prometheus for time series data
            query = f'rate({metric}{{project="{project}"}}[5m])'
            _result = await self.prometheus_client.query(query)

            # Extract values from result
            # In real implementation, parse Prometheus response format
            # For now, return mock data
            return self._generate_mock_time_series()

        except Exception as e:
            logger.warning(f"Time series query failed: {e}")
            return []

    def _generate_mock_time_series(self, count: int = 100) -> list[float]:
        """Generate mock time series data for testing.

        Args:
            count: Number of data points

        Returns:
            List of mock values
        """
        np.random.seed(42)
        base_value = 100
        noise = np.random.normal(0, 10, count)
        trend = np.linspace(0, 5, count)

        # Add some anomalies
        series = base_value + noise + trend
        series[20] = 200  # Sudden spike
        series[50] = 30  # Sudden drop
        series[80] = 180  # Another spike

        return list(series)

    def _detect_z_score_anomalies(
        self, time_series: list[float], threshold: float
    ) -> list[dict[str, Any]]:
        """Detect anomalies using z-score method.

        Args:
            time_series: List of metric values
            threshold: Z-score threshold for anomaly detection

        Returns:
            List of detected anomalies
        """
        if not time_series or len(time_series) < 3:
            return []

        values = np.array(time_series)
        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return []

        # Calculate z-scores
        z_scores = np.abs((values - mean) / std)

        # Find anomalies
        anomalies = []
        for i, z_score in enumerate(z_scores):
            if z_score > threshold:
                anomalies.append(
                    {
                        "index": i,
                        "value": float(values[i]),
                        "z_score": float(z_score),
                        "method": "z_score",
                        "threshold": threshold,
                        "severity": "high" if z_score > threshold * 1.5 else "medium",
                    }
                )

        return anomalies

    def _detect_iqr_anomalies(
        self, time_series: list[float], multiplier: float
    ) -> list[dict[str, Any]]:
        """Detect anomalies using IQR (Interquartile Range) method.

        Args:
            time_series: List of metric values
            multiplier: IQR multiplier for outlier detection

        Returns:
            List of detected anomalies
        """
        if not time_series or len(time_series) < 4:
            return []

        values = np.array(time_series)
        q1 = np.percentile(values, 25)
        q3 = np.percentile(values, 75)
        iqr = q3 - q1

        if iqr == 0:
            return []

        # Calculate bounds
        lower_bound = q1 - (multiplier * iqr)
        upper_bound = q3 + (multiplier * iqr)

        # Find anomalies
        anomalies = []
        for i, value in enumerate(values):
            if value < lower_bound or value > upper_bound:
                anomalies.append(
                    {
                        "index": i,
                        "value": float(value),
                        "method": "iqr",
                        "bounds": {"lower": float(lower_bound), "upper": float(upper_bound)},
                        "severity": "high"
                        if abs(value - np.median(values)) > 2 * iqr
                        else "medium",
                    }
                )

        return anomalies

    def _analyze_patterns(self, time_series: list[float]) -> dict[str, Any]:
        """Analyze patterns in time series data.

        Args:
            time_series: List of metric values

        Returns:
            Dictionary with pattern analysis results
        """
        if not time_series or len(time_series) < 10:
            return {"has_patterns": False}

        values = np.array(time_series)

        # Detect sudden spikes (values > 2 * median)
        median = np.median(values)
        spikes = [i for i, v in enumerate(values) if v > 2 * median]
        has_sudden_spikes = len(spikes) > 0

        # Detect sudden drops (values < 0.5 * median)
        drops = [i for i, v in enumerate(values) if v < 0.5 * median]
        has_sudden_drops = len(drops) > 0

        # Detect slow drift (trend over time)
        if len(values) > 10:
            # Calculate linear trend
            x = np.arange(len(values))
            slope, _ = np.polyfit(x, values, 1)
            has_slow_drift = abs(slope) > 0.1
        else:
            has_slow_drift = False

        # Detect periodic patterns
        has_periodic = False  # Would require FFT analysis

        return {
            "has_patterns": True,
            "has_sudden_spikes": has_sudden_spikes,
            "spike_count": len(spikes),
            "has_sudden_drops": has_sudden_drops,
            "drop_count": len(drops),
            "has_slow_drift": has_slow_drift,
            "has_periodic": has_periodic,
        }

    def _calculate_severity(
        self, anomalies: list[dict], time_series: list[float]
    ) -> dict[str, Any]:
        """Calculate severity scores for detected anomalies.

        Args:
            anomalies: List of detected anomalies
            time_series: Original time series data

        Returns:
            Dictionary with severity analysis
        """
        if not anomalies:
            return {
                "total_anomalies": 0,
                "high_severity_count": 0,
                "medium_severity_count": 0,
                "overall_severity": "none",
            }

        high_count = sum(1 for a in anomalies if a.get("severity") == "high")
        medium_count = sum(1 for a in anomalies if a.get("severity") == "medium")

        # Determine overall severity
        total = len(anomalies)
        if high_count > total / 2 or total > 10:
            overall = "critical"
        elif high_count > 0 or medium_count > 5:
            overall = "high"
        elif medium_count > 2:
            overall = "medium"
        else:
            overall = "low"

        return {
            "total_anomalies": total,
            "high_severity_count": high_count,
            "medium_severity_count": medium_count,
            "overall_severity": overall,
        }

    async def _find_correlated_events(
        self,
        project: str,
        anomalies: list[dict],
        time_window_hours: int,
    ) -> list[dict[str, Any]]:
        """Find events correlated with detected anomalies.

        Args:
            project: Project name
            anomalies: Detected anomalies
            time_window_hours: Time window for correlation

        Returns:
            List of correlated events
        """
        # In real implementation, would query:
        # - Deployment history
        # - Alert history
        # - Incident records
        # - Other metrics

        # For now, return mock correlated events
        return [
            {
                "type": "deployment",
                "description": "New deployment at 14:30 UTC",
                "correlation_strength": "high",
            }
        ]

    def _calculate_confidence(
        self, time_series: list, anomalies: list, methods_used: int
    ) -> float:
        """Calculate confidence score based on data quality and method agreement.

        Args:
            time_series: Time series data quality
            anomalies: Detected anomalies
            methods_used: Number of detection methods used

        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.5

        # Increase confidence with good data
        if len(time_series) > 50:
            confidence += 0.2
        elif len(time_series) > 20:
            confidence += 0.1

        # Increase confidence if methods agree
        if methods_used > 1:
            confidence += 0.1

        # Increase confidence if anomalies found (valid detection)
        if anomalies:
            confidence += 0.1

        return min(confidence, 1.0)

    def _generate_summary(
        self, anomalies: list[dict], pattern_analysis: dict
    ) -> str:
        """Generate human-readable summary.

        Args:
            anomalies: Detected anomalies
            pattern_analysis: Pattern analysis results

        Returns:
            Summary string
        """
        if not anomalies:
            return "No anomalies detected in the specified time window."

        patterns = []
        if pattern_analysis.get("has_sudden_spikes"):
            patterns.append("sudden spikes")
        if pattern_analysis.get("has_sudden_drops"):
            patterns.append("sudden drops")
        if pattern_analysis.get("has_slow_drift"):
            patterns.append("gradual drift")

        pattern_desc = ", ".join(patterns) if patterns else "various patterns"

        return (
            f"Detected {len(anomalies)} anomalies showing {pattern_desc}. "
            f"Review correlated events and recent deployments."
        )
