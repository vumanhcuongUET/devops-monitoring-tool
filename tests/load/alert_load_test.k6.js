/**
 * Alert Management Load Test
 * Phase 9 - Sprint 4 - Day 17
 *
 * Tests the alert management endpoints under load.
 * Run with: k6 run tests/load/alert_load_test.k6.js
 */

import http from 'k6/http';
import { check } from 'k6';

const BACKEND_URL = __ENV.BACKEND_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY || 'dev-key-123';

export const options = {
  scenarios: {
    constant_load: {
      executor: 'constant-vus',
      vus: 20,
      duration: '2m',
    },
  },
  thresholds: {
    'http_req_duration': ['p(95)<1000'],
    'http_req_failed': ['rate<0.02'],
    'checks': ['rate>0.95'],
  },
};

export default function () {
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
    },
  };

  // Test creating alert rules
  const payload = JSON.stringify({
    name: `TestAlert_${__VU}_${__ITER}`,
    condition: "error_rate > 5%",
    threshold: 5,
    window_minutes: 5,
    project: "meinvoice",
    severity: "high",
  });

  const res = http.post(`${BACKEND_URL}/api/v1/alerts/rules`, payload, params);

  check(res, {
    'create alert status 201 or 200': (r) => r.status === 201 || r.status === 200,
    'create alert response time < 1s': (r) => r.timings.duration < 1000,
  });
}
