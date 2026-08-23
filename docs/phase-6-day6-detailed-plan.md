# Phase 6: Sprint 2 - Day 6 Detailed Implementation Plan

**Date**: Day 6 of Sprint 2  
**Focus**: Accuracy Validator Implementation  
**Duration**: 8 hours  
**Status**: 📋 READY FOR EXECUTION

---

## 📋 Day 6 Objectives

### Primary Goals
1. ✅ Implement AccuracyValidator class
2. ✅ Define accuracy metrics (recall, precision, severity)
3. ✅ Create test dataset with 50 labeled incidents
4. ✅ Implement finding comparison logic
5. ✅ Build ground truth validation

### Success Metrics
| Metric | Target | How to Measure |
|--------|--------|----------------|
| AccuracyValidator | Functional | Unit tests |
| Finding Comparison | Correct logic | Unit tests |
| Test Dataset | 50 incidents | File count |
| Metrics Calculation | Accurate | Validation |
| Ground Truth | Validated | Review |

---

## 🌅 Morning Session (4 Hours)

### Task 1: Accuracy Metrics Definition (1.5h)

**File**: `backend/app/quality/accuracy_metrics.py`

```python
from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum

class Severity(Enum):
    """Severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

@dataclass
class Finding:
    """A single finding from triage card."""
    id: str
    description: str
    severity: str
    category: str
    confidence: float
    root_cause: bool
    actionable: bool

@dataclass
class AccuracyReport:
    """Comprehensive accuracy report."""
    # Finding metrics
    finding_recall: float           # TP / (TP + FN)
    finding_precision: float        # TP / (TP + FP)
    finding_f1: float              # 2 * (precision * recall) / (precision + recall)
    
    # Severity metrics
    severity_accuracy: float        # Correct severity / total
    severity_recall_by_level: Dict[str, float]
    
    # Root cause metrics
    root_cause_recall: float       # Root causes identified / total root causes
    root_cause_precision: float     # Actual root causes / predicted root causes
    
    # Recommendation metrics
    recommendation_relevance: float # Actionable / total recommendations
    recommendation_coverage: float  # Issues with recommendations / total issues
    
    # Token metrics
    token_savings: float
    token_reduction_pct: float
    
    # Performance metrics
    processing_time_ms: float
    
    # Sample sizes
    baseline_findings_count: int
    optimized_findings_count: int
    ground_truth_findings_count: int
    
    # Detailed comparison
    true_positives: List[str]       # Finding IDs
    false_positives: List[str]      # Finding IDs
    false_negatives: List[str]      # Finding IDs
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'finding_metrics': {
                'recall': self.finding_recall,
                'precision': self.finding_precision,
                'f1': self.finding_f1
            },
            'severity_metrics': {
                'accuracy': self.severity_accuracy,
                'recall_by_level': self.severity_recall_by_level
            },
            'root_cause_metrics': {
                'recall': self.root_cause_recall,
                'precision': self.root_cause_precision
            },
            'recommendation_metrics': {
                'relevance': self.recommendation_relevance,
                'coverage': self.recommendation_coverage
            },
            'token_metrics': {
                'savings': self.token_savings,
                'reduction_pct': self.token_reduction_pct
            },
            'performance': {
                'processing_time_ms': self.processing_time_ms
            },
            'sample_sizes': {
                'baseline': self.baseline_findings_count,
                'optimized': self.optimized_findings_count,
                'ground_truth': self.ground_truth_findings_count
            },
            'confusion_matrix': {
                'true_positives': self.true_positives,
                'false_positives': self.false_positives,
                'false_negatives': self.false_negatives
            }
        }
```

**Acceptance Criteria**:
- [ ] All metrics defined
- [ ] Data classes functional
- [ ] Serialization works
- [ ] Types validated

---

### Task 2: Finding Comparison Logic (1.5h)

**File**: `backend/app/quality/finding_comparator.py`

```python
from difflib import SequenceMatcher
from typing import List, Set, Tuple
import re

class FindingComparator:
    """Compare findings between triage cards."""
    
    def __init__(self, similarity_threshold: float = 0.8):
        """
        Initialize comparator.
        
        Args:
            similarity_threshold: Minimum similarity for match (0.0-1.0)
        """
        self.similarity_threshold = similarity_threshold
    
    def compare_findings(
        self,
        baseline_findings: List[Finding],
        optimized_findings: List[Finding],
        ground_truth: Optional[List[Finding]] = None
    ) -> Tuple[Set[str], Set[str], Set[str]]:
        """
        Compare findings and calculate TP, FP, FN.
        
        Args:
            baseline_findings: Findings from baseline (non-optimized)
            optimized_findings: Findings from optimized
            ground_truth: Known correct findings (optional)
        
        Returns:
            (true_positives, false_positives, false_negatives) as sets of finding IDs
        """
        baseline_ids = {f.id for f in baseline_findings}
        optimized_ids = {f.id for f in optimized_findings}
        
        # If no ground truth, use baseline as reference
        if ground_truth is None:
            reference_ids = baseline_ids
            reference_findings = baseline_findings
        else:
            reference_ids = {f.id for f in ground_truth}
            reference_findings = ground_truth
        
        # Match findings by description similarity
        true_positives = set()
        false_positives = set()
        false_negatives = set()
        
        matched_baseline = set()
        matched_optimized = set()
        
        # Find true positives (findings in both reference and optimized)
        for ref_finding in reference_findings:
            for opt_finding in optimized_findings:
                if (ref_finding.id not in matched_baseline and 
                    opt_finding.id not in matched_optimized):
                    
                    if self._findings_match(ref_finding, opt_finding):
                        true_positives.add(ref_finding.id)
                        matched_baseline.add(ref_finding.id)
                        matched_optimized.add(opt_finding.id)
                        break
        
        # False negatives (in reference but not in optimized)
        for ref_finding in reference_findings:
            if ref_finding.id not in matched_baseline:
                false_negatives.add(ref_finding.id)
        
        # False positives (in optimized but not in reference)
        for opt_finding in optimized_findings:
            if opt_finding.id not in matched_optimized:
                false_positives.add(opt_finding.id)
        
        return true_positives, false_positives, false_negatives
    
    def _findings_match(self, f1: Finding, f2: Finding) -> bool:
        """
        Check if two findings match.
        
        Match criteria:
        1. Same category
        2. Similar description (above threshold)
        3. Compatible severity (within 1 level)
        """
        # Check category
        if f1.category != f2.category:
            return False
        
        # Check severity compatibility
        if not self._severity_compatible(f1.severity, f2.severity):
            return False
        
        # Check description similarity
        desc_similarity = self._text_similarity(
            f1.description.lower(),
            f2.description.lower()
        )
        
        return desc_similarity >= self.similarity_threshold
    
    def _severity_compatible(self, sev1: str, sev2: str) -> bool:
        """Check if severities are compatible (within 1 level)."""
        severity_rank = {
            'critical': 5,
            'high': 4,
            'medium': 3,
            'low': 2,
            'info': 1
        }
        
        rank1 = severity_rank.get(sev1.lower(), 3)
        rank2 = severity_rank.get(sev2.lower(), 3)
        
        return abs(rank1 - rank2) <= 1
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using SequenceMatcher."""
        return SequenceMatcher(None, text1, text2).ratio()
    
    def calculate_similarity_score(
        self,
        baseline_findings: List[Finding],
        optimized_findings: List[Finding]
    ) -> float:
        """
        Calculate overall similarity score between two sets of findings.
        
        Returns:
            Float between 0.0 (no match) and 1.0 (perfect match)
        """
        if not baseline_findings and not optimized_findings:
            return 1.0  # Both empty = perfect match
        
        if not baseline_findings or not optimized_findings:
            return 0.0  # One empty = no match
        
        tp, fp, fn = self.compare_findings(
            baseline_findings,
            optimized_findings
        )
        
        # Calculate Jaccard similarity
        intersection = len(tp)
        union = len(tp) + len(fp) + len(fn)
        
        return intersection / union if union > 0 else 0.0
```

**Acceptance Criteria**:
- [ ] TP/FP/FN calculated correctly
- [ ] Similarity threshold configurable
- [ ] Severity compatibility works
- [ ] Text similarity functional

---

### Task 3: Test Dataset Creation (1h)

**File**: `backend/app/quality/test_dataset.py`

```python
from typing import List, Dict, Optional
from datetime import datetime
import json
from pathlib import Path

class TestDataset:
    """Create and manage test dataset for validation."""
    
    def __init__(self, storage_path: str = "data/test_dataset.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    def create_labeled_incident(
        self,
        incident_id: str,
        incident_type: str,
        severity: str,
        description: str,
        ground_truth_findings: List[Dict],
        context_data: Dict
    ) -> Dict:
        """
        Create a labeled incident for testing.
        
        Args:
            incident_id: Unique identifier
            incident_type: Type of incident
            severity: Severity level
            description: Incident description
            ground_truth_findings: Known correct findings
            context_data: Full incident context
        
        Returns:
            Labeled incident dictionary
        """
        return {
            'incident_id': incident_id,
            'incident_type': incident_type,
            'severity': severity,
            'description': description,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'ground_truth': {
                'findings': ground_truth_findings,
                'root_causes': [f for f in ground_truth_findings if f.get('root_cause', False)],
                'affected_services': self._extract_services(context_data),
                'expected_severity': severity
            },
            'context_data': context_data
        }
    
    def create_50_incident_dataset(self) -> List[Dict]:
        """
        Create a comprehensive dataset of 50 labeled incidents.
        
        Distribution:
        - 10 high_latency incidents
        - 10 error_spike incidents
        - 10 pod_crashloop incidents
        - 5 resource_exhaustion incidents
        - 5 database_slow incidents
        - 5 network_issue incidents
        - 5 other incidents
        """
        from app.services.__tests__.data_generator import TestDataGenerator
        
        generator = TestDataGenerator()
        incidents = []
        
        # Incident type distribution
        incident_counts = {
            'high_latency': 10,
            'error_spike': 10,
            'pod_crashloop': 10,
            'resource_exhaustion': 5,
            'database_slow': 5,
            'network_issue': 5,
            'disk_full': 3,
            'memory_leak': 2
        }
        
        incident_id = 1
        
        for incident_type, count in incident_counts.items():
            for i in range(count):
                # Generate incident
                severity = ['low', 'medium', 'high', 'critical'][i % 4]
                
                context = generator.generate_incident(
                    incident_type=incident_type,
                    severity=severity,
                    complexity=0.5
                )
                
                # Create ground truth findings based on incident type
                ground_truth = self._create_ground_truth(incident_type, context)
                
                incident = self.create_labeled_incident(
                    incident_id=f"test_{incident_id:03d}",
                    incident_type=incident_type,
                    severity=severity,
                    description=f"{incident_type.replace('_', ' ').title()} - Test case {i+1}",
                    ground_truth_findings=ground_truth,
                    context_data=context
                )
                
                incidents.append(incident)
                incident_id += 1
        
        # Save dataset
        self._save_dataset(incidents)
        
        return incidents
    
    def _create_ground_truth(self, incident_type: str, context: Dict) -> List[Dict]:
        """Create ground truth findings based on incident type."""
        
        ground_truth_templates = {
            'high_latency': [
                {
                    'id': 'latency-001',
                    'description': 'API response time exceeded SLA',
                    'category': 'performance',
                    'severity': 'high',
                    'root_cause': True,
                    'actionable': True
                },
                {
                    'id': 'latency-002',
                    'description': 'Database query slow',
                    'category': 'database',
                    'severity': 'medium',
                    'root_cause': True,
                    'actionable': True
                }
            ],
            'error_spike': [
                {
                    'id': 'error-001',
                    'description': 'HTTP 502 errors increasing',
                    'category': 'availability',
                    'severity': 'critical',
                    'root_cause': True,
                    'actionable': True
                }
            ],
            'pod_crashloop': [
                {
                    'id': 'k8s-001',
                    'description': 'Pod in CrashLoopBackOff state',
                    'category': 'kubernetes',
                    'severity': 'high',
                    'root_cause': True,
                    'actionable': True
                }
            ],
            'resource_exhaustion': [
                {
                    'id': 'resource-001',
                    'description': 'CPU utilization at 95%',
                    'category': 'capacity',
                    'severity': 'high',
                    'root_cause': True,
                    'actionable': True
                }
            ],
            'database_slow': [
                {
                    'id': 'db-001',
                    'description': 'Database connection pool exhausted',
                    'category': 'database',
                    'severity': 'high',
                    'root_cause': True,
                    'actionable': True
                }
            ],
            'network_issue': [
                {
                    'id': 'network-001',
                    'description': 'Network latency between services',
                    'category': 'network',
                    'severity': 'medium',
                    'root_cause': True,
                    'actionable': True
                }
            ]
        }
        
        return ground_truth_templates.get(incident_type, [])
    
    def _extract_services(self, context: Dict) -> List[str]:
        """Extract affected services from context."""
        services = set()
        
        # From logs
        for log in context.get('logs', {}).get('logs', []):
            if 'service' in log.get('kubernetes', {}):
                services.add(log['kubernetes']['service'])
        
        # From APM data
        for error in context.get('apm_data', {}).get('errors', []):
            if 'service_name' in error:
                services.add(error['service_name'])
        
        return list(services)
    
    def _save_dataset(self, incidents: List[Dict]):
        """Save dataset to file."""
        with open(self.storage_path, 'w') as f:
            json.dump(incidents, f, indent=2)
    
    def load_dataset(self) -> List[Dict]:
        """Load dataset from file."""
        if not self.storage_path.exists():
            return self.create_50_incident_dataset()
        
        with open(self.storage_path, 'r') as f:
            return json.load(f)
```

**Acceptance Criteria**:
- [ ] 50 incidents created
- [ ] Ground truth defined for each
- [ ] Distribution matches plan
- [ ] Dataset persists to file

---

## 🌤️ Afternoon Session (4 Hours)

### Task 4: Accuracy Validator Implementation (2h)

**File**: `backend/app/quality/accuracy_validator.py`

```python
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class AccuracyValidator:
    """Validate optimization accuracy against baseline and ground truth."""
    
    def __init__(self):
        self.finding_comparator = FindingComparator()
    
    def compare_triage_cards(
        self,
        baseline_card: Dict,
        optimized_card: Dict,
        ground_truth: Optional[Dict] = None
    ) -> AccuracyReport:
        """
        Compare accuracy between baseline and optimized triage cards.
        
        Args:
            baseline_card: Triage card from baseline (non-optimized)
            optimized_card: Triage card from optimized
            ground_truth: Known correct findings (optional)
        
        Returns:
            AccuracyReport with all metrics
        """
        # Extract findings
        baseline_findings = self._extract_findings(baseline_card)
        optimized_findings = self._extract_findings(optimized_card)
        ground_truth_findings = (
            self._extract_findings(ground_truth) if ground_truth else None
        )
        
        # Compare findings
        tp, fp, fn = self.finding_comparator.compare_findings(
            baseline_findings,
            optimized_findings,
            ground_truth_findings
        )
        
        # Calculate metrics
        finding_recall = self._calculate_recall(len(tp), len(fn))
        finding_precision = self._calculate_precision(len(tp), len(fp))
        finding_f1 = self._calculate_f1(finding_precision, finding_recall)
        
        # Severity metrics
        severity_accuracy = self._calculate_severity_accuracy(
            baseline_findings,
            optimized_findings,
            ground_truth_findings
        )
        
        severity_recall = self._calculate_severity_recall(
            baseline_findings,
            optimized_findings,
            ground_truth_findings
        )
        
        # Root cause metrics
        root_cause_recall = self._calculate_root_cause_recall(
            baseline_findings,
            optimized_findings,
            ground_truth_findings
        )
        
        root_cause_precision = self._calculate_root_cause_precision(
            optimized_findings,
            ground_truth_findings
        )
        
        # Recommendation metrics
        recommendation_relevance = self._calculate_recommendation_relevance(
            optimized_card
        )
        
        recommendation_coverage = self._calculate_recommendation_coverage(
            baseline_findings,
            optimized_card
        )
        
        # Token metrics
        token_savings = self._calculate_token_savings(
            baseline_card,
            optimized_card
        )
        
        # Performance metrics
        processing_time = optimized_card.get('processing_time_ms', 0)
        
        return AccuracyReport(
            finding_recall=finding_recall,
            finding_precision=finding_precision,
            finding_f1=finding_f1,
            severity_accuracy=severity_accuracy,
            severity_recall_by_level=severity_recall,
            root_cause_recall=root_cause_recall,
            root_cause_precision=root_cause_precision,
            recommendation_relevance=recommendation_relevance,
            recommendation_coverage=recommendation_coverage,
            token_savings=token_savings,
            token_reduction_pct=0,  # Calculated elsewhere
            processing_time_ms=processing_time,
            baseline_findings_count=len(baseline_findings),
            optimized_findings_count=len(optimized_findings),
            ground_truth_findings_count=len(ground_truth_findings) if ground_truth_findings else 0,
            true_positives=list(tp),
            false_positives=list(fp),
            false_negatives=list(fn)
        )
    
    def _extract_findings(self, card: Dict) -> List[Finding]:
        """Extract findings from triage card."""
        if not card or 'findings' not in card:
            return []
        
        findings = []
        for f in card['findings']:
            findings.append(Finding(
                id=f.get('id', ''),
                description=f.get('description', ''),
                severity=f.get('severity', 'medium'),
                category=f.get('category', 'general'),
                confidence=f.get('confidence', 0.5),
                root_cause=f.get('root_cause', False),
                actionable=f.get('actionable', True)
            ))
        
        return findings
    
    def _calculate_recall(self, tp: int, fn: int) -> float:
        """Calculate recall: TP / (TP + FN)"""
        denominator = tp + fn
        return tp / denominator if denominator > 0 else 1.0
    
    def _calculate_precision(self, tp: int, fp: int) -> float:
        """Calculate precision: TP / (TP + FP)"""
        denominator = tp + fp
        return tp / denominator if denominator > 0 else 0.0
    
    def _calculate_f1(self, precision: float, recall: float) -> float:
        """Calculate F1 score: 2 * (P * R) / (P + R)"""
        denominator = precision + recall
        return 2 * (precision * recall) / denominator if denominator > 0 else 0.0
    
    def _calculate_severity_accuracy(
        self,
        baseline: List[Finding],
        optimized: List[Finding],
        ground_truth: Optional[List[Finding]]
    ) -> float:
        """Calculate severity accuracy."""
        if not ground_truth:
            # Compare with baseline
            reference = baseline
        else:
            reference = ground_truth
        
        if not reference:
            return 1.0  # No reference = perfect by default
        
        correct = 0
        total = len(reference)
        
        for ref_finding in reference:
            for opt_finding in optimized:
                if ref_finding.id == opt_finding.id:
                    if ref_finding.severity == opt_finding.severity:
                        correct += 1
                    break
        
        return correct / total if total > 0 else 1.0
    
    def _calculate_severity_recall(
        self,
        baseline: List[Finding],
        optimized: List[Finding],
        ground_truth: Optional[List[Finding]]
    ) -> Dict[str, float]:
        """Calculate recall by severity level."""
        reference = ground_truth if ground_truth else baseline
        
        if not reference:
            return {}
        
        severity_counts = {}
        severity_matched = {}
        
        # Initialize counters
        for finding in reference:
            sev = finding.severity
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            severity_matched[sev] = severity_matched.get(sev, 0)
        
        # Count matches
        for ref_finding in reference:
            for opt_finding in optimized:
                if ref_finding.id == opt_finding.id:
                    severity_matched[ref_finding.severity] += 1
                    break
        
        # Calculate recall by level
        recall_by_level = {}
        for sev, count in severity_counts.items():
            matched = severity_matched.get(sev, 0)
            recall_by_level[sev] = matched / count if count > 0 else 0.0
        
        return recall_by_level
    
    def _calculate_root_cause_recall(
        self,
        baseline: List[Finding],
        optimized: List[Finding],
        ground_truth: Optional[List[Finding]]
    ) -> float:
        """Calculate root cause recall."""
        reference = ground_truth if ground_truth else baseline
        
        if not reference:
            return 1.0
        
        ref_root_causes = {f.id for f in reference if f.root_cause}
        opt_root_causes = {f.id for f in optimized if f.root_cause}
        
        if not ref_root_causes:
            return 1.0
        
        matched = len(ref_root_causes & opt_root_causes)
        return matched / len(ref_root_causes)
    
    def _calculate_root_cause_precision(
        self,
        optimized: List[Finding],
        ground_truth: Optional[List[Finding]]
    ) -> float:
        """Calculate root cause precision."""
        if not ground_truth:
            return 1.0
        
        truth_root_causes = {f.id for f in ground_truth if f.root_cause}
        opt_root_causes = {f.id for f in optimized if f.root_cause}
        
        if not opt_root_causes:
            return 1.0
        
        matched = len(truth_root_causes & opt_root_causes)
        return matched / len(opt_root_causes)
    
    def _calculate_recommendation_relevance(self, card: Dict) -> float:
        """Calculate recommendation relevance (actionable / total)."""
        if not card or 'recommendations' not in card:
            return 1.0
        
        recommendations = card['recommendations']
        if not recommendations:
            return 1.0
        
        actionable = sum(1 for r in recommendations if r.get('actionable', True))
        return actionable / len(recommendations)
    
    def _calculate_recommendation_coverage(
        self,
        baseline_findings: List[Finding],
        optimized_card: Dict
    ) -> float:
        """Calculate recommendation coverage."""
        if not baseline_findings:
            return 1.0
        
        if not optimized_card or 'recommendations' not in optimized_card:
            return 0.0
        
        # For now, assume all findings have recommendations
        return 1.0
    
    def _calculate_token_savings(
        self,
        baseline_card: Dict,
        optimized_card: Dict
    ) -> int:
        """Calculate token savings."""
        baseline_tokens = baseline_card.get('input_tokens', 0)
        optimized_tokens = optimized_card.get('input_tokens', 0)
        
        return baseline_tokens - optimized_tokens
```

**Acceptance Criteria**:
- [ ] All accuracy metrics calculated
- [ ] Comparison logic correct
- [ ] Handles missing data gracefully
- [ ] Returns complete report

---

### Task 5: Testing & Validation (2h)

**File**: `backend/app/quality/__tests__/test_accuracy_validator.py`

```python
import pytest
from app.quality.accuracy_validator import AccuracyValidator, Finding, AccuracyReport
from app.quality.test_dataset import TestDataset

class TestAccuracyValidator:
    """Test accuracy validation functionality."""
    
    @pytest.fixture
    def validator(self):
        return AccuracyValidator()
    
    @pytest.fixture
    def sample_baseline_card(self):
        return {
            'findings': [
                {
                    'id': 'f1',
                    'description': 'High CPU usage',
                    'severity': 'high',
                    'category': 'performance',
                    'root_cause': True,
                    'actionable': True
                },
                {
                    'id': 'f2',
                    'description': 'Memory leak',
                    'severity': 'medium',
                    'category': 'capacity',
                    'root_cause': True,
                    'actionable': True
                }
            ],
            'input_tokens': 5000
        }
    
    @pytest.fixture
    def sample_optimized_card(self):
        return {
            'findings': [
                {
                    'id': 'f1',
                    'description': 'High CPU usage',
                    'severity': 'high',
                    'category': 'performance',
                    'root_cause': True,
                    'actionable': True
                }
            ],
            'input_tokens': 2000,
            'processing_time_ms': 100
        }
    
    def test_compare_triage_cards(self, validator, sample_baseline_card, sample_optimized_card):
        """Test comparing two triage cards."""
        report = validator.compare_triage_cards(
            sample_baseline_card,
            sample_optimized_card
        )
        
        assert isinstance(report, AccuracyReport)
        assert report.finding_recall >= 0.0
        assert report.finding_precision >= 0.0
        assert report.baseline_findings_count == 2
        assert report.optimized_findings_count == 1
    
    def test_recall_calculation(self, validator, sample_baseline_card, sample_optimized_card):
        """Test recall calculation."""
        report = validator.compare_triage_cards(
            sample_baseline_card,
            sample_optimized_card
        )
        
        # 1 TP (f1), 1 FN (f2) = 50% recall
        assert report.finding_recall == 0.5
    
    def test_precision_calculation(self, validator, sample_baseline_card, sample_optimized_card):
        """Test precision calculation."""
        report = validator.compare_triage_cards(
            sample_baseline_card,
            sample_optimized_card
        )
        
        # 1 TP (f1), 0 FP = 100% precision
        assert report.finding_precision == 1.0
    
    def test_token_savings(self, validator, sample_baseline_card, sample_optimized_card):
        """Test token savings calculation."""
        report = validator.compare_triage_cards(
            sample_baseline_card,
            sample_optimized_card
        )
        
        assert report.token_savings == 3000  # 5000 - 2000

class TestFindingComparator:
    """Test finding comparison logic."""
    
    @pytest.fixture
    def comparator(self):
        from app.quality.finding_comparator import FindingComparator
        return FindingComparator()
    
    def test_matching_findings(self, comparator):
        """Test matching findings."""
        f1 = Finding(
            id='f1',
            description='High CPU usage',
            severity='high',
            category='performance',
            confidence=0.9,
            root_cause=True,
            actionable=True
        )
        
        f2 = Finding(
            id='f2',  # Different ID but similar
            description='CPU usage is high',  # Similar description
            severity='high',  # Same severity
            category='performance',  # Same category
            confidence=0.8,
            root_cause=True,
            actionable=True
        )
        
        assert comparator._findings_match(f1, f2) is True
    
    def test_non_matching_findings(self, comparator):
        """Test non-matching findings."""
        f1 = Finding(
            id='f1',
            description='High CPU usage',
            severity='high',
            category='performance',
            confidence=0.9,
            root_cause=True,
            actionable=True
        )
        
        f2 = Finding(
            id='f2',
            description='Network latency',  # Different description
            severity='medium',  # Different severity
            category='network',  # Different category
            confidence=0.8,
            root_cause=False,
            actionable=True
        )
        
        assert comparator._findings_match(f1, f2) is False

class TestDataset:
    """Test dataset creation and management."""
    
    @pytest.fixture
    def dataset(self):
        return TestDataset()
    
    def test_create_labeled_incident(self, dataset):
        """Test creating a labeled incident."""
        incident = dataset.create_labeled_incident(
            incident_id='test-001',
            incident_type='high_latency',
            severity='high',
            description='Test incident',
            ground_truth_findings=[{
                'id': 'f1',
                'description': 'Latency high',
                'severity': 'high',
                'category': 'performance',
                'root_cause': True,
                'actionable': True
            }],
            context_data={'logs': [], 'metrics': {}}
        )
        
        assert incident['incident_id'] == 'test-001'
        assert incident['incident_type'] == 'high_latency'
        assert 'ground_truth' in incident
        assert len(incident['ground_truth']['findings']) == 1
    
    def test_create_50_incident_dataset(self, dataset):
        """Test creating 50 incident dataset."""
        incidents = dataset.create_50_incident_dataset()
        
        assert len(incidents) == 50
        
        # Check distribution
        types = {}
        for incident in incidents:
            itype = incident['incident_type']
            types[itype] = types.get(itype, 0) + 1
        
        # Should have multiple types
        assert len(types) >= 5
```

**Acceptance Criteria**:
- [ ] 15+ unit tests passing
- [ ] Accuracy validator functional
- [ ] Finding comparator working
- [ ] Dataset creation successful

---

## 📊 Day 6 Deliverables

### Code Deliverables
1. `accuracy_metrics.py` - Data classes
2. `finding_comparator.py` - Comparison logic
3. `accuracy_validator.py` - Main validator
4. `test_dataset.py` - Dataset management
5. Unit tests for all components

### Data Deliverables
1. 50 labeled test incidents
2. Test dataset persisted to file

### Documentation Deliverables
1. Day 6 summary document
2. Accuracy metrics documentation

---

## ✅ Day 6 Success Criteria Checklist

### Must Achieve
- [ ] AccuracyValidator implemented
- [ ] 50 labeled incidents created
- [ ] All metrics calculated correctly
- [ ] Tests passing

### Should Achieve
- [ ] Coverage >85%
- [ ] Dataset diverse (all incident types)

---

**Document Version**: 1.0  
**Status**: ✅ READY FOR EXECUTION
