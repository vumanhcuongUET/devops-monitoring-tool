# Phase 6: Sprint 1 - Day 3 Detailed Implementation Plan

**Date**: Day 3 of Sprint 1  
**Focus**: Smart Sampling Enhancement  
**Duration**: 8 hours  
**Status**: 📋 READY FOR EXECUTION

---

## 📋 Day 3 Objectives

### Primary Goals
1. ✅ Implement temporal proximity scoring for logs
2. ✅ Add keyword extraction from alerts
3. ✅ Enhance relevance scoring with 4-factor weighting
4. ✅ Apply intelligent sampling to APM errors
5. ✅ Profile and validate sampling performance

### Success Metrics
| Metric | Target | How to Measure |
|--------|--------|----------------|
| Temporal Scoring | Functional | Unit tests |
| Keyword Extraction | 5-10 keywords | Test validation |
| Relevance Score | 0.0-1.0 range | Unit tests |
| APM Error Sampling | Prioritized | Integration tests |
| Sampling Speed | <200ms for 1k logs | Performance tests |
| Token Savings | >40% for logs | Comparison tests |

---

## 🌅 Morning Session (4 Hours)

### Task 1: Temporal Proximity Scoring (1.5h)

**File**: `backend/app/services/log_sampler.py`

#### Implementation

```python
from datetime import datetime, timedelta
from typing import List, Dict

class LogSampler:
    """Enhanced log sampler with temporal and relevance scoring."""
    
    TEMPORAL_WEIGHTS = {
        timedelta(minutes=5): 1.0,      # Within 5 min: full score
        timedelta(minutes=15): 0.7,     # Within 15 min: 70% score
        timedelta(minutes=30): 0.4,     # Within 30 min: 40% score
        timedelta(hours=1): 0.2,        # Within 1 hour: 20% score
    }
    
    def __init__(self):
        self.incident_timestamp = None
        self.time_windows = sorted(
            self.TEMPORAL_WEIGHTS.keys(),
            key=lambda x: x.total_seconds()
        )
    
    def set_incident_time(self, timestamp: datetime):
        """Set the incident timestamp for proximity scoring."""
        self.incident_timestamp = timestamp
    
    def _score_temporal_proximity(
        self,
        log: Dict,
        incident_timestamp: datetime
    ) -> float:
        """
        Score log based on temporal proximity to incident.
        
        Scoring:
        - Within 5 min:  1.0 score
        - Within 15 min: 0.7 score
        - Within 30 min: 0.4 score
        - Within 1 hour: 0.2 score
        - Beyond 1 hour: 0.1 score
        - Future: 0.0 score
        
        Args:
            log: Log entry with @timestamp field
            incident_timestamp: Incident occurrence time
        
        Returns:
            Float score between 0.0 and 1.0
        """
        try:
            log_time = datetime.fromisoformat(
                log.get('@timestamp', '').replace('Z', '+00:00')
            ).replace(tzinfo=None)
            
            incident_time = incident_timestamp.replace(tzinfo=None)
            
            # Future logs get zero score
            if log_time > incident_time:
                return 0.0
            
            time_diff = incident_time - log_time
            
            # Find applicable time window
            for window in self.time_windows:
                if time_diff <= window:
                    return self.TEMPORAL_WEIGHTS[window]
            
            # Beyond all windows
            return 0.1
            
        except (ValueError, KeyError):
            return 0.0  # Default score for parsing errors
    
    def sample_logs_with_temporal(
        self,
        logs: List[Dict],
        incident_timestamp: datetime,
        max_results: int = 50
    ) -> List[Dict]:
        """
        Sample logs with temporal proximity scoring.
        
        Process:
        1. Score each log by temporal proximity
        2. Sort by score (descending)
        3. Return top N results
        
        Args:
            logs: List of log entries
            incident_timestamp: When incident occurred
            max_results: Maximum logs to return
        
        Returns:
            List of sampled logs with temporal scores
        """
        scored_logs = []
        
        for log in logs:
            temporal_score = self._score_temporal_proximity(
                log, incident_timestamp
            )
            
            scored_logs.append({
                **log,
                '_temporal_score': temporal_score
            })
        
        # Sort by temporal score (descending)
        scored_logs.sort(
            key=lambda x: x['_temporal_score'],
            reverse=True
        )
        
        # Return top results
        return scored_logs[:max_results]
```

**Acceptance Criteria**:
- [ ] Temporal scoring returns 0.0-1.0 range
- [ ] Recent logs (5min) get 1.0 score
- [ ] Old logs (>1hour) get ≤0.1 score
- [ ] Future logs get 0.0 score
- [ ] Handles missing timestamps gracefully

---

### Task 2: Keyword Extraction from Alerts (1h)

**File**: `backend/app/services/log_sampler.py`

#### Implementation

```python
import re
from typing import List, Set

class KeywordExtractor:
    """Extract relevant keywords from alert messages."""
    
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
        
        # 3. Filter stop words and short words
        significant_words = [
            w for w in words 
            if w not in self.STOP_WORDS and len(w) > 2
        ]
        
        # 4. Extract service names (common patterns)
        service_keywords = self._extract_service_names(alert_message)
        keywords.update(service_keywords)
        
        # 5. Extract error types
        error_keywords = self._extract_error_types(alert_message)
        keywords.update(error_keywords)
        
        # 6. Convert to list and limit
        keyword_list = list(keywords)[:10]
        
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
```

**Acceptance Criteria**:
- [ ] Extracts 5-10 keywords from alert
- [ ] Filters common stop words
- [ ] Identifies technical terms correctly
- [ ] Extracts service names
- [ ] Extracts error types

---

### Task 3: Relevance Scoring Enhancement (1.5h)

**File**: `backend/app/services/log_sampler.py`

#### Implementation

```python
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class RelevanceScore:
    """Relevance score with breakdown."""
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

class LogSampler:
    """Enhanced with comprehensive relevance scoring."""
    
    def __init__(self):
        self.keyword_extractor = KeywordExtractor()
        self.incident_timestamp = None
        self.incident_keywords = []
        self.incident_service = None
        self.incident_severity = None
    
    def configure_incident(
        self,
        timestamp: datetime,
        alert_message: str,
        service: Optional[str] = None,
        severity: Optional[str] = None
    ):
        """Configure incident context for scoring."""
        self.incident_timestamp = timestamp
        self.incident_keywords = self.keyword_extractor.extract_keywords(
            alert_message
        )
        self.incident_service = service
        self.incident_severity = severity
    
    def _calculate_keyword_score(self, log: Dict) -> float:
        """
        Calculate keyword match score.
        
        Score = (matched_keywords / total_keywords) * 0.4
        """
        if not self.incident_keywords:
            return 0.0
        
        log_message = log.get('message', '').lower()
        matched = sum(
            1 for kw in self.incident_keywords 
            if kw.lower() in log_message
        )
        
        return (matched / len(self.incident_keywords)) * 0.4
    
    def _calculate_temporal_score(self, log: Dict) -> float:
        """
        Calculate temporal proximity score.
        
        Returns score weighted by 0.3
        """
        base_score = self._score_temporal_proximity(
            log, self.incident_timestamp
        )
        return base_score * 0.3
    
    def _calculate_severity_score(self, log: Dict) -> float:
        """
        Calculate severity match score.
        
        If log severity matches incident severity: 0.2
        If log severity is higher: 0.15
        If log severity is lower: 0.1
        Else: 0.0
        """
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
        """
        Calculate service relevance score.
        
        If log service matches: 0.1
        If related service (same namespace): 0.05
        Else: 0.0
        """
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
    
    def calculate_relevance_score(self, log: Dict) -> RelevanceScore:
        """
        Calculate comprehensive relevance score.
        
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
    
    def sample_logs_smart(
        self,
        logs: List[Dict],
        incident_config: Dict,
        max_results: int = 50
    ) -> List[Dict]:
        """
        Sample logs using comprehensive relevance scoring.
        
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
```

**Acceptance Criteria**:
- [ ] All 4 factors weighted correctly
- [ ] Score ranges 0.0-1.0
- [ ] Keyword matching works
- [ ] Temporal proximity accurate
- [ ] Severity matching functional
- [ ] Service relevance working

---

## 🌤️ Afternoon Session (4 Hours)

### Task 4: APM Error Sampling Enhancement (1.5h)

**File**: `backend/app/services/log_sampler.py`

#### Implementation

```python
class LogSampler:
    """Enhanced with APM error sampling."""
    
    def sample_apm_errors_smart(
        self,
        apm_errors: List[Dict],
        incident_config: Dict,
        max_results: int = 10
    ) -> List[Dict]:
        """
        Sample APM errors with relevance scoring.
        
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
        Calculate APM error importance score.
        
        Factors:
        - Frequency (0-0.4): More frequent = higher score
        - Keyword match (0-0.3): Based on alert keywords
        - Impact (0-0.2): Transactions affected
        - Temporal (0-0.1): Proximity to incident
        """
        score = 0.0
        
        # 1. Frequency score
        frequency = error.get('occurrences', 0)
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
        if error_time:
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
            except:
                pass
        
        return min(score, 1.0)
```

**Acceptance Criteria**:
- [ ] APM errors scored by relevance
- [ ] Frequency affects scoring correctly
- [ ] Keyword matching works
- [ ] Impact measured correctly
- [ ] Temporal proximity considered

---

### Task 5: Comprehensive Testing (1.5h)

**File**: `backend/app/services/__tests__/test_log_sampler_enhanced.py`

#### Test Implementation

```python
import pytest
from datetime import datetime, timedelta
from app.services.log_sampler import LogSampler, KeywordExtractor, RelevanceScore

class TestKeywordExtractor:
    """Test keyword extraction from alerts."""
    
    @pytest.fixture
    def extractor(self):
        return KeywordExtractor()
    
    def test_extract_basic_keywords(self, extractor):
        """Test basic keyword extraction."""
        alert = "High latency detected on api-service"
        keywords = extractor.extract_keywords(alert)
        
        assert 'api-service' in keywords
        assert len(keywords) >= 3
    
    def test_extract_error_codes(self, extractor):
        """Test HTTP error code extraction."""
        alert = "502 Bad Gateway on payment-service"
        keywords = extractor.extract_keywords(alert)
        
        assert '502' in keywords
        assert 'payment-service' in keywords
    
    def test_extract_service_names(self, extractor):
        """Test service name extraction."""
        alert = "Pod worker-1 in CrashLoopBackOff state"
        keywords = extractor.extract_keywords(alert)
        
        assert 'worker' in keywords or 'worker-1' in keywords
    
    def test_filter_stop_words(self, extractor):
        """Test stop word filtering."""
        alert = "The alert was detected on the service"
        keywords = extractor.extract_keywords(alert)
        
        assert 'the' not in keywords
        assert 'alert' not in keywords  # In stop list
        assert 'service' in keywords


class TestTemporalScoring:
    """Test temporal proximity scoring."""
    
    @pytest.fixture
    def sampler(self):
        return LogSampler()
    
    @pytest.fixture
    def incident_time(self):
        return datetime(2026, 8, 23, 12, 0, 0)
    
    def test_recent_log_full_score(self, sampler, incident_time):
        """Test log within 5 minutes gets full score."""
        log = {
            '@timestamp': (incident_time - timedelta(minutes=2)).isoformat()
        }
        
        score = sampler._score_temporal_proximity(log, incident_time)
        assert score == 1.0
    
    def test_older_log_reduced_score(self, sampler, incident_time):
        """Test log 20 minutes ago gets reduced score."""
        log = {
            '@timestamp': (incident_time - timedelta(minutes=20)).isoformat()
        }
        
        score = sampler._score_temporal_proximity(log, incident_time)
        assert score == 0.7
    
    def test_old_log_minimal_score(self, sampler, incident_time):
        """Test log >1 hour ago gets minimal score."""
        log = {
            '@timestamp': (incident_time - timedelta(hours=2)).isoformat()
        }
        
        score = sampler._score_temporal_proximity(log, incident_time)
        assert score == 0.1
    
    def test_future_log_zero_score(self, sampler, incident_time):
        """Test future log gets zero score."""
        log = {
            '@timestamp': (incident_time + timedelta(minutes=5)).isoformat()
        }
        
        score = sampler._score_temporal_proximity(log, incident_time)
        assert score == 0.0


class TestRelevanceScoring:
    """Test comprehensive relevance scoring."""
    
    @pytest.fixture
    def sampler(self):
        return LogSampler()
    
    @pytest.fixture
    def incident_config(self):
        return {
            'timestamp': datetime(2026, 8, 23, 12, 0, 0),
            'alert_message': 'High latency on payment-service',
            'service': 'payment-service',
            'severity': 'error'
        }
    
    def test_keyword_match_score(self, sampler, incident_config):
        """Test keyword matching contributes to score."""
        sampler.configure_incident(**incident_config)
        
        log = {
            'message': 'Payment API latency exceeded threshold',
            'service': 'payment-service',
            'severity': 'error'
        }
        
        score = sampler.calculate_relevance_score(log)
        
        assert score.keyword_score > 0
        assert score.total_score > 0
    
    def test_temporal_proximity_score(self, sampler, incident_config):
        """Test temporal proximity contributes to score."""
        sampler.configure_incident(**incident_config)
        
        log = {
            'message': 'Some log message',
            '@timestamp': (
                incident_config['timestamp'] - timedelta(minutes=3)
            ).isoformat()
        }
        
        score = sampler.calculate_relevance_score(log)
        
        assert score.temporal_score > 0
    
    def test_severity_match_score(self, sampler, incident_config):
        """Test severity matching contributes to score."""
        sampler.configure_incident(**incident_config)
        
        log = {
            'message': 'Error occurred',
            'severity': 'error'
        }
        
        score = sampler.calculate_relevance_score(log)
        
        assert score.severity_score > 0
    
    def test_service_relevance_score(self, sampler, incident_config):
        """Test service matching contributes to score."""
        sampler.configure_incident(**incident_config)
        
        log = {
            'message': 'Processing payment',
            'service': 'payment-service'
        }
        
        score = sampler.calculate_relevance_score(log)
        
        assert score.service_score > 0
    
    def test_score_range(self, sampler, incident_config):
        """Test scores are in valid range."""
        sampler.configure_incident(**incident_config)
        
        log = {
            'message': 'Test log',
            '@timestamp': datetime.now().isoformat()
        }
        
        score = sampler.calculate_relevance_score(log)
        
        assert 0.0 <= score.total_score <= 1.0
        assert 0.0 <= score.keyword_score <= 0.4
        assert 0.0 <= score.temporal_score <= 0.3
        assert 0.0 <= score.severity_score <= 0.2
        assert 0.0 <= score.service_score <= 0.1


class TestSmartSampling:
    """Test smart sampling functionality."""
    
    @pytest.fixture
    def sampler(self):
        return LogSampler()
    
    @pytest.fixture
    def sample_logs(self):
        base_time = datetime(2026, 8, 23, 12, 0, 0)
        return [
            {
                '@timestamp': (base_time - timedelta(minutes=i)).isoformat(),
                'message': f'Log message {i}',
                'severity': 'info' if i % 2 else 'error',
                'service': 'test-service'
            }
            for i in range(100)
        ]
    
    def test_sample_returns_limit(self, sampler, sample_logs):
        """Test sampling respects max_results limit."""
        incident_config = {
            'timestamp': datetime(2026, 8, 23, 12, 0, 0),
            'alert_message': 'Test alert',
            'service': 'test-service'
        }
        
        results = sampler.sample_logs_smart(
            sample_logs, incident_config, max_results=10
        )
        
        assert len(results) <= 10
    
    def test_sample_sorts_by_relevance(self, sampler, sample_logs):
        """Test results are sorted by relevance score."""
        incident_config = {
            'timestamp': datetime(2026, 8, 23, 12, 0, 0),
            'alert_message': 'Test alert',
            'service': 'test-service'
        }
        
        results = sampler.sample_logs_smart(
            sample_logs, incident_config, max_results=20
        )
        
        # Check scores are descending
        scores = [r['_relevance_score'] for r in results]
        assert scores == sorted(scores, reverse=True)
    
    def test_sample_includes_scores(self, sampler, sample_logs):
        """Test sampled logs include relevance scores."""
        incident_config = {
            'timestamp': datetime(2026, 8, 23, 12, 0, 0),
            'alert_message': 'Test alert'
        }
        
        results = sampler.sample_logs_smart(
            sample_logs, incident_config, max_results=10
        )
        
        for result in results:
            assert '_relevance_score' in result
            assert '_relevance_breakdown' in result
```

**Acceptance Criteria**:
- [ ] 20+ new tests passing
- [ ] Coverage >90% for LogSampler
- [ ] All enhancements validated

---

### Task 6: Performance Profiling (1h)

**File**: `backend/tests/performance/test_sampling_performance.py`

#### Implementation

```python
import pytest
import time
from app.services.log_sampler import LogSampler
from app.services.__tests__.data_generator import TestDataGenerator

class TestSamplingPerformance:
    """Performance benchmarks for log sampling."""
    
    @pytest.fixture
    def sampler(self):
        return LogSampler()
    
    @pytest.fixture
    def generator(self):
        return TestDataGenerator()
    
    def test_sample_100_logs_performance(self, sampler):
        """Test sampling 100 logs completes quickly."""
        logs = [{'message': f'Log {i}', 'severity': 'info'} for i in range(100)]
        
        incident_config = {
            'timestamp': datetime.now(),
            'alert_message': 'Test alert'
        }
        
        start = time.time()
        results = sampler.sample_logs_smart(logs, incident_config, max_results=50)
        elapsed_ms = (time.time() - start) * 1000
        
        assert elapsed_ms < 50, f"Sampling 100 logs took {elapsed_ms}ms"
    
    def test_sample_1000_logs_performance(self, sampler):
        """Test sampling 1000 logs completes quickly."""
        logs = [{'message': f'Log {i}', 'severity': 'info'} for i in range(1000)]
        
        incident_config = {
            'timestamp': datetime.now(),
            'alert_message': 'Test alert'
        }
        
        start = time.time()
        results = sampler.sample_logs_smart(logs, incident_config, max_results=50)
        elapsed_ms = (time.time() - start) * 1000
        
        assert elapsed_ms < 200, f"Sampling 1000 logs took {elapsed_ms}ms"
    
    def test_memory_usage(self, sampler):
        """Test memory usage is reasonable."""
        import tracemalloc
        
        tracemalloc.start()
        
        logs = [{'message': f'Log {i}', 'severity': 'info'} for i in range(10000)]
        
        incident_config = {
            'timestamp': datetime.now(),
            'alert_message': 'Test alert'
        }
        
        results = sampler.sample_logs_smart(logs, incident_config, max_results=50)
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Peak memory should be <50MB for 10k logs
        assert peak < 50 * 1024 * 1024, f"Peak memory was {peak / 1024 / 1024}MB"
```

**Acceptance Criteria**:
- [ ] 100 logs sampled in <50ms
- [ ] 1000 logs sampled in <200ms
- [ ] 10k logs use <50MB memory
- [ ] No memory leaks in repeated sampling

---

## 📊 Day 3 Deliverables

### Code Deliverables
1. **Enhanced LogSampler** with temporal + relevance scoring
2. **KeywordExtractor** for alert parsing
3. **APM error sampling** with intelligence
4. **Comprehensive tests** (25+ tests)

### Test Deliverables
1. Unit tests for KeywordExtractor (5+ tests)
2. Unit tests for temporal scoring (5+ tests)
3. Unit tests for relevance scoring (8+ tests)
4. Integration tests for smart sampling (5+ tests)
5. Performance benchmarks (3+ tests)

### Documentation Deliverables
1. Day 3 summary document
2. Updated INDEX.md

---

## ✅ Day 3 Success Criteria Checklist

### Must Achieve
- [ ] Temporal scoring functional
- [ ] Keyword extraction working
- [ ] Relevance scoring with 4 factors
- [ ] APM error sampling prioritized
- [ ] 25+ tests passing
- [ ] Sampling <200ms for 1k logs

### Should Achieve
- [ ] Coverage >90% for LogSampler
- [ ] Token savings >40% for logs
- [ ] Performance <50ms for 100 logs

### Could Achieve
- [ ] Token savings >50% for logs
- [ ] Additional relevance factors
- [ ] Advanced keyword NLP

---

**Document Version**: 1.0  
**Created**: 2026-08-23  
**Status**: ✅ READY FOR EXECUTION
