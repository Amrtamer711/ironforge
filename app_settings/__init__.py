"""
Application settings package for the Sales Proposals Bot.

This package provides centralized, type-safe configuration management
using Pydantic settings.
"""

from app_settings.settings import Settings, settings

__all__ = ["settings", "Settings"]
