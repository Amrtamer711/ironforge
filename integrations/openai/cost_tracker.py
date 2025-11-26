"""
AI Cost Tracking Utilities

OpenAI Pricing (as of January 2025):

GPT-5 (Text):
  - Input: $1.250 / 1M tokens
  - Cached Input: $0.125 / 1M tokens (90% discount)
  - Output: $10.000 / 1M tokens

GPT-image-1 (Image Generation):
  Text Input:
    - Input: $5.00 / 1M tokens
    - Cached Input: $1.25 / 1M tokens
  Image Input:
    - Input: $10.00 / 1M tokens
    - Cached Input: $2.50 / 1M tokens
    - Output: $40.00 / 1M tokens

GPT-image-1-mini:
  Text Input:
    - Input: $2.00 / 1M tokens
    - Cached Input: $0.20 / 1M tokens
  Image Input:
    - Input: $2.50 / 1M tokens
    - Cached Input: $0.25 / 1M tokens
    - Output: $8.00 / 1M tokens
"""

import logging
from typing import Optional
from data.database import db

logger = logging.getLogger("proposal-bot")

# Pricing per 1M tokens (in dollars)
PRICING = {
    "gpt-5": {
        "input": 1.25,
        "input_cached": 0.125,  # 90% discount
        "output": 10.00,
        "reasoning": 0.00  # GPT-5 doesn't have separate reasoning pricing
    },
    "gpt-image-1": {
        "text_input": 5.00,
        "text_input_cached": 1.25,
        "image_input": 10.00,
        "image_input_cached": 2.50,
        "output": 40.00
    },
    "gpt-image-1-mini": {
        "text_input": 2.00,
        "text_input_cached": 0.20,
        "image_input": 2.50,
        "image_input_cached": 0.25,
        "output": 8.00
    },
    "gpt-4.1": {
        "input": 0.30,
        "input_cached": 0.03,
        "output": 1.20,
        "reasoning": 0.00
    },
    "gpt-4": {
        "input": 0.30,
        "input_cached": 0.03,
        "output": 1.20,
        "reasoning": 0.00
    }
}


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int = 0,
    cached_input_tokens: int = 0
) -> dict:
    """
    Calculate cost breakdown for an AI API call

    Args:
        model: Model name (gpt-5, gpt-4.1, etc.)
        input_tokens: Number of input tokens (total, including cached)
        output_tokens: Number of output tokens
        reasoning_tokens: Number of reasoning tokens (note: GPT-5 no longer charges separately for reasoning)
        cached_input_tokens: Number of cached input tokens (charged at 90% discount)

    Returns:
        Dict with:
            - input_cost: Cost for input tokens (non-cached + cached)
            - output_cost: Cost for output tokens
            - reasoning_cost: Cost for reasoning tokens (always 0 for GPT-5)
            - total_cost: Total cost
    """
    # Get pricing for model (default to gpt-5 if unknown)
    pricing = PRICING.get(model, PRICING["gpt-5"])

    # Calculate non-cached input tokens
    non_cached_input_tokens = input_tokens - cached_input_tokens

    # Calculate costs (per million tokens)
    # Non-cached input tokens at regular price
    non_cached_input_cost = (non_cached_input_tokens / 1_000_000) * pricing["input"]
    # Cached input tokens at discounted price (90% discount)
    cached_input_cost = (cached_input_tokens / 1_000_000) * pricing.get("input_cached", pricing["input"] * 0.1)
    input_cost = non_cached_input_cost + cached_input_cost

    output_cost = (output_tokens / 1_000_000) * pricing["output"]

    # Reasoning cost - GPT-5 no longer charges separately for reasoning
    # Reasoning tokens are included in regular output token cost
    reasoning_cost = (reasoning_tokens / 1_000_000) * pricing.get("reasoning", 0.0)

    total_cost = input_cost + output_cost + reasoning_cost

    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "reasoning_cost": reasoning_cost,
        "total_cost": total_cost
    }


def get_user_name_sync(user_id: Optional[str]) -> Optional[str]:
    """
    Get user's real name from Slack synchronously.
    Returns the real name or None if lookup fails.
    """
    if not user_id:
        return None

    try:
        import asyncio
        from bo_slack_messaging import get_user_real_name

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


def track_openai_call(
    response: any,
    call_type: str,
    user_id: Optional[str] = None,
    workflow: Optional[str] = None,
    context: Optional[str] = None,
    metadata: Optional[dict] = None
):
    """
    Track OpenAI API call costs from a response object

    Args:
        response: OpenAI API response object
        call_type: Type of call (classification, parsing, coordinator_thread, main_llm, etc.)
        user_id: Slack user ID (optional) - will be converted to user name
        workflow: Workflow type - mockup_upload, mockup_ai, bo_parsing, bo_editing, bo_revision, proposal_generation, general_chat, location_management (optional)
        context: Additional context (optional)
        metadata: Additional metadata dict (optional)
    """
    try:
        # Note: user_id parameter should already be the user name (converted by caller)
        user_name = user_id
        # Extract usage from response
        usage = response.usage if hasattr(response, 'usage') else None
        if not usage:
            logger.warning(f"[COSTS] No usage data in response for {call_type}")
            return

        # Get token counts
        input_tokens = getattr(usage, 'input_tokens', 0) or 0
        output_tokens = getattr(usage, 'output_tokens', 0) or 0

        # Handle cached input tokens (90% discount)
        cached_input_tokens = 0
        if hasattr(usage, 'input_tokens_details'):
            input_details = usage.input_tokens_details
            cached_input_tokens = getattr(input_details, 'cached_tokens', 0) or 0

        # Handle reasoning tokens (for tracking purposes - GPT-5 no longer charges separately)
        reasoning_tokens = 0
        if hasattr(usage, 'output_tokens_details'):
            details = usage.output_tokens_details
            reasoning_tokens = getattr(details, 'reasoning_tokens', 0) or 0

        # Get model from response
        model = getattr(response, 'model', 'unknown')

        # Calculate costs
        costs = calculate_cost(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens
        )

        # Convert metadata to JSON string if provided
        metadata_json = None
        if metadata:
            import json
            metadata_json = json.dumps(metadata)

        # Log to database with user_name instead of user_id
        db.log_ai_cost(
            call_type=call_type,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            input_cost=costs["input_cost"],
            output_cost=costs["output_cost"],
            reasoning_cost=costs["reasoning_cost"],
            total_cost=costs["total_cost"],
            user_id=user_name,  # Store user name, not ID
            workflow=workflow,
            cached_input_tokens=cached_input_tokens,
            context=context,
            metadata_json=metadata_json
        )

        # Log with cached token info if applicable
        if cached_input_tokens > 0:
            logger.info(
                f"[COSTS] {call_type} | Model: {model} | "
                f"Tokens: {input_tokens}in ({cached_input_tokens} cached) + {output_tokens}out + {reasoning_tokens}reasoning | "
                f"Cost: ${costs['total_cost']:.4f}"
            )
        else:
            logger.info(
                f"[COSTS] {call_type} | Model: {model} | "
                f"Tokens: {input_tokens}in + {output_tokens}out + {reasoning_tokens}reasoning | "
                f"Cost: ${costs['total_cost']:.4f}"
            )

    except Exception as e:
        logger.error(f"[COSTS] Failed to track OpenAI call: {e}", exc_info=True)
        raise  # Re-raise to make errors visible in INFO logs


def track_image_generation(
    response: any = None,
    model: str = None,
    size: str = None,
    quality: str = None,
    n: int = 1,
    user_id: Optional[str] = None,
    workflow: Optional[str] = None,
    context: Optional[str] = None,
    metadata: Optional[dict] = None
):
    """
    Track OpenAI image generation costs from API response or fallback to fixed pricing

    Args:
        response: OpenAI image generation response object (optional, preferred)
        model: Image model (gpt-image-1, dall-e-3, etc.) - fallback if no response
        size: Image size (e.g., "1024x1024") - fallback if no response
        quality: Image quality ("standard" or "high") - fallback if no response
        n: Number of images generated - fallback if no response
        user_id: Slack user ID or "website_mockup" for public API - will be converted to user name
        workflow: Workflow type - typically 'mockup_ai' for AI-generated mockups (optional)
        context: Additional context (optional)
        metadata: Additional metadata dict (optional)
    """
    try:
        # Note: user_id parameter should already be the user name (converted by caller)
        user_name = user_id
        # Try to extract usage from response first (token-based pricing)
        if response and hasattr(response, 'usage') and response.usage:
            usage = response.usage

            # Extract token counts
            total_input_tokens = getattr(usage, 'input_tokens', 0) or 0
            output_tokens = getattr(usage, 'output_tokens', 0) or 0

            # Extract input token details (text vs image tokens)
            text_input_tokens = 0
            image_input_tokens = 0
            if hasattr(usage, 'input_tokens_details'):
                details = usage.input_tokens_details
                text_input_tokens = getattr(details, 'text_tokens', 0) or 0
                image_input_tokens = getattr(details, 'image_tokens', 0) or 0

            # Get model from response if not provided
            if not model:
                model = getattr(response, 'model', 'gpt-image-1')

            # Calculate costs using token-based pricing
            # gpt-image-1: $5/1M text input, $10/1M image input, $40/1M output
            pricing = PRICING.get(model, PRICING.get("gpt-image-1", {}))

            text_input_cost = (text_input_tokens / 1_000_000) * pricing.get("text_input", 5.0)
            image_input_cost = (image_input_tokens / 1_000_000) * pricing.get("image_input", 10.0)
            output_cost = (output_tokens / 1_000_000) * pricing.get("output", 40.0)

            total_cost = text_input_cost + image_input_cost + output_cost

            # Convert metadata to JSON string if provided
            metadata_json = None
            if metadata:
                import json
                metadata_json = json.dumps(metadata)

            # Log to database with token details
            db.log_ai_cost(
                call_type="image_generation",
                model=model,
                input_tokens=total_input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=0,
                input_cost=text_input_cost + image_input_cost,
                output_cost=output_cost,
                reasoning_cost=0.0,
                total_cost=total_cost,
                user_id=user_name,  # Store user name, not ID
                workflow=workflow,
                context=context,
                metadata_json=metadata_json
            )

            logger.info(
                f"[COSTS] image_generation | Model: {model} | "
                f"Tokens: {text_input_tokens}text + {image_input_tokens}img + {output_tokens}out | "
                f"Cost: ${total_cost:.4f}"
            )

        else:
            # Fallback to fixed pricing if no usage data
            # gpt-image-1 / DALL-E 3:
            #   - 1024x1024: standard $0.040, high $0.080
            #   - 1024x1792 or 1792x1024: standard $0.080, high $0.120

            if not model or not size or not quality:
                logger.warning("[COSTS] image_generation called without response or required params, skipping")
                return

            # Determine pricing based on size and quality
            if "1792" in size or "1536" in size:
                # Large format
                cost_per_image = 0.120 if quality == "high" else 0.080
            else:
                # Standard 1024x1024
                cost_per_image = 0.080 if quality == "high" else 0.040

            total_cost = cost_per_image * n

            # Convert metadata to JSON string if provided
            metadata_json = None
            if metadata:
                import json
                metadata_json = json.dumps(metadata)

            # Log to database
            db.log_ai_cost(
                call_type="image_generation",
                model=model,
                input_tokens=0,  # Fixed pricing, no token data
                output_tokens=0,
                reasoning_tokens=0,
                input_cost=0.0,
                output_cost=0.0,
                reasoning_cost=0.0,
                total_cost=total_cost,
                user_id=user_name,  # Store user name, not ID
                workflow=workflow,
                context=context,
                metadata_json=metadata_json
            )

            logger.info(
                f"[COSTS] image_generation | Model: {model} | "
                f"Size: {size}, Quality: {quality}, Count: {n} | "
                f"Cost: ${total_cost:.4f} (fixed pricing)"
            )

    except Exception as e:
        logger.error(f"[COSTS] Failed to track image generation: {e}", exc_info=True)
        raise  # Re-raise to make errors visible in INFO logs
