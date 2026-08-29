"""
Database Base Configuration

Phase 10 - Sprint 1 - Day 3
Purpose: SQLAlchemy declarative base and configuration
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all database models."""

