"""
Alembic Environment Configuration

Phase 10 - Sprint 1 - Day 3
Purpose: Configure Alembic for database migrations
"""

import asyncio

# Import settings and models
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Import all models to ensure they're registered with SQLAlchemy
import app.database.models  # noqa: F401
from app.settings import settings
from app.database.base import Base

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata

# Get database URL from settings
DATABASE_URL = (
    settings.DATABASE_URL
    or f"postgresql+asyncpg://{settings.DATABASE_USER}:{settings.DATABASE_PASSWORD}"
    f"@{settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}"
)


def get_database_url() -> str:
    """Get the database URL for migrations.

    Phase 16 P1-12: this used to rewrite postgresql+asyncpg:// to
    postgresql+py:// — a dialect that does not exist in SQLAlchemy — so
    every migration died at engine creation. run_migrations_online drives
    the async engine (asyncpg), so the URL must stay as configured.
    """
    return DATABASE_URL


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a connection
    with the context.
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def run_async_migrations():
        """Run migrations asynchronously."""
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
