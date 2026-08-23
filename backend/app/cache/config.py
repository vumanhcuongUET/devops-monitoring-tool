"""
Cache Configuration

Phase 7 - Sprint 1 - Day 5
Environment-based configuration for cache layers
"""

from typing import Optional
from pydantic_settings import BaseSettings


class CacheSettings(BaseSettings):
    """Cache configuration from environment variables."""

    # Redis Configuration
    redis_url: Optional[str] = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_max_connections: int = 20

    # Sentinel Configuration
    redis_sentinel_hosts: Optional[str] = None  # Comma-separated list
    redis_sentinel_master_name: str = "mymaster"
    redis_sentinel_password: Optional[str] = None

    # Cache Behavior
    cache_default_ttl: int = 300  # 5 minutes
    cache_enable_warming: bool = True
    cache_warming_interval: int = 300  # 5 minutes
    cache_serialization: str = "json"  # json or msgpack

    # L1 Cache
    l1_cache_enabled: bool = True
    l1_cache_max_size: int = 1000  # Max entries per request

    # L2 Cache
    l2_cache_enabled: bool = True
    l2_cache_key_prefix: str = "l2"

    # L3 Cache (Semantic)
    l3_cache_enabled: bool = True
    l3_cache_similarity_threshold: float = 0.7  # 70% similarity
    l3_cache_max_results: int = 5

    # Cache Invalidation
    cache_invalidation_enabled: bool = True
    cache_invalidation_check_interval: int = 60  # 1 minute

    # Single Flight
    single_flight_enabled: bool = True
    single_flight_timeout: int = 30  # 30 seconds

    # Monitoring
    cache_stats_enabled: bool = True
    cache_stats_reset_interval: int = 3600  # 1 hour

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


def get_cache_settings() -> CacheSettings:
    """
    Get cache settings from environment.

    Returns:
        CacheSettings instance with values from environment or defaults
    """
    return CacheSettings()


# Global settings instance
cache_settings = get_cache_settings()
