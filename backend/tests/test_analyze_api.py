#!/usr/bin/env python3
"""
Test script for /api/v1/analyze endpoint.

This script tests the AI-powered incident analysis API.

Usage:
    python test_analyze_api.py

Prerequisites:
    1. Backend running: cd backend && uvicorn app.main:app --reload
    2. ANTHROPIC_API_KEY set in .env
    3. Valid API key configured
"""

import asyncio
import json
import os
from datetime import datetime

import httpx


# Configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "test-api-key")  # Replace with actual API key


async def test_analyze_health():
    """Test the analyze health endpoint."""
    print("\n🔍 Testing /api/v1/analyze/health...")

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/v1/analyze/health")

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Health check passed: {data}")
        return True
    else:
        print(f"❌ Health check failed: {response.status_code} - {response.text}")
        return False


async def test_analyze_incident():
    """Test the analyze endpoint with a sample incident."""
    print("\n🔍 Testing /api/v1/analyze with sample incident...")

    request_data = {
        "project": "meinvoice",
        "incident_id": f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "alert_message": "High error rate detected in meinvoice production API",
        "time_range_minutes": 60,
        "include_recommendations": True,
        "severity_threshold": "medium",
    }

    print(f"📤 Request: {json.dumps(request_data, indent=2)}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/analyze",
            json=request_data,
            headers={"X-API-Key": API_KEY},
        )

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            triage_card = data.get("triage_card")
            print(f"✅ Triage Card generated successfully!")
            print(f"\n📋 Summary: {triage_card.get('summary', 'N/A')}")
            print(f"🚨 Severity: {triage_card.get('severity', 'N/A')}")
            print(f"📊 Status: {triage_card.get('status', 'N/A')}")
            print(f"\n🔍 Findings ({len(triage_card.get('findings', []))}):")
            for i, finding in enumerate(triage_card.get('findings', [])[:3], 1):
                print(f"  {i}. [{finding.get('severity')}] {finding.get('title')}")
            print(f"\n💡 Recommendations ({len(triage_card.get('recommendations', []))}):")
            for i, rec in enumerate(triage_card.get('recommendations', [])[:3], 1):
                print(f"  {i}. [Priority {rec.get('priority')}] {rec.get('action')}")
            return True
        else:
            print(f"❌ API returned error: {data.get('error')}")
            return False
    else:
        print(f"❌ Request failed: {response.status_code} - {response.text}")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("DevOps AI Agentics 2026 - Analyze API Test")
    print("=" * 60)

    # Test health first
    health_ok = await test_analyze_health()

    if health_ok:
        # Test analyze endpoint
        await test_analyze_incident()
    else:
        print("\n⚠️ Skipping analyze test due to health check failure")
        print("   Ensure ANTHROPIC_API_KEY is configured in .env")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
