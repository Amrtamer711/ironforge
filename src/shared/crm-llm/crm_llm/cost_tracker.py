"""
Cost Tracking Interface for LLM API calls.

This module provides an abstract interface for cost logging that can be
implemented by consuming applications. The actual database/storage logic
is injected, keeping this library database-agnostic.

Usage:
    # Define your cost logger
    class MyCostLogger(CostLogger):
        def log_cost(self, cost, call_type, user_id, workflow, context, metadata):
            # Log to your database/service
            db.log_ai_cost(...)

    # Pass to LLMClient
    client = LLMClient(provider, cost_logger=MyCostLogger())
"""

import logging
from typing import Any, Protocol

from crm_llm.base import CostInfo

logger = logging.getLogger("crm-llm")


class CostLogger(Protocol):
    """
    Protocol for cost logging implementations.

    Applications implement this to log costs to their preferred storage.
    """

    def log_cost(
        self,
        cost: CostInfo,
        call_type: str,
        user_id: str | None = None,
        workflow: str | None = None,
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Log an AI API cost.

        Args:
            cost: CostInfo object from the LLM provider
            call_type: Type of call (llm_call, image_generation, etc.)
            user_id: User identifier for tracking
            workflow: Workflow type (mockup_ai, proposal_generation, etc.)
            context: Additional context string
            metadata: Additional metadata dict
        """
        ...


class ConsoleCostLogger:
    """
    Simple console-based cost logger for development/debugging.

    Logs costs to the console with detailed breakdown.
    """

    def log_cost(
        self,
        cost: CostInfo,
        call_type: str,
        user_id: str | None = None,
        workflow: str | None = None,
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log cost to console."""
        if cost.image_count > 0:
            # Image generation
            logger.info(
                f"[COSTS] {call_type} | Provider: {cost.provider} | Model: {cost.model} | "
                f"Images: {cost.image_count} ({cost.image_size or 'default'}) | "
                f"Cost: ${cost.total_cost:.4f}"
            )
        elif cost.reasoning_tokens > 0:
            # Completion with reasoning
            logger.info(
                f"[COSTS] {call_type} | Provider: {cost.provider} | Model: {cost.model} | "
                f"Tokens: {cost.input_tokens}in"
                f"{f' ({cost.cached_tokens} cached)' if cost.cached_tokens > 0 else ''} + "
                f"{cost.output_tokens}out + {cost.reasoning_tokens}reasoning | "
                f"Cost: ${cost.total_cost:.4f}"
            )
        elif cost.cached_tokens > 0:
            # Completion with caching
            logger.info(
                f"[COSTS] {call_type} | Provider: {cost.provider} | Model: {cost.model} | "
                f"Tokens: {cost.input_tokens}in ({cost.cached_tokens} cached) + {cost.output_tokens}out | "
                f"Cost: ${cost.total_cost:.4f}"
            )
        else:
            # Standard completion
            logger.info(
                f"[COSTS] {call_type} | Provider: {cost.provider} | Model: {cost.model} | "
                f"Tokens: {cost.input_tokens}in + {cost.output_tokens}out | "
                f"Cost: ${cost.total_cost:.4f}"
            )


class NullCostLogger:
    """
    No-op cost logger that discards all costs.

    Useful when cost tracking is disabled.
    """

    def log_cost(
        self,
        cost: CostInfo,
        call_type: str,
        user_id: str | None = None,
        workflow: str | None = None,
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Discard cost (no-op)."""
        pass
