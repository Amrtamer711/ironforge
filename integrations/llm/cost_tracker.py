"""
Unified AI Cost Tracking

This module provides a centralized, provider-agnostic interface for logging AI API costs
to the database. Each LLM provider calculates its own costs based on its response format
and pricing structure, then passes a normalized CostInfo object here for logging.

The cost tracker maintains data accuracy by preserving all cost breakdowns:
- Input costs (non-cached tokens)
- Cached input costs (discounted tokens)
- Output costs (generated tokens)
- Reasoning costs (thinking/reasoning tokens, separate from output)
- Image costs (per-image or token-based)

All costs are logged with full metadata for analytics and debugging.
"""

import json
import logging
from typing import Any, Dict, Optional

from db.database import db
from integrations.llm.base import CostInfo

logger = logging.getLogger("proposal-bot")


def track_cost(
    cost: CostInfo,
    call_type: str,
    user_id: Optional[str] = None,
    workflow: Optional[str] = None,
    context: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Track AI API costs from a provider-calculated CostInfo object.

    This is the primary entry point for cost tracking. Each LLM provider
    calculates its own costs and returns a CostInfo object, which is then
    logged uniformly here.

    Args:
        cost: CostInfo object from the LLM provider containing calculated costs
        call_type: Type of call (llm_call, image_generation, etc.)
        user_id: User identifier for tracking
        workflow: Workflow type (mockup_ai, proposal_generation, etc.)
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
        # Reasoning tokens are tracked separately from output tokens
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


def get_user_name_sync(user_id: Optional[str]) -> Optional[str]:
    """
    Get user's real name from Slack synchronously.
    Returns the real name or None if lookup fails.
    """
    if not user_id:
        return None

    try:
        import asyncio
        from core.bo_messaging import get_user_real_name

        # Run async function synchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            user_name = loop.run_until_complete(get_user_real_name(user_id))
            return user_name
        finally:
            loop.close()
    except Exception as e:
        logger.warning(f"[COSTS] Failed to get user name for {user_id}: {e}")
        return user_id  # Fall back to ID
