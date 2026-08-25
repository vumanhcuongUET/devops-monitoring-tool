/**
 * Overview Endpoint Load Test
 * Phase 9 - Sprint 4 - Day 17
 *
 * This test simulates concurrent users accessing the overview endpoint
 * to validate performance under load.
 *
 * Run with: k6 run tests/load/overview_load_test.k6.js
 * Or with specific URL: BACKEND_URL=http://localhost:8000 k6 run tests/load/overview_load_test.k6.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';

const BACKEND_URL = __ENV.BACKEND_URL || 'http://localhost:8000';

export const options = {
  // Stages: ramp-up to sustained load, then ramp down
  stages: [
    { duration: '1m', target: 10 },   // Ramp up to 10 users
    { duration: '3m', target: 50 },   // Ramp up to 50 users
    { duration: '5m', target: 100 },  // Ramp up to 100 users
    { duration: '2m', target: 0 },    // Ramp down
  ],

  // Performance thresholds
  thresholds: {
    // 95% of requests should complete within 2 seconds
    'http_req_duration': ['p(95)<2000'],

    // 99% of requests should complete within 5 seconds
    'http_req_duration': ['p(99)<5000'],

    // Error rate should be less than 1%
    'http_req_failed': ['rate<0.01'],

    // Checks should pass more than 95% of the time
    'checks': ['rate>0.95'],
  },
};

export default function () {
  // Test the overview endpoint
  const overviewRes = http.get(`${BACKEND_URL}/api/v1/overview?project=meinvoice`, {
    tags: { name: 'Overview' },
  });

  check(overviewRes, {
    'overview status 200': (r) => r.status === 200,
    'overview response time < 2s': (r) => r.timings.duration < 2000,
    'overview has content': (r) => r.json('systems') !== undefined,
  });

  // Optional: Test APM data endpoint
  const apmRes = http.get(
    `${BACKEND_URL}/api/v1/apm/transactions?project=meinvoice&range=1h`,
    { tags: { name: 'APM' } }
  );

  check(apmRes, {
    'apm status 200': (r) => r.status === 200 || r.status === 404, // 404 is acceptable if no APM data
  });

  // Small pause between iterations to simulate realistic user behavior
  sleep(Math.random() * 2 + 1); // Random sleep between 1-3 seconds
}

export function handleSummary(data) {
  return {
    stdout: JSON.stringify(data, null, 2),
  };
}
