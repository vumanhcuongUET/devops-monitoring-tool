"""
OpenTelemetry Distributed Tracing Module

Phase 9 - Sprint 4 - Day 16
Purpose: Enable distributed tracing with OpenTelemetry

Features:
- Automatic FastAPI instrumentation
- HTTP client tracing (httpx)
- Asyncio operation tracking
- Span export to OTLP endpoint
- Resource attributes for service identification
"""

import asyncio
import functools
import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from app.config import settings

logger = logging.getLogger(__name__)

# Global tracer provider
_tracer_provider: TracerProvider | None = None


def get_tracer(name: str = __name__):
    """Get a tracer for the given component name."""
    return trace.get_tracer(name)


def setup_telemetry(app=None) -> TracerProvider:
    """
    Setup OpenTelemetry tracing for the application.

    This function:
    1. Creates a TracerProvider with service resource attributes
    2. Configures OTLP span exporter (or console exporter if no endpoint)
    3. Instruments FastAPI for automatic request/response tracing
    4. Instruments httpx for HTTP client tracing
    5. Instruments asyncio for operation tracking

    Args:
        app: Optional FastAPI application to instrument

    Returns:
        Configured TracerProvider

    Example:
        from app.telemetry import setup_telemetry
        from fastapi import FastAPI

        app = FastAPI()
        tracer_provider = setup_telemetry(app)
    """
    global _tracer_provider

    # Resource attributes identify this service
    resource = Resource.create({
        SERVICE_NAME: "devops-monitoring-backend",
        "service.version": "1.0.0",
        "deployment.environment": settings.ENVIRONMENT,
        "service.namespace": "devops-monitoring",
    })

    # Create tracer provider
    _tracer_provider = TracerProvider(resource=resource)

    # Configure exporter based on environment
    otlp_endpoint = getattr(settings, "OTLP_ENDPOINT", None)

    if otlp_endpoint:
        # Production: Export to OTLP endpoint (Jaeger, Tempo, etc.)
        otlp_secure = getattr(settings, "OTLP_SECURE", True)
        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=not otlp_secure,
        )
        logger.info(f"Configured OTLP exporter: {otlp_endpoint}")
    else:
        # Development: Use console exporter
        exporter = ConsoleSpanExporter()
        logger.info("Using console span exporter (development mode)")

    # Add batch span processor for efficient exporting
    _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

    # Set as global default
    trace.set_tracer_provider(_tracer_provider)

    # Instrument FastAPI
    if app is not None:
        try:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI instrumented for tracing")
        except Exception as e:
            logger.warning(f"Failed to instrument FastAPI: {e}")

    # Instrument HTTP clients
    try:
        HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX instrumented for tracing")
    except Exception as e:
        logger.warning(f"Failed to instrument HTTPX: {e}")

    # Instrument asyncio
    try:
        AsyncioInstrumentor().instrument()
        logger.info("Asyncio instrumented for tracing")
    except Exception as e:
        logger.warning(f"Failed to instrument asyncio: {e}")

    logger.info("OpenTelemetry tracing initialized")
    return _tracer_provider


def shutdown_telemetry():
    """Shutdown telemetry and flush remaining spans."""
    global _tracer_provider

    if _tracer_provider:
        logger.info("Shutting down telemetry...")
        _tracer_provider.shutdown()
        _tracer_provider = None


class TracedOperation:
    """
    Context manager for tracing custom operations.

    Use this to manually create spans for operations not automatically
    instrumented.

    Example:
        with TracedOperation("database.query", {"query": "SELECT *"}):
            result = db.execute_query(...)
    """

    def __init__(self, name: str, attributes: dict | None = None):
        """
        Initialize traced operation.

        Args:
            name: Operation name (will become span name)
            attributes: Optional span attributes
        """
        self.name = name
        self.attributes = attributes or {}
        self.span = None

    def __enter__(self):
        """Start the span."""
        tracer = get_tracer(__name__)
        self._cm = tracer.start_as_current_span(
            self.name,
            attributes=self.attributes,
        )
        self.span = self._cm.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End the span."""
        if self._cm:
            if exc_type is not None:
                self.span.record_exception(exc_val)
                self.span.set_status(StatusCode.ERROR, str(exc_val))
            self._cm.__exit__(exc_type, exc_val, exc_tb)


def trace_function(name: str | None = None):
    """Decorator to trace sync and async function execution."""
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                span_name = name or f"{func.__module__}.{func.__name__}"
                with TracedOperation(span_name):
                    return await func(*args, **kwargs)
            return async_wrapper
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            span_name = name or f"{func.__module__}.{func.__name__}"
            with TracedOperation(span_name):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# Optional: Status import
try:
    from opentelemetry.trace import Status, StatusCode
except ImportError:
    # Fallback for older versions
    class Status:
        def __init__(self, status_code, description=None):
            self.status_code = status_code
            self.description = description

    class StatusCode:
        OK = "OK"
        ERROR = "ERROR"
        UNSET = "UNSET"
