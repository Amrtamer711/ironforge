"""
AI Cost Tracking Utilities

OpenAI Pricing (as of 2025):
- GPT-5 with reasoning:
  - Input: $2.50 / 1M tokens
  - Output: $10.00 / 1M tokens
  - Reasoning: $10.00 / 1M tokens (cached at 50% after first use)

- GPT-4.1:
  - Input: $0.30 / 1M tokens
  - Output: $1.20 / 1M tokens
"""

import logging
from typing import Optional
import db

logger = logging.getLogger("proposal-bot")

# Pricing per 1M tokens (in dollars)
PRICING = {
    "gpt-5": {
        "input": 1.25,
        "output": 10.00,
        "reasoning": 10.00,
        "reasoning_cached": 5.00  # 50% discount for cached reasoning
    },
    "gpt-4.1": {
        "input": 0.30,
        "output": 1.20,
        "reasoning": 0.00  # GPT-4.1 doesn't have reasoning
    },
    "gpt-4": {
        "input": 0.30,
        "output": 1.20,
        "reasoning": 0.00
    }
}


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int = 0,
    reasoning_cached: bool = False
) -> dict:
    """
    Calculate cost breakdown for an AI API call

    Args:
        model: Model name (gpt-5, gpt-4.1, etc.)
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        reasoning_tokens: Number of reasoning tokens (GPT-5 only)
        reasoning_cached: Whether reasoning tokens are cached (50% off)

    Returns:
        Dict with:
            - input_cost: Cost for input tokens
            - output_cost: Cost for output tokens
            - reasoning_cost: Cost for reasoning tokens
            - total_cost: Total cost
    """
    # Get pricing for model (default to gpt-5 if unknown)
    pricing = PRICING.get(model, PRICING["gpt-5"])

    # Calculate costs (per million tokens)
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]

    if reasoning_tokens > 0 and reasoning_cached:
        reasoning_cost = (reasoning_tokens / 1_000_000) * pricing["reasoning_cached"]
    else:
        reasoning_cost = (reasoning_tokens / 1_000_000) * pricing["reasoning"]

    total_cost = input_cost + output_cost + reasoning_cost

    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "reasoning_cost": reasoning_cost,
        "total_cost": total_cost
    }


def track_openai_call(
    response: any,
    call_type: str,
    user_id: Optional[str] = None,
    context: Optional[str] = None,
    metadata: Optional[dict] = None
):
    """
    Track OpenAI API call costs from a response object

    Args:
        response: OpenAI API response object
        call_type: Type of call (classification, parsing, coordinator_thread, main_llm, etc.)
        user_id: Slack user ID (optional)
        context: Additional context (optional)
        metadata: Additional metadata dict (optional)
    """
    try:
        # Extract usage from response
        usage = response.usage if hasattr(response, 'usage') else None
        if not usage:
            logger.warning(f"[COSTS] No usage data in response for {call_type}")
            return

        # Get token counts
        input_tokens = getattr(usage, 'input_tokens', 0) or 0
        output_tokens = getattr(usage, 'output_tokens', 0) or 0

        # Handle reasoning tokens (GPT-5 with reasoning)
        reasoning_tokens = 0
        reasoning_cached = False
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
            reasoning_cached=reasoning_cached
        )

        # Convert metadata to JSON string if provided
        metadata_json = None
        if metadata:
            import json
            metadata_json = json.dumps(metadata)

        # Log to database
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
            user_id=user_id,
            context=context,
            metadata_json=metadata_json
        )

        logger.info(
            f"[COSTS] {call_type} | Model: {model} | "
            f"Tokens: {input_tokens}in + {output_tokens}out + {reasoning_tokens}reasoning | "
            f"Cost: ${costs['total_cost']:.4f}"
        )

    except Exception as e:
        logger.error(f"[COSTS] Failed to track OpenAI call: {e}", exc_info=True)


def track_image_generation(
    model: str,
    size: str,
    quality: str,
    n: int = 1,
    user_id: Optional[str] = None,
    context: Optional[str] = None,
    metadata: Optional[dict] = None
):
    """
    Track OpenAI image generation costs

    Args:
        model: Image model (gpt-image-1, dall-e-3, etc.)
        size: Image size (e.g., "1024x1024", "1536x1024")
        quality: Image quality ("standard" or "high")
        n: Number of images generated
        user_id: Slack user ID or "website_mockup" for public API
        context: Additional context (optional)
        metadata: Additional metadata dict (optional)
    """
    try:
        # Image generation pricing (per image)
        # gpt-image-1 / DALL-E 3:
        #   - 1024x1024: standard $0.040, high $0.080
        #   - 1024x1792 or 1792x1024: standard $0.080, high $0.120

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
        # For image generation, we don't have token counts, so set to 0
        db.log_ai_cost(
            call_type="image_generation",
            model=model,
            input_tokens=0,  # Not applicable for image generation
            output_tokens=0,  # Not applicable for image generation
            reasoning_tokens=0,
            input_cost=0.0,
            output_cost=0.0,
            reasoning_cost=0.0,
            total_cost=total_cost,
            user_id=user_id,
            context=context,
            metadata_json=metadata_json
        )

        logger.info(
            f"[COSTS] image_generation | Model: {model} | "
            f"Size: {size}, Quality: {quality}, Count: {n} | "
            f"Cost: ${total_cost:.4f}"
        )

    except Exception as e:
        logger.error(f"[COSTS] Failed to track image generation: {e}", exc_info=True)
