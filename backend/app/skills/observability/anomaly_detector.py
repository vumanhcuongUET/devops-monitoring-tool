"""Observability Anomaly Detector Skill — real Prometheus series (Phase 13).

Was a stub: the time series was numpy-seeded mock data and "correlated
events" were fabricated. Now the series comes from a real range query over
the injected Prometheus client; statistical detection (z-score, IQR) runs on
whatever the metrics source actually returned.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillConfig,
    SkillPriority,
)

logger = logging.getLogger(__name__)

SENSITIVITY_THRESHOLDS = {
    "low": {"z_score": 4.0, "iqr_multiplier": 3.0},
    "medium": {"z_score": 3.0, "iqr_multiplier": 1.5},
    "high": {"z_score": 2.0, "iqr_multiplier": 1.0},
}


class AnomalyDetectorSkill(BaseSkill):
    """Detect anomalies in a real Prometheus time series (z-score + IQR)."""

    skill_id = "observability_anomaly_detector"
    name = "Observability Anomaly Detector"
    description = (
        "Detect anomalies in a live Prometheus time series using z-score and "
        "IQR statistics, with spike/drop/drift pattern analysis."
    )
    category = SkillCategory.OBSERVABILITY
    priority = SkillPriority.HIGH
    version = "2.0.0"

    def __init__(self, config: SkillConfig | None = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        try:
            expression = parameters.get("expression") or parameters.get("metric")
            if not expression:
                raise ValueError("Parameter 'expression' (PromQL) or 'metric' is required")

            hours = max(int(parameters.get("time_window_hours", 24)), 1)
            sensitivity = parameters.get("sensitivity", "medium")
            thresholds = SENSITIVITY_THRESHOLDS[sensitivity]

            prom = ((context or {}).get("clients") or {}).get("prometheus")
            if prom is None:
                raise RuntimeError(
                    "No Prometheus client in context['clients']['prometheus'] — "
                    "skill requires a live metrics source"
                )

            # A bare metric name is valid PromQL; richer expressions are used
            # as-is so callers can pre-aggregate.
            end = datetime.now(timezone.utc)
            start = end - timedelta(hours=hours)
            step = f"{max(hours * 60 // 240, 1)}m"
            rows = await prom.query_range(expression, str(start.timestamp()), str(end.timestamp()), step)

            series = self._series_average_per_timestamp(rows)
            if len(series) < 4:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=[
                        f"Insufficient data for {expression!r}: got {len(series)} points "
                        f"over {hours}h"
                    ],
                    metadata={"project": project, "expression": expression},
                )

            anomalies = self._detect_z_score(series, thresholds["z_score"])
            anomalies += self._detect_iqr(series, thresholds["iqr_multiplier"])
            patterns = self._analyze_patterns(series)
            severity = self._severity(anomalies)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9 if len(series) > 50 else 0.7,
                data={
                    "expression": expression,
                    "time_window_hours": hours,
                    "points": len(series),
                    "statistics": {
                        "mean": round(float(np.mean(series)), 4),
                        "std": round(float(np.std(series)), 4),
                        "min": round(float(np.min(series)), 4),
                        "max": round(float(np.max(series)), 4),
                    },
                    "anomalies": anomalies,
                    "pattern_analysis": patterns,
                    "severity": severity,
                },
                warnings=[f"{len(anomalies)} anomalies detected in {hours}h window"]
                if anomalies
                else [],
                metadata={"project": project, "sensitivity": sensitivity, "step": step},
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Anomaly detection failed: {e!s}"],
            )

    def _series_average_per_timestamp(self, rows: list[dict[str, Any]]) -> list[float]:
        """Average a range-query result across series per timestamp."""
        per_ts: dict[int, list[float]] = {}
        for row in rows or []:
            for point in row.get("values", []):
                try:
                    per_ts.setdefault(int(float(point[0])), []).append(float(point[1]))
                except (TypeError, ValueError, IndexError):
                    continue
        return [round(sum(v) / len(v), 4) for _, v in sorted(per_ts.items())]

    def _detect_z_score(self, series: list[float], threshold: float) -> list[dict[str, Any]]:
        values = np.array(series)
        std = float(np.std(values))
        if std == 0:
            return []
        z_scores = np.abs((values - np.mean(values)) / std)
        return [
            {
                "index": int(i),
                "value": round(float(values[i]), 4),
                "z_score": round(float(z), 3),
                "method": "z_score",
                "severity": "high" if z > threshold * 1.5 else "medium",
            }
            for i, z in enumerate(z_scores)
            if z > threshold
        ]

    def _detect_iqr(self, series: list[float], multiplier: float) -> list[dict[str, Any]]:
        values = np.array(series)
        q1, q3 = np.percentile(values, [25, 75])
        iqr = float(q3 - q1)
        if iqr == 0:
            return []
        lower, upper = q1 - multiplier * iqr, q3 + multiplier * iqr
        median = float(np.median(values))
        return [
            {
                "index": int(i),
                "value": round(float(v), 4),
                "method": "iqr",
                "bounds": {"lower": round(float(lower), 4), "upper": round(float(upper), 4)},
                "severity": "high" if abs(float(v) - median) > 2 * iqr else "medium",
            }
            for i, v in enumerate(values)
            if v < lower or v > upper
        ]

    def _analyze_patterns(self, series: list[float]) -> dict[str, Any]:
        values = np.array(series)
        median = float(np.median(values))
        spikes = int(np.sum(values > 2 * median)) if median > 0 else 0
        drops = int(np.sum(values < 0.5 * median)) if median > 0 else 0
        slope = float(np.polyfit(np.arange(len(values)), values, 1)[0]) if len(values) > 10 else 0.0
        span = float(np.max(values) - np.min(values))
        return {
            "has_sudden_spikes": spikes > 0,
            "spike_count": spikes,
            "has_sudden_drops": drops > 0,
            "drop_count": drops,
            "has_slow_drift": abs(slope) > 0.1 * max(span, 1.0),
            "slope_per_point": round(slope, 6),
        }

    def _severity(self, anomalies: list[dict[str, Any]]) -> dict[str, Any]:
        high = sum(1 for a in anomalies if a["severity"] == "high")
        total = len(anomalies)
        if high > total / 2 or total > 10:
            overall = "critical"
        elif high > 0 or total > 5:
            overall = "high"
        elif total > 2:
            overall = "medium"
        else:
            overall = "low"
        return {
            "total_anomalies": total,
            "high_severity_count": high,
            "overall_severity": overall if total else "none",
        }

    async def get_recommendations(
        self, analysis_id: str, project: str
    ) -> list[Recommendation]:
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        data = result.data
        recommendations = []
        severity = data.get("severity", {})
        if severity.get("overall_severity") in ("high", "critical"):
            recommendations.append(Recommendation(
                title=f"{severity.get('overall_severity').title()} anomalies in {data['expression']}",
                description=(
                    f"{severity.get('total_anomalies')} anomalies "
                    f"({severity.get('high_severity_count')} high severity) over "
                    f"{data['time_window_hours']}h."
                ),
                priority=SkillPriority.HIGH,
                action_type="investigate",
                risk_level="high",
            ))

        patterns = data.get("pattern_analysis", {})
        if patterns.get("has_slow_drift"):
            recommendations.append(Recommendation(
                title="Slow drift detected",
                description=(
                    "The series trends steadily over the window — check for "
                    "resource exhaustion, leaks, or organic growth needing capacity."
                ),
                priority=SkillPriority.MEDIUM,
                action_type="monitor",
                risk_level="medium",
            ))
        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        errors = []
        if not (parameters.get("expression") or parameters.get("metric")):
            errors.append("Parameter 'expression' (PromQL) or 'metric' is required")
        hours = parameters.get("time_window_hours", 24)
        if not isinstance(hours, (int, float)) or hours <= 0:
            errors.append("time_window_hours must be a positive number")
        if parameters.get("sensitivity", "medium") not in SENSITIVITY_THRESHOLDS:
            errors.append("sensitivity must be one of: low, medium, high")
        return len(errors) == 0, errors
