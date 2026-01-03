"""
Channel adapter implementations for Video Critique.

Each adapter implements the ChannelAdapter interface for a specific platform.
"""

from .slack import SlackAdapter
from .web import WebAdapter

__all__ = [
    "SlackAdapter",
    "WebAdapter",
]
