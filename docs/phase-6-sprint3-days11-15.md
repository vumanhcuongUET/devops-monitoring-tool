# Phase 6: Sprint 3 - Days 11-15 Detailed Plans

**Status**: 📋 READY FOR EXECUTION

---

## 📅 Day 11: Relevance Scoring Implementation

### Morning Session (4h)

**Task 1: RelevanceScorer Implementation (2h)**

```python
# backend/app/services/relevance_scorer.py
from typing import List, Dict, Optional
from datetime import datetime, timedelta

class RelevanceScorer:
    """ML-based relevance scoring for logs and data elements."""
    
    def __init__(self, weights: Optional[Dict] = None):
        """
        Initialize scorer with custom weights.
        
        Default weights:
        - keyword_match: 0.4
        - temporal_proximity: 0.3
        - severity_match: 0.2
        - service_relevance: 0.1
        """
        self.weights = weights or {
            'keyword_match': 0.4,
            'temporal_proximity': 0.3,
            'severity_match': 0.2,
            'service_relevance': 0.1
        }
        self.keyword_extractor = KeywordExtractor()
    
    def score_logs(
        self,
        logs: List[Dict],
        incident_type: str,
        alert_message: str,
        alert_keywords: List[str],
        incident_timestamp: datetime,
        incident_severity: Optional[str] = None,
        incident_service: Optional[str] = None
    ) -> List[tuple[Dict, float]]:
        """
        Score logs by relevance to incident.
        
        Args:
            logs: List of log entries
            incident_type: Type of incident
            alert_message: Alert text for keyword extraction
            alert_keywords: Pre-extracted keywords
            incident_timestamp: When incident occurred
            incident_severity: Severity level
            incident_service: Affected service
        
        Returns:
            List of (log, score) tuples, sorted by score descending
        """
        # Extract keywords if not provided
        if not alert_keywords:
            alert_keywords = self.keyword_extractor.extract_keywords(alert_message)
        
        scored_logs = []
        
        for log in logs:
            score = self._calculate_log_score(
                log=log,
                alert_keywords=alert_keywords,
                incident_timestamp=incident_timestamp,
                incident_severity=incident_severity,
                incident_service=incident_service
            )
            
            scored_logs.append((log, score))
        
        # Sort by score descending
        scored_logs.sort(key=lambda x: x[1], reverse=True)
        
        return scored_logs
    
    def _calculate_log_score(
        self,
        log: Dict,
        alert_keywords: List[str],
        incident_timestamp: datetime,
        incident_severity: Optional[str],
        incident_service: Optional[str]
    ) -> float:
        """Calculate comprehensive relevance score."""
        
        score = 0.0
        
        # 1. Keyword matching (40% weight)
        keyword_score = self._calculate_keyword_score(log, alert_keywords)
        score += keyword_score * self.weights['keyword_match']
        
        # 2. Temporal proximity (30% weight)
        temporal_score = self._calculate_temporal_score(log, incident_timestamp)
        score += temporal_score * self.weights['temporal_proximity']
        
        # 3. Severity matching (20% weight)
        if incident_severity:
            severity_score = self._calculate_severity_score(log, incident_severity)
            score += severity_score * self.weights['severity_match']
        
        # 4. Service relevance (10% weight)
        if incident_service:
            service_score = self._calculate_service_score(log, incident_service)
            score += service_score * self.weights['service_relevance']
        
        return min(score, 1.0)  # Cap at 1.0
```

**Task 2: Training & Calibration (2h)**
- Create labeled dataset for training
- Calibrate scoring weights
- Validate against ground truth

### Afternoon Session (4h)

**Task 3: Integration with TokenOptimizer (2h)**
- Integrate RelevanceScorer into optimization flow
- Use scores for log sampling prioritization

**Task 4: Testing (2h)**
- Unit tests for all scoring factors
- Integration tests
- Performance validation

---

## 📅 Day 12: Dynamic Token Budgeting

### Morning Session (4h)

**Task 1: TokenBudgetManager Implementation (2h)**

```python
# backend/app/services/token_budget_manager.py
from enum import Enum
from typing import Dict

class SeverityLevel(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class TokenBudgetManager:
    """Manage token budgets based on severity and complexity."""
    
    BUDGET_MATRIX = {
        SeverityLevel.CRITICAL: 3000,   # Max budget for critical
        SeverityLevel.HIGH: 2500,
        SeverityLevel.MEDIUM: 2000,     # Standard budget
        SeverityLevel.LOW: 1500,
        SeverityLevel.INFO: 1000        # Minimal budget
    }
    
    def __init__(self):
        self.budgets = self.BUDGET_MATRIX.copy()
    
    def get_budget(self, severity: str) -> int:
        """Get base budget for severity level."""
        try:
            level = SeverityLevel(severity.lower())
            return self.budgets[level]
        except ValueError:
            return self.budgets[SeverityLevel.MEDIUM]  # Default to medium
    
    def calculate_complexity(self, incident: Dict) -> float:
        """
        Calculate incident complexity (0.0 to 1.0).
        
        Complexity factors:
        - Number of affected services (0-0.4)
        - Duration of incident (0-0.3)
        - Number of related alerts (0-0.3)
        """
        complexity = 0.0
        
        # 1. Affected services
        services = incident.get('affected_services', [])
        if len(services) > 1:
            complexity += 0.2
        if len(services) > 3:
            complexity += 0.2
        
        # 2. Duration
        duration_hours = incident.get('duration_hours', 0)
        if duration_hours > 2:
            complexity += 0.15
        if duration_hours > 8:
            complexity += 0.15
        
        # 3. Related alerts
        alert_count = incident.get('alert_count', 0)
        if alert_count > 3:
            complexity += 0.15
        if alert_count > 10:
            complexity += 0.15
        
        return min(complexity, 1.0)
    
    def adjust_budget(
        self,
        base_budget: int,
        incident_complexity: float
    ) -> int:
        """
        Adjust budget based on incident complexity.
        
        Formula: base * (1 + complexity * 0.2)
        Max increase: 20%
        """
        multiplier = 1.0 + (incident_complexity * 0.2)
        adjusted = int(base_budget * multiplier)
        
        return adjusted
    
    def get_final_budget(self, incident: Dict) -> int:
        """Get final budget for incident."""
        severity = incident.get('severity', 'medium')
        base = self.get_budget(severity)
        complexity = self.calculate_complexity(incident)
        
        return self.adjust_budget(base, complexity)
```

**Task 2: Budget Enforcement (2h)**
- Implement budget checking
- Add pre-optimization budget calculation
- Add post-optimization validation

### Afternoon Session (4h)

**Task 3: Integration (2h)**
- Integrate into TokenOptimizer
- Update optimization flow

**Task 4: Testing (2h)**
- Unit tests for budget calculation
- Integration tests
- Edge case validation

---

## 📅 Day 13: Context-Aware Prompts

### Morning Session (4h)

**Task 1: ContextAwarePromoter Implementation (2h)**

```python
# backend/app/services/context_aware_promoter.py
from typing import Dict

class ContextAwarePromoter:
    """Generate context-aware prompts for different incident types."""
    
    PROMPT_TEMPLATES = {
        "high_latency": """
Focus on APM metrics and response times.

Key areas to investigate:
- Latency percentiles (p50, p95, p99)
- Slow endpoints and transactions
- Database query performance
- External service calls

Current context shows:
{context_summary}

Please analyze and identify root causes.
""",
        
        "high_error_rate": """
Focus on error patterns and failure rates.

Key areas to investigate:
- Error types and frequencies
- Affected endpoints
- Recent deployments or changes
- Dependency failures

Current error rate: {error_rate}%

Please analyze the error patterns.
""",
        
        "pod_crashloop": """
Focus on Kubernetes pod state and restart patterns.

Key areas to investigate:
- Crash reasons and messages
- Resource limits vs usage
- Recent configuration changes
- Image pull issues

Pod status: {pod_status}

Please identify why the pod is crashing.
""",
        
        "resource_exhaustion": """
Focus on resource utilization and capacity.

Key areas to investigate:
- CPU, memory, disk, network metrics
- Resource limits and requests
- Sudden spikes in usage
- Capacity constraints

Resource levels:
{resource_summary}

Please assess resource exhaustion.
"""
    }
    
    def build_prompt(
        self,
        incident_type: str,
        optimized_data: Dict,
        severity: str
    ) -> str:
        """Build optimized prompt for incident type."""
        template = self.PROMPT_TEMPLATES.get(
            incident_type,
            self.PROMPT_TEMPLATES["high_latency"]  # Default
        )
        
        # Fill in context
        context_summary = self._summarize_context(optimized_data)
        error_rate = optimized_data.get('error_rate', 'N/A')
        pod_status = optimized_data.get('pod_status', 'unknown')
        resource_summary = self._summarize_resources(optimized_data)
        
        return template.format(
            context_summary=context_summary,
            error_rate=error_rate,
            pod_status=pod_status,
            resource_summary=resource_summary
        )
    
    def _summarize_context(self, data: Dict) -> str:
        """Summarize optimized context."""
        summaries = []
        
        if 'anomalies' in data:
            anomalies = data['anomalies']
            if anomalies:
                summaries.append(f"- {len(anomalies)} metric anomalies detected")
        
        if 'logs' in data:
            logs = data['logs']
            if logs:
                summaries.append(f"- {len(logs)} relevant log entries")
        
        return '\n'.join(summaries) if summaries else "No significant anomalies"
```

**Task 2: Prompt Testing (2h)**
- Test each prompt type
- Measure quality differences
- Refine based on results

### Afternoon Session (4h)

**Task 3: Optimization (2h)**
- Remove redundant instructions
- Use concise language
- Focus on relevant sections

**Task 4: Integration (2h)**
- Integrate with LLM client
- Test with real incidents

---

## 📅 Day 14: End-to-End Integration

### Morning Session (4h)

**Task 1: OptimizedTriageGenerator Implementation (2h)**

```python
# backend/app/services/optimized_triage_generator.py
class OptimizedTriageGenerator:
    """Complete optimized triage generation with all intelligent features."""
    
    def __init__(self):
        self.optimizer = TokenOptimizer()
        self.scorer = RelevanceScorer()
        self.budget_manager = TokenBudgetManager()
        self.promoter = ContextAwarePromoter()
        self.validator = AccuracyValidator()
    
    async def generate_triage(
        self,
        incident: Dict,
        request_id: str
    ) -> Dict:
        """
        Complete optimized triage generation flow.
        
        Flow:
        1. Classify incident
        2. Calculate token budget
        3. Collect and optimize context
        4. Build optimized prompt
        5. Generate triage card
        6. Validate quality
        """
        # 1. Classify incident
        incident_type = self._classify_incident(incident)
        severity = incident.get('severity', 'medium')
        
        # 2. Calculate budget
        budget = self.budget_manager.get_final_budget(incident)
        
        # 3. Optimize context
        optimized_context = await self.optimizer.optimize_comprehensive(
            context_data=incident,
            incident_type=incident_type,
            severity=severity,
            request_id=request_id
        )
        
        # Check budget
        if optimized_context.optimized_token_count > budget:
            # Further reduce
            optimized_context = self._reduce_to_budget(
                optimized_context, budget
            )
        
        # 4. Build prompt
        prompt = self.promoter.build_prompt(
            incident_type=incident_type,
            optimized_data=optimized_context.optimized_context,
            severity=severity
        )
        
        # 5. Generate triage
        triage_card = await self._generate_triage_with_prompt(
            prompt, incident
        )
        
        # 6. Validate
        # (Compare with baseline if available)
        
        return triage_card
```

**Task 2: Performance Tuning (2h)**
- Profile end-to-end flow
- Optimize hot paths
- Reduce overhead

### Afternoon Session (4h)

**Task 3: E2E Testing (2h)**
- Test complete flow
- Measure end-to-end metrics
- Validate quality

**Task 4: Documentation (2h)**
- API documentation
- Usage examples
- Integration guide

---

## 📅 Day 15: Sprint 3 Review

### Morning Session (4h)

**Task 1: Sprint Review (2h)**
- Demo all intelligent features
- Review metrics and achievements
- Document lessons learned

**Task 2: Metrics Summary (2h)**
```python
SPRINT_3_METRICS = {
    "token_reduction": 0.70,
    "finding_recall": 0.91,
    "finding_precision": 0.86,
    "processing_time_ms": 2800,
    "relevance_improvement": 0.15
}
```

### Afternoon Session (4h)

**Task 3: Sprint 4 Planning (2h)**
- Review remaining work
- Plan analytics implementation
- Prepare for production rollout

**Task 4: Documentation (2h)**
- Sprint 3 retrospective
- Metrics report
- Sprint 4 plan approved

---

## 📊 Sprint 3 Deliverables Summary

### Code (6 files)
1. `relevance_scorer.py`
2. `token_budget_manager.py`
3. `context_aware_promoter.py`
4. `optimized_triage_generator.py`
5. Unit tests (3 files)

### Configuration (1 file)
1. Enhanced `optimization.yaml`

### Documentation (8 files)
1. Day 11-15 summaries
2. Sprint 3 retrospective
3. Metrics report

---

## ✅ Sprint 3 Success Criteria

- [ ] RelevanceScorer implemented
- [ ] TokenBudgetManager working
- [ ] ContextAwarePromoter functional
- [ ] All components integrated
- [ ] End-to-end flow working
- [ ] Token reduction >70%
- [ ] Finding recall ≥90%
- [ ] Finding precision ≥85%
- [ ] Processing time <3000ms
- [ ] Sprint 3 complete

---

**Document Version**: 1.0  
**Status**: ✅ READY FOR EXECUTION
