"""
Enhanced Log Sampler Tests - Day 3 Features

Tests for temporal scoring, keyword extraction, and 4-factor relevance scoring.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.log_sampler import KeywordExtractor, LogSampler
from app.services.token_optimizer import OptimizationConfig


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

    def test_extract_oom_error(self, extractor):
        """Test OOM error extraction."""
        alert = "Pod killed with OOMKilled status"
        keywords = extractor.extract_keywords(alert)

        assert 'OOMKilled' in keywords

    def test_extract_multiple_services(self, extractor):
        """Test extracting multiple service names."""
        alert = "Issues with api-service, worker-scheduler and payment-api"
        keywords = extractor.extract_keywords(alert)

        assert 'api-service' in keywords
        assert len(keywords) >= 3

    def test_extract_ip_address(self, extractor):
        """Test IP address extraction."""
        alert = "Connection failed to 192.168.1.100"
        keywords = extractor.extract_keywords(alert)

        assert '192.168.1.100' in keywords

    def test_extract_crashloop_backoff(self, extractor):
        """Test CrashLoopBackOff extraction."""
        alert = "Pod in CrashLoopBackOff state"
        keywords = extractor.extract_keywords(alert)

        assert 'CrashLoopBackOff' in keywords


class TestTemporalScoring:
    """Test temporal proximity scoring."""

    @pytest.fixture
    def sampler(self):
        config = OptimizationConfig()
        return LogSampler(config)

    @pytest.fixture
    def incident_time(self):
        return datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

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
        assert score == 0.4  # 20 min is in the 15-30 min bucket

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

    def test_30_min_log_score(self, sampler, incident_time):
        """Test log 30 minutes ago gets 0.4 score."""
        log = {
            '@timestamp': (incident_time - timedelta(minutes=30)).isoformat()
        }

        score = sampler._score_temporal_proximity(log, incident_time)
        assert score == 0.4

    def test_45_min_log_score(self, sampler, incident_time):
        """Test log 45 minutes ago gets 0.2 score."""
        log = {
            '@timestamp': (incident_time - timedelta(minutes=45)).isoformat()
        }

        score = sampler._score_temporal_proximity(log, incident_time)
        assert score == 0.2

    def test_10_min_log_score(self, sampler, incident_time):
        """Test log 10 minutes ago gets 0.7 score."""
        log = {
            '@timestamp': (incident_time - timedelta(minutes=10)).isoformat()
        }

        score = sampler._score_temporal_proximity(log, incident_time)
        assert score == 0.7  # 10 min is in the 5-15 min bucket

    def test_missing_timestamp_zero_score(self, sampler, incident_time):
        """Test log without timestamp gets zero score."""
        log = {'message': 'Some log'}

        score = sampler._score_temporal_proximity(log, incident_time)
        assert score == 0.0

    def test_invalid_timestamp_zero_score(self, sampler, incident_time):
        """Test log with invalid timestamp gets zero score."""
        log = {'@timestamp': 'invalid-date'}

        score = sampler._score_temporal_proximity(log, incident_time)
        assert score == 0.0


class TestRelevanceScoring:
    """Test comprehensive relevance scoring."""

    @pytest.fixture
    def sampler(self):
        config = OptimizationConfig()
        return LogSampler(config)

    @pytest.fixture
    def incident_config(self):
        return {
            'timestamp': datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc),
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
            '@timestamp': datetime.now(timezone.utc).isoformat()
        }

        score = sampler.calculate_relevance_score(log)

        assert 0.0 <= score.total_score <= 1.0
        assert 0.0 <= score.keyword_score <= 0.4
        assert 0.0 <= score.temporal_score <= 0.3
        assert 0.0 <= score.severity_score <= 0.2
        assert 0.0 <= score.service_score <= 0.1

    def test_no_incident_config(self, sampler):
        """Test scoring with minimal incident config."""
        sampler.configure_incident(
            timestamp=datetime.now(timezone.utc),
            alert_message=''
        )

        log = {'message': 'Test log'}

        score = sampler.calculate_relevance_score(log)
        assert score.total_score >= 0

    def test_higher_severity_scores_higher(self, sampler, incident_config):
        """Test log severity higher than incident gets partial credit."""
        incident_config['severity'] = 'warning'
        sampler.configure_incident(**incident_config)

        log = {
            'message': 'Critical error',
            'severity': 'critical'
        }

        score = sampler.calculate_relevance_score(log)
        assert score.severity_score > 0

    def test_severity_breakdown_serialization(self, sampler, incident_config):
        """Test RelevanceScore serialization."""
        sampler.configure_incident(**incident_config)

        log = {'message': 'Test'}
        score = sampler.calculate_relevance_score(log)

        breakdown = score.to_dict()
        assert 'total' in breakdown
        assert 'keyword' in breakdown
        assert 'temporal' in breakdown
        assert 'severity' in breakdown
        assert 'service' in breakdown


class TestSmartSampling:
    """Test smart sampling functionality."""

    @pytest.fixture
    def sampler(self):
        config = OptimizationConfig()
        return LogSampler(config)

    @pytest.fixture
    def sample_logs(self):
        base_time = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)
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
            'timestamp': datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc),
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
            'timestamp': datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc),
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
            'timestamp': datetime.now(timezone.utc),
            'alert_message': 'Test alert'
        }

        results = sampler.sample_logs_smart(
            sample_logs, incident_config, max_results=10
        )

        for result in results:
            assert '_relevance_score' in result
            assert '_relevance_breakdown' in result

    def test_sample_with_empty_logs(self, sampler):
        """Test sampling with empty log list."""
        incident_config = {
            'timestamp': datetime.now(timezone.utc),
            'alert_message': 'Test'
        }

        results = sampler.sample_logs_smart([], incident_config)
        assert results == []

    def test_sample_prioritizes_recent_logs(self, sampler):
        """Test recent logs are prioritized."""
        base_time = datetime.now(timezone.utc)

        logs = [
            {
                '@timestamp': (base_time - timedelta(minutes=10)).isoformat(),
                'message': 'Old log',
                'severity': 'error'
            },
            {
                '@timestamp': (base_time - timedelta(minutes=1)).isoformat(),
                'message': 'Recent log',
                'severity': 'error'
            }
        ]

        incident_config = {
            'timestamp': base_time,
            'alert_message': 'Test'
        }

        results = sampler.sample_logs_smart(logs, incident_config, max_results=2)

        # Recent log should come first
        assert results[0]['message'] == 'Recent log'


class TestAPMErrorSampling:
    """Test APM error sampling with relevance."""

    @pytest.fixture
    def sampler(self):
        config = OptimizationConfig()
        return LogSampler(config)

    @pytest.fixture
    def sample_apm_errors(self):
        return [
            {
                'error_message': 'Connection timeout',
                'transaction_name': 'api_checkout',
                'occurrences': 50,
                'affected_transactions': 200,
                '@timestamp': datetime.now(timezone.utc).isoformat()
            },
            {
                'error_message': 'Null pointer exception',
                'transaction_name': 'api_payment',
                'occurrences': 5,
                'affected_transactions': 10,
                '@timestamp': datetime.now(timezone.utc).isoformat()
            }
        ]

    def test_apm_error_scoring_considers_frequency(self, sampler, sample_apm_errors):
        """Test higher frequency errors score higher."""
        incident_config = {
            'timestamp': datetime.now(timezone.utc),
            'alert_message': 'Connection timeout on checkout'
        }

        results = sampler.sample_apm_errors_smart(
            apm_errors=sample_apm_errors,
            incident_config=incident_config,
            max_results=10
        )

        # First result should be the high-frequency error
        assert results[0]['error_message'] == 'Connection timeout'

    def test_apm_error_includes_scores(self, sampler, sample_apm_errors):
        """Test sampled APM errors include scores."""
        incident_config = {
            'timestamp': datetime.now(timezone.utc),
            'alert_message': 'Test'
        }

        results = sampler.sample_apm_errors_smart(
            sample_apm_errors, incident_config, max_results=10
        )

        for result in results:
            assert '_error_score' in result

    def test_apm_error_empty_list(self, sampler):
        """Test APM sampling with empty list."""
        incident_config = {
            'timestamp': datetime.now(timezone.utc),
            'alert_message': 'Test'
        }

        results = sampler.sample_apm_errors_smart(
            [], incident_config, max_results=10
        )

        assert results == []


class TestPerformance:
    """Performance tests for enhanced sampling."""

    @pytest.fixture
    def sampler(self):
        config = OptimizationConfig()
        return LogSampler(config)

    def test_sample_100_logs_performance(self, sampler):
        """Test sampling 100 logs completes quickly."""
        import time

        logs = [
            {'message': f'Log {i}', 'severity': 'info'}
            for i in range(100)
        ]

        incident_config = {
            'timestamp': datetime.now(timezone.utc),
            'alert_message': 'Test alert'
        }

        start = time.time()
        _results = sampler.sample_logs_smart(logs, incident_config, max_results=50)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 100, f"Sampling 100 logs took {elapsed_ms}ms"

    def test_sample_1000_logs_performance(self, sampler):
        """Test sampling 1000 logs completes quickly."""
        import time

        logs = [
            {'message': f'Log {i}', 'severity': 'info'}
            for i in range(1000)
        ]

        incident_config = {
            'timestamp': datetime.now(timezone.utc),
            'alert_message': 'Test alert'
        }

        start = time.time()
        _results = sampler.sample_logs_smart(logs, incident_config, max_results=50)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 300, f"Sampling 1000 logs took {elapsed_ms}ms"
