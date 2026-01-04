"""
AI Cost Tracking for Video Critique

This module provides centralized, provider-agnostic interface for logging AI API costs
to the database. Each LLM provider calculates its own costs based on its response format
and pricing structure, then passes a normalized CostInfo object here for logging.
"""

import json
from typing import Any

from crm_llm import CostInfo

from core.utils.logging import get_logger
from db.database import db

logger = get_logger(__name__)


def track_cost(
    cost: CostInfo,
    call_type: str,
    user_id: str | None = None,
    workflow: str | None = None,
    context: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Track AI API costs from a provider-calculated CostInfo object.

    This is the primary entry point for cost tracking. Each LLM provider
    calculates its own costs and returns a CostInfo object, which is then
    logged uniformly here.

    Args:
        cost: CostInfo object from the LLM provider containing calculated costs
        call_type: Type of call (llm_call, vision_call, etc.)
        user_id: User identifier for tracking
        workflow: Workflow type (design_request, task_edit, etc.)
        context: Additional context string
        metadata: Additional metadata dict
    """
    try:
        # Build metadata with provider info
        full_metadata = metadata.copy() if metadata else {}
        full_metadata["provider"] = cost.provider

        # Include all relevant cost breakdown info
        if cost.image_size:
            full_metadata["image_size"] = cost.image_size
        if cost.image_count > 0:
            full_metadata["image_count"] = cost.image_count
        if cost.cached_tokens > 0:
            full_metadata["cached_tokens"] = cost.cached_tokens
        if cost.reasoning_tokens > 0:
            full_metadata["reasoning_tokens"] = cost.reasoning_tokens

        metadata_json = json.dumps(full_metadata) if full_metadata else None

        # Calculate reasoning cost for accurate breakdown
        reasoning_cost = 0.0
        if cost.reasoning_tokens > 0 and cost.reasoning_cost > 0:
            reasoning_cost = cost.reasoning_cost

        # Log to database with full accuracy
        db.log_ai_cost(
            call_type=call_type,
            model=cost.model,
            input_tokens=cost.input_tokens,
            output_tokens=cost.output_tokens,
            reasoning_tokens=cost.reasoning_tokens,
            input_cost=cost.input_cost,
            output_cost=cost.output_cost,
            reasoning_cost=reasoning_cost,
            total_cost=cost.total_cost,
            user_id=user_id,
            workflow=workflow,
            cached_input_tokens=cost.cached_tokens,
            context=context,
            metadata_json=metadata_json,
        )

        # Log detailed summary
        _log_cost_summary(cost, call_type)

    except Exception as e:
        logger.error(f"[COSTS] Failed to track cost: {e}", exc_info=True)


def _log_cost_summary(cost: CostInfo, call_type: str) -> None:
    """Log a detailed cost summary for debugging and monitoring."""
    if cost.image_count > 0:
        # Image analysis
        logger.info(
            f"[COSTS] {call_type} | Provider: {cost.provider} | Model: {cost.model} | "
            f"Images: {cost.image_count} | "
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
