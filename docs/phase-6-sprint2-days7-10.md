# Phase 6: Sprint 2 - Days 7-10 Detailed Plans

**Files**: 
- Day 7: `docs/phase-6-day7-detailed-plan.md`
- Day 8: `docs/phase-6-day8-detailed-plan.md`
- Day 9: `docs/phase-6-day9-detailed-plan.md`
- Day 10: `docs/phase-6-day10-detailed-plan.md`

**Status**: 📋 READY FOR EXECUTION

---

## 📅 Day 7: A/B Testing Framework

**Focus**: Build framework for comparing baseline vs optimized

### Morning Session (4h)

**Task 1: ABTester Implementation (2h)**

```python
# backend/app/quality/ab_tester.py
from dataclasses import dataclass
from typing import Dict, Optional
import random
import json
from datetime import datetime

@dataclass
class ABTestResult:
    """Result of a single A/B test."""
    request_id: str
    incident_type: str
    baseline_card: Dict
    optimized_card: Dict
    accuracy_report: Dict
    timestamp: str
    test_group: str  # 'baseline' or 'optimized'

class ABTester:
    """A/B testing framework for optimization validation."""
    
    def __init__(self, test_ratio: float = 0.1):
        """
        Initialize A/B tester.
        
        Args:
            test_ratio: Ratio of requests for A/B testing (0.0-1.0)
        """
        self.test_ratio = test_ratio
        self.validator = AccuracyValidator()
    
    def should_run_ab_test(self) -> bool:
        """Determine if current request should be in A/B test."""
        return random.random() < self.test_ratio
    
    async def run_ab_test(
        self,
        incident: Dict,
        request_id: str
    ) -> ABTestResult:
        """
        Run A/B test for single incident.
        
        Process:
        1. Generate triage with baseline
        2. Generate triage with optimized
        3. Compare using AccuracyValidator
        4. Store results
        
        Args:
            incident: Incident context data
            request_id: Unique request identifier
        
        Returns:
            ABTestResult with comparison
        """
        # Generate baseline triage
        baseline_card = await self._generate_baseline_triage(incident)
        
        # Generate optimized triage
        optimized_card = await self._generate_optimized_triage(incident)
        
        # Compare
        accuracy_report = self.validator.compare_triage_cards(
            baseline_card,
            optimized_card
        )
        
        return ABTestResult(
            request_id=request_id,
            incident_type=incident.get('incident_type', 'unknown'),
            baseline_card=baseline_card,
            optimized_card=optimized_card,
            accuracy_report=accuracy_report.to_dict(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            test_group='both'  # Ran both baseline and optimized
        )
    
    async def _generate_baseline_triage(self, incident: Dict) -> Dict:
        """Generate triage card without optimization."""
        # Use existing LLM client without optimization
        from app.services.llm_client import LLMClient
        client = LLMClient()
        return await client.generate_triage_card(incident, optimize=False)
    
    async def _generate_optimized_triage(self, incident: Dict) -> Dict:
        """Generate triage card with optimization."""
        from app.services.llm_client import LLMClient
        client = LLMClient()
        return await client.generate_triage_card(incident, optimize=True)
```

**Task 2: Statistical Analysis (2h)**

```python
# backend/app/quality/statistical_analysis.py
from scipy import stats
import numpy as np
from typing import List, Dict

def calculate_significance(results: List[ABTestResult]) -> Dict:
    """
    Calculate statistical significance of differences.
    
    Tests:
    - Paired t-test for accuracy metrics
    - Chi-square for categorical agreement
    - Confidence intervals for means
    
    Returns:
        {
            'recall_significant': bool,
            'precision_significant': bool,
            'recall_p_value': float,
            'precision_p_value': float,
            'recall_ci': [float, float],
            'precision_ci': [float, float]
        }
    """
    # Extract metrics
    baseline_recalls = []
    optimized_recalls = []
    baseline_precisions = []
    optimized_precisions = []
    
    for result in results:
        baseline_recalls.append(
            result.accuracy_report['finding_metrics']['recall']
        )
        optimized_recalls.append(
            result.accuracy_report['finding_metrics']['recall']
        )
        # ... same for precision
    
    # Paired t-test for recall
    recall_stat, recall_p = stats.ttest_rel(baseline_recalls, optimized_recalls)
    
    # Paired t-test for precision
    precision_stat, precision_p = stats.ttest_rel(baseline_precisions, optimized_precisions)
    
    # Confidence intervals
    recall_ci = stats.t.interval(0.95, len(baseline_recalls)-1, 
                                 loc=np.mean(baseline_recalls), 
                                 scale=stats.sem(baseline_recalls))
    
    return {
        'recall_significant': recall_p < 0.05,
        'precision_significant': precision_p < 0.05,
        'recall_p_value': recall_p,
        'precision_p_value': precision_p,
        'recall_ci': recall_ci
    }
```

### Afternoon Session (4h)

**Task 3: Dashboard Setup (2h)**
- Create API endpoint for A/B results
- Build real-time statistics display
- Add significance indicators

**Task 4: Integration Testing (2h)**
- Test A/B flow end-to-end
- Verify statistical calculations
- Validate data storage

---

## 📅 Day 8: Baseline Validation

**Focus**: Measure current system performance accurately

### Morning Session (4h)

**Task 1: Run Baseline Tests (2h)**

```python
# backend/tests/quality/test_baseline_validation.py
import pytest
from app.quality.accuracy_validator import AccuracyValidator
from app.quality.test_dataset import TestDataset

class TestBaselineValidation:
    """Validate baseline performance metrics."""
    
    @pytest.fixture
    def validator(self):
        return AccuracyValidator()
    
    @pytest.fixture
    def dataset(self):
        return TestDataset()
    
    @pytest.mark.asyncio
    async def test_baseline_100_incidents(self, validator, dataset):
        """Test 100 incidents for baseline metrics."""
        incidents = dataset.create_50_incident_dataset()
        # Create another 50 for total 100
        incidents.extend(dataset.create_50_incident_dataset())
        
        results = []
        for incident in incidents:
            # Generate baseline triage
            baseline_card = await self._generate_baseline(incident)
            
            # Store result
            results.append({
                'incident_id': incident['incident_id'],
                'incident_type': incident['incident_type'],
                'input_tokens': baseline_card.get('input_tokens', 0),
                'findings_count': len(baseline_card.get('findings', [])),
                'processing_time_ms': baseline_card.get('processing_time_ms', 0)
            })
        
        # Calculate baseline metrics
        BASELINE_REPORT = {
            'sample_size': len(results),
            'avg_input_tokens': sum(r['input_tokens'] for r in results) / len(results),
            'avg_output_tokens': sum(r.get('output_tokens', 0) for r in results) / len(results),
            'avg_cost_per_request': 0.015,
            'avg_processing_time_ms': sum(r['processing_time_ms'] for r in results) / len(results),
            'by_incident_type': self._group_by_type(results),
            'by_severity': self._group_by_severity(results)
        }
        
        # Document baseline
        self._save_baseline_report(BASELINE_REPORT)
```

**Task 2: Document Baseline (2h)**
- Create baseline performance report
- Identify optimization targets
- Define success criteria

### Afternoon Session (4h)

**Task 3: Establish Success Criteria (2h)**

```python
# config/success_criteria.yaml
success_criteria:
  # Primary metrics
  finding_recall:
    baseline: 0.92
    target: 0.90
    minimum: 0.85
  
  finding_precision:
    baseline: 0.88
    target: 0.85
    minimum: 0.80
  
  token_reduction:
    baseline: 0.0
    target: 0.60
    minimum: 0.50
  
  processing_time:
    baseline: 2500  # ms
    target: 3000   # ms
    maximum: 5000  # ms
```

**Task 4: Baseline Report Creation (2h)**
- Comprehensive baseline document
- Charts and visualizations
- Share with stakeholders

---

## 📅 Day 9: Initial A/B Testing

**Focus**: Run first A/B tests with optimization

### Morning Session (4h)

**Task 1: Enable A/B Testing (2h)**

```python
# backend/app/api/v1/analyze.py
@router.post("/analyze")
async def analyze_incident(request: Request, triage_request: TriageCardRequest):
    """Analyze incident with optional A/B testing."""
    
    # Check if should run A/B test
    ab_tester = request.app.state.ab_tester
    if ab_tester.should_run_ab_test():
        # Run both baseline and optimized
        result = await ab_tester.run_ab_test(
            incident=triage_request.dict(),
            request_id=triage_request.request_id
        )
        
        # Store A/B result
        ab_tester.store_result(result)
        
        # Return optimized result to user
        return result.optimized_card
    
    # Normal optimized flow
    # ...
```

**Task 2: Run 50 A/B Tests (2h)**
- Execute 50 test incidents
- Collect comparison metrics
- Store all results

### Afternoon Session (4h)

**Task 3: Analyze Results (2h)**
- Calculate initial statistics
- Compare baseline vs optimized
- Identify patterns

**Task 4: Tune Parameters (2h)**

```python
# Adjust based on A/B test results
TUNING_PARAMETERS = {
    "log_sampling_critical": 5,     # May increase to 7
    "log_sampling_error": 10,        # May decrease to 8
    "anomaly_threshold_cpu": 80,     # May adjust to 75
    "relevance_min_score": 0.3      # May adjust to 0.4
}

# Update config
def update_parameters_based_on_ab_results(results: List[ABTestResult]):
    """Tune parameters based on A/B test analysis."""
    
    # If recall is low, increase sampling quotas
    avg_recall = np.mean([r.accuracy_report['finding_metrics']['recall'] for r in results])
    if avg_recall < 0.90:
        TUNING_PARAMETERS["log_sampling_critical"] = 7
        TUNING_PARAMETERS["log_sampling_error"] = 12
    
    # If precision is low, increase relevance threshold
    avg_precision = np.mean([r.accuracy_report['finding_metrics']['precision'] for r in results])
    if avg_precision < 0.85:
        TUNING_PARAMETERS["relevance_min_score"] = 0.4
```

---

## 📅 Day 10: Quality Gates Validation

**Focus**: Ensure quality standards are met

### Morning Session (4h)

**Task 1: Quality Validation Setup (1h)**

```python
# backend/app/quality/quality_gates.py
class QualityGateValidator:
    """Validate all quality gates."""
    
    QUALITY_GATES = {
        "finding_recall_min": 0.90,
        "finding_precision_min": 0.85,
        "severity_accuracy_min": 0.95,
        "token_reduction_min": 0.50,
        "processing_time_max_ms": 3000
    }
    
    def validate_gates(self, metrics: Dict) -> Dict:
        """
        Validate all quality gates.
        
        Returns:
            {
                'all_passed': bool,
                'passed_gates': list,
                'failed_gates': list,
                'details': dict
            }
        """
        results = {
            'all_passed': True,
            'passed_gates': [],
            'failed_gates': [],
            'details': {}
        }
        
        for gate, threshold in self.QUALITY_GATES.items():
            metric_value = metrics.get(gate, 0)
            
            if 'max' in gate:
                passed = metric_value <= threshold
            else:
                passed = metric_value >= threshold
            
            results['details'][gate] = {
                'threshold': threshold,
                'actual': metric_value,
                'passed': passed
            }
            
            if passed:
                results['passed_gates'].append(gate)
            else:
                results['failed_gates'].append(gate)
                results['all_passed'] = False
        
        return results
```

**Task 2: Run 100 Incident Tests (3h)**
- Test 100 diverse incidents
- Collect all metrics
- Run quality gate validation

### Afternoon Session (4h)

**Task 3: Fix Failed Gates (2h)**
- Address any failed gates
- Re-test until all pass
- Document fixes

**Task 4: Sprint 2 Review (2h)**
- Quality validation report
- Sprint 2 retrospective
- Sprint 3 preparation

---

## 📊 Sprint 2 Deliverables Summary

### Code (8 files)
- `accuracy_validator.py`
- `finding_comparator.py`
- `ab_tester.py`
- `statistical_analysis.py`
- `quality_gates.py`
- `test_dataset.py`
- Unit tests (2 files)

### Data
- 50 labeled test incidents
- 100 baseline test results
- 50 A/B test results
- Quality validation dataset

### Documentation (10 files)
- Day 6-10 detailed plans
- Day 6-10 summaries
- Sprint 2 retrospective
- Baseline validation report
- A/B testing results
- Quality validation report

---

## ✅ Sprint 2 Success Criteria

- [ ] AccuracyValidator functional
- [ ] ABTester functional
- [ ] 50 A/B tests completed
- [ ] Baseline documented
- [ ] All quality gates passing
- [ ] Finding recall ≥90%
- [ ] Finding precision ≥85%
- [ ] No accuracy regression
- [ ] Parameters tuned based on data
- [ ] Sprint 2 documentation complete

---

**Document Version**: 1.0  
**Status**: ✅ READY FOR EXECUTION
