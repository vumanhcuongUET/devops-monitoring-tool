"""
Sync/Async Bridge for AI Assistant.

Provides wrapper to call async backend services from sync CLI code.
"""

import asyncio
from functools import wraps
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def sync_async_bridge(func: Callable[..., Any]) -> Callable[..., T]:
    """
    Wrapper to call async functions from sync context.

    This allows ai_assistant CLI tool to use async backend clients
    without requiring the entire CLI to be async.

    Usage:
        @sync_async_bridge
        async def my_async_method():
            return await some_async_operation()

        # Can be called from sync code:
        result = my_async_method()
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running (e.g., in Jupyter), run in thread pool
                import concurrent.futures
                import concurrent.futures.thread

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, func(*args, **kwargs))
                    return future.result()
            else:
                # Loop exists but not running, use it
                return loop.run_until_complete(func(*args, **kwargs))
        except RuntimeError:
            # No event loop exists, create new one
            return asyncio.run(func(*args, **kwargs))

    return wrapper


def run_async(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """
    Helper to run an async function from sync context.

    Alternative to the decorator when you don't want to modify
    the original function.

    Usage:
        result = run_async(async_function, arg1, arg2)
    """
    return asyncio.run(func(*args, **kwargs))
