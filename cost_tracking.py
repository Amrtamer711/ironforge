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
import db

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
    reasoning_tokens: int = 0
) -> dict:
    """
    Calculate cost breakdown for an AI API call

    Args:
        model: Model name (gpt-5, gpt-4.1, etc.)
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        reasoning_tokens: Number of reasoning tokens (note: GPT-5 no longer charges separately for reasoning)

    Returns:
        Dict with:
            - input_cost: Cost for input tokens
            - output_cost: Cost for output tokens
            - reasoning_cost: Cost for reasoning tokens (always 0 for GPT-5)
            - total_cost: Total cost
    """
    # Get pricing for model (default to gpt-5 if unknown)
    pricing = PRICING.get(model, PRICING["gpt-5"])

    # Calculate costs (per million tokens)
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
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
        user_id: Slack user ID (optional)
        workflow: Workflow type - mockup_upload, mockup_ai, bo_parsing, bo_editing, bo_revision, proposal_generation, general_chat, location_management (optional)
        context: Additional context (optional)
        metadata: Additional metadata dict (optional)
    """
    try:
        # Log full response structure for debugging
        logger.info(f"[COSTS DEBUG] ===== {call_type} API Response Structure =====")
        logger.info(f"[COSTS DEBUG] Response type: {type(response)}")
        logger.info(f"[COSTS DEBUG] Response dir: {dir(response)}")

        # Extract usage from response
        usage = response.usage if hasattr(response, 'usage') else None
        if not usage:
            logger.warning(f"[COSTS] No usage data in response for {call_type}")
            return

        logger.info(f"[COSTS DEBUG] Usage object: {usage}")
        logger.info(f"[COSTS DEBUG] Usage type: {type(usage)}")
        logger.info(f"[COSTS DEBUG] Usage dir: {dir(usage)}")

        # Get token counts
        input_tokens = getattr(usage, 'input_tokens', 0) or 0
        output_tokens = getattr(usage, 'output_tokens', 0) or 0
        logger.info(f"[COSTS DEBUG] Base tokens - Input: {input_tokens}, Output: {output_tokens}")

        # Handle reasoning tokens (for tracking purposes - GPT-5 no longer charges separately)
        reasoning_tokens = 0
        if hasattr(usage, 'output_tokens_details'):
            details = usage.output_tokens_details
            logger.info(f"[COSTS DEBUG] Output tokens details: {details}")
            logger.info(f"[COSTS DEBUG] Details type: {type(details)}")
            logger.info(f"[COSTS DEBUG] Details dir: {dir(details)}")
            reasoning_tokens = getattr(details, 'reasoning_tokens', 0) or 0
            logger.info(f"[COSTS DEBUG] Reasoning tokens: {reasoning_tokens}")

        # Get model from response
        model = getattr(response, 'model', 'unknown')
        logger.info(f"[COSTS DEBUG] Model: {model}")

        # Calculate costs
        costs = calculate_cost(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens
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
            workflow=workflow,
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
    workflow: Optional[str] = None,
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
        workflow: Workflow type - typically 'mockup_ai' for AI-generated mockups (optional)
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
            workflow=workflow,
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
