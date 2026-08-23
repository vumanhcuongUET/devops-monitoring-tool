"""
Tests for sync_bridge module.
"""

import pytest
import asyncio

from core.sync_bridge import sync_async_bridge, run_async


class TestSyncAsyncBridge:
    """Tests for async-to-sync bridge decorator."""

    def test_sync_async_bridge_basic(self):
        """Test basic async function wrapping."""
        @sync_async_bridge
        async def async_func():
            await asyncio.sleep(0.01)
            return "result"

        result = async_func()
        assert result == "result"

    def test_sync_async_bridge_with_args(self):
        """Test async function with arguments."""
        @sync_async_bridge
        async def async_add(a, b):
            return a + b

        result = async_add(5, 3)
        assert result == 8

    def test_sync_async_bridge_with_kwargs(self):
        """Test async function with keyword arguments."""
        @sync_async_bridge
        async def async_greet(name):
            return f"Hello, {name}"

        result = async_greet(name="World")
        assert result == "Hello, World"

    def test_sync_async_bridge_exception(self):
        """Test that exceptions are properly propagated."""
        @sync_async_bridge
        async def async_error():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            async_error()

    def test_run_async_helper(self):
        """Test run_async helper function."""
        async def async_func():
            return "helper_result"

        result = run_async(async_func)
        assert result == "helper_result"

    @pytest.mark.asyncio
    async def test_sync_async_bridge_with_running_loop(self):
        """Test bridge behavior when event loop is already running."""
        # This test verifies the bridge handles existing loops correctly
        @sync_async_bridge
        async def nested_async():
            return "nested"

        # Since we're in async test, loop is running
        result = nested_async()
        assert result == "nested"
