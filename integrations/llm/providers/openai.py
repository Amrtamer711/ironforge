"""
OpenAI LLM Provider Implementation.

Text completions: responses.create() API
- instructions: System/developer message
- input: User/assistant messages array
- reasoning: {effort: "none"|"minimal"|"low"|"medium"|"high"}
- max_output_tokens: Max tokens to generate
- text.format: For structured outputs (json_schema)
- Response: output[].content[].text or response.output_text

Image generation: gpt-image-1 via images.generate()
- prompt: max 32000 chars
- quality: "low", "medium", "high" (passed directly, NOT hd/standard)
- size: "1024x1024", "1536x1024" (landscape), "1024x1536" (portrait), "auto"
- n: 1-10 images
- Always returns b64_json (no response_format param)
- Response: img.data[0].b64_json
- Usage: {input_tokens, output_tokens, input_tokens_details: {text_tokens, image_tokens}}
"""

import base64
import logging
from typing import Any, Dict, List, Optional, Union

from openai import AsyncOpenAI

from integrations.llm.base import (
    CostInfo,
    FileReference,
    ImageResponse,
    JSONSchema,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    RawTool,
    ReasoningEffort,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)

logger = logging.getLogger("proposal-bot")

# ============================================================================
# PRICING (per 1M tokens)
# ============================================================================

OPENAI_PRICING = {
    # Text models
    "gpt-5.1": {
        "input": 1.25,
        "input_cached": 0.125,
        "output": 10.00,
    },
    "gpt-5": {
        "input": 1.25,
        "input_cached": 0.125,
        "output": 10.00,
    },
    "gpt-4.1": {
        "input": 0.30,
        "input_cached": 0.03,
        "output": 1.20,
    },
    # Image models (token-based pricing)
    "gpt-image-1": {
        "text_input": 5.00,
        "text_input_cached": 1.25,
        "image_input": 10.00,
        "image_input_cached": 2.50,
        "output": 40.00,
    },
}


class OpenAIProvider(LLMProvider):
    """
    OpenAI API implementation.

    Text: responses.create() with input= parameter
    Images: images.generate() for gpt-image-1
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "gpt-5.1",
        default_image_model: str = "gpt-image-1",
    ):
        self._client = AsyncOpenAI(api_key=api_key)
        self._default_model = default_model
        self._default_image_model = default_image_model

    @property
    def name(self) -> str:
        return "openai"

    @property
    def client(self) -> AsyncOpenAI:
        """Access to raw client for advanced use cases."""
        return self._client

    # ========================================================================
    # TEXT COMPLETIONS
    # ========================================================================

    async def complete(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        tools: Optional[List[ToolDefinition]] = None,
        tool_choice: Optional[str] = None,
        json_schema: Optional[JSONSchema] = None,
        reasoning: Optional[ReasoningEffort] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        store: bool = False,
        cache_key: Optional[str] = None,
        cache_retention: Optional[str] = None,
    ) -> LLMResponse:
        """
        Generate completion using OpenAI's responses.create API.

        OpenAI Responses API specifics:
        - instructions: System/developer message (separate from input)
        - input: User/assistant messages array
        - reasoning: {effort: "none"|"minimal"|"low"|"medium"|"high"}
        - max_output_tokens: Max tokens to generate (not max_tokens)
        - text.format: For structured outputs (json_schema)

        Prompt Caching (gpt-5.1, gpt-5, gpt-4.1):
        - cache_key: Stable identifier for routing (e.g., "proposal-system")
        - cache_retention: "in_memory" (default, 5-10 min) or "24h" (extended)
        - Caching is automatic for prompts 1024+ tokens
        - Up to 90% input cost reduction, 80% latency reduction
        """
        model = model or self._default_model

        # Separate system message (-> instructions) from conversation (-> input)
        instructions = None
        input_messages = []

        for msg in messages:
            if msg.role == "system":
                # System messages go to instructions parameter
                instructions = msg.content if isinstance(msg.content, str) else str(msg.content)
            else:
                # User/assistant messages go to input
                input_messages.append({"role": msg.role, "content": msg.content})

        # Build request
        kwargs: Dict[str, Any] = {
            "model": model,
            "input": input_messages,
            "store": store,
        }

        # Add instructions (system message) if present
        if instructions:
            kwargs["instructions"] = instructions

        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            if tool_choice:
                kwargs["tool_choice"] = tool_choice

        if json_schema:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": json_schema.name,
                    "schema": json_schema.schema,
                    "strict": json_schema.strict,
                }
            }

        if reasoning:
            kwargs["reasoning"] = {"effort": reasoning.value}

        if temperature is not None:
            kwargs["temperature"] = temperature

        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens

        # Prompt caching options (gpt-5.1, gpt-5, gpt-4.1 support extended caching)
        if cache_key:
            kwargs["prompt_cache_key"] = cache_key
        if cache_retention:
            kwargs["prompt_cache_retention"] = cache_retention

        response = await self._client.responses.create(**kwargs)
        return self._parse_text_response(response, model)

    # ========================================================================
    # IMAGE GENERATION (gpt-image-1)
    # ========================================================================

    async def generate_image(
        self,
        prompt: str,
        quality: str = "high",
        orientation: str = "landscape",
        n: int = 1,
    ) -> ImageResponse:
        """
        Generate image using gpt-image-1.

        Args:
            prompt: Text description (max 32000 chars for gpt-image-1)
            quality: "low", "medium", or "high" - passed directly to API
            orientation: "portrait" or "landscape" - mapped to size

        gpt-image-1 sizes (from docs):
        - 1024x1024 (square)
        - 1536x1024 (landscape)
        - 1024x1536 (portrait)
        """
        model = self._default_image_model

        # Map orientation to gpt-image-1 size
        if orientation == "portrait":
            size = "1024x1536"
        else:  # landscape
            size = "1536x1024"

        logger.info(f"[OPENAI] Generating {n} image(s): model={model}, size={size}, quality={quality}")

        # Call gpt-image-1 API
        # Note: gpt-image-1 always returns b64_json, no response_format needed
        response = await self._client.images.generate(
            model=model,
            prompt=prompt,
            n=n,
            size=size,
            quality=quality,
        )

        # Extract images from response.data[].b64_json
        images = []
        for img_data in response.data:
            if img_data.b64_json:
                images.append(base64.b64decode(img_data.b64_json))

        # Parse usage and calculate cost
        usage = None
        cost = None
        if hasattr(response, "usage") and response.usage:
            usage = self._parse_image_usage(response.usage)
            cost = self._calculate_image_cost(model, usage, n)

        return ImageResponse(
            images=images,
            model=model,
            usage=usage,
            cost=cost,
            raw_response=response,
        )

    # ========================================================================
    # FILE OPERATIONS
    # ========================================================================

    async def upload_file(
        self,
        file_path: str,
        purpose: str = "user_data",
    ) -> FileReference:
        """Upload a file to OpenAI."""
        with open(file_path, "rb") as f:
            file_obj = await self._client.files.create(file=f, purpose=purpose)

        logger.info(f"[OPENAI] Uploaded file: {file_obj.id}")
        return FileReference(file_id=file_obj.id, provider=self.name)

    async def delete_file(self, file_ref: FileReference) -> bool:
        """Delete a file from OpenAI."""
        if file_ref.provider != self.name:
            logger.warning(f"[OPENAI] Cannot delete file from provider: {file_ref.provider}")
            return False

        try:
            await self._client.files.delete(file_ref.file_id)
            logger.info(f"[OPENAI] Deleted file: {file_ref.file_id}")
            return True
        except Exception as e:
            logger.warning(f"[OPENAI] Failed to delete file {file_ref.file_id}: {e}")
            return False

    # ========================================================================
    # INTERNAL: PARSING & COST CALCULATION
    # ========================================================================

    def _convert_tools(
        self, tools: List[Union[ToolDefinition, RawTool]]
    ) -> List[Dict[str, Any]]:
        """Convert tool definitions to OpenAI format."""
        result = []
        for tool in tools:
            if isinstance(tool, RawTool):
                result.append(tool.raw)
            else:
                result.append({
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                })
        return result

    def _parse_text_response(self, response: Any, model: str) -> LLMResponse:
        """Parse text completion response."""
        content = ""
        tool_calls = []

        if hasattr(response, "output") and response.output:
            for item in response.output:
                if hasattr(item, "type"):
                    if item.type == "message" and hasattr(item, "content"):
                        for content_item in item.content:
                            if hasattr(content_item, "text"):
                                content = content_item.text
                    elif item.type == "function_call":
                        import json
                        tool_calls.append(
                            ToolCall(
                                id=getattr(item, "call_id", ""),
                                name=getattr(item, "name", ""),
                                arguments=json.loads(getattr(item, "arguments", "{}")),
                            )
                        )

        # Check for direct output_text (structured outputs)
        if hasattr(response, "output_text") and response.output_text:
            content = response.output_text

        # Parse usage
        usage = None
        cost = None
        if hasattr(response, "usage") and response.usage:
            usage = self._parse_text_usage(response.usage)
            cost = self._calculate_text_cost(model, usage)

        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
            cost=cost,
            tool_calls=tool_calls if tool_calls else None,
            raw_response=response,
        )

    def _parse_text_usage(self, usage: Any) -> TokenUsage:
        """
        Parse text completion usage.

        Structure:
        {
            "input_tokens": 328,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 52,
            "output_tokens_details": {"reasoning_tokens": 0}
        }
        """
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        cached_input_tokens = 0
        if hasattr(usage, "input_tokens_details"):
            cached_input_tokens = getattr(usage.input_tokens_details, "cached_tokens", 0) or 0

        reasoning_tokens = 0
        if hasattr(usage, "output_tokens_details"):
            reasoning_tokens = getattr(usage.output_tokens_details, "reasoning_tokens", 0) or 0

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
        )

    def _parse_image_usage(self, usage: Any) -> TokenUsage:
        """
        Parse gpt-image-1 usage.

        Structure (from docs):
        {
            "total_tokens": 100,
            "input_tokens": 50,
            "output_tokens": 50,
            "input_tokens_details": {
                "text_tokens": 10,
                "image_tokens": 40
            }
        }
        """
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        text_input_tokens = 0
        image_input_tokens = 0
        if hasattr(usage, "input_tokens_details"):
            details = usage.input_tokens_details
            text_input_tokens = getattr(details, "text_tokens", 0) or 0
            image_input_tokens = getattr(details, "image_tokens", 0) or 0

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            text_input_tokens=text_input_tokens,
            image_input_tokens=image_input_tokens,
        )

    def _calculate_text_cost(self, model: str, usage: TokenUsage) -> CostInfo:
        """Calculate cost for text completion."""
        pricing = OPENAI_PRICING.get(model, OPENAI_PRICING.get("gpt-5", {}))

        non_cached = usage.input_tokens - usage.cached_input_tokens
        input_cost = (non_cached / 1_000_000) * pricing.get("input", 0)
        input_cost += (usage.cached_input_tokens / 1_000_000) * pricing.get(
            "input_cached", pricing.get("input", 0) * 0.1
        )

        output_cost = (usage.output_tokens / 1_000_000) * pricing.get("output", 0)

        reasoning_cost = 0.0
        if usage.reasoning_tokens > 0:
            reasoning_rate = pricing.get("reasoning", pricing.get("output", 0))
            reasoning_cost = (usage.reasoning_tokens / 1_000_000) * reasoning_rate

        return CostInfo(
            provider=self.name,
            model=model,
            total_cost=input_cost + output_cost + reasoning_cost,
            input_cost=input_cost,
            output_cost=output_cost,
            reasoning_cost=reasoning_cost,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_tokens=usage.cached_input_tokens,
            reasoning_tokens=usage.reasoning_tokens,
        )

    def _calculate_image_cost(self, model: str, usage: TokenUsage, n: int) -> CostInfo:
        """Calculate cost for gpt-image-1 generation."""
        pricing = OPENAI_PRICING.get(model, OPENAI_PRICING.get("gpt-image-1", {}))

        text_cost = (usage.text_input_tokens / 1_000_000) * pricing.get("text_input", 5.0)
        image_cost = (usage.image_input_tokens / 1_000_000) * pricing.get("image_input", 10.0)
        output_cost = (usage.output_tokens / 1_000_000) * pricing.get("output", 40.0)

        return CostInfo(
            provider=self.name,
            model=model,
            total_cost=text_cost + image_cost + output_cost,
            input_cost=text_cost + image_cost,
            output_cost=output_cost,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            image_count=n,
        )
