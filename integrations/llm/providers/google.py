"""
Google Gemini LLM Provider Implementation.

Text completions: gemini-2.5-flash, gemini-2.5-pro via models.generate_content()
Image generation: gemini-3-pro-image-preview (Nano Banana Pro) via models.generate_content()

gemini-3-pro-image-preview API (from nano_doc.txt):
- contents: [prompt] or [prompt, image1, image2, ...]
- config: GenerateContentConfig with image_config for aspect_ratio and image_size
- image_size: "1K", "2K", "4K" (uppercase K required)
- aspect_ratio: "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"
- Response: response.parts contains text and inline_data
- Thinking mode: thought=true images are interim reasoning (not charged), skip them
- thought_signature: used for multi-turn, handled automatically by SDK
"""

import base64
import logging
from typing import Any, Dict, List, Optional, Union

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
# PRICING
# ============================================================================

# Text models (per 1M tokens)
GEMINI_TEXT_PRICING = {
    "gemini-2.5-flash": {
        "input": 0.15,
        "input_cached": 0.0375,
        "output": 0.60,
        "thinking_output": 3.50,
    },
    "gemini-2.5-pro": {
        "input": 1.25,
        "input_cached": 0.3125,
        "output": 10.00,
        "thinking_output": 10.00,
    },
}

# Image models (per image, by resolution)
GEMINI_IMAGE_PRICING = {
    "gemini-3-pro-image-preview": {
        "1K": 0.040,
        "2K": 0.080,
        "4K": 0.160,
    },
}


class GoogleProvider(LLMProvider):
    """
    Google Gemini API implementation.

    Fixed models per task type:
    - Text: gemini-2.5-flash via models.generate_content()
    - Images: gemini-3-pro-image-preview via models.generate_content() (4K)
    """

    # Fixed models - one per task type
    TEXT_MODEL = "gemini-2.5-flash"
    IMAGE_MODEL = "gemini-3-pro-image-preview"

    def __init__(self, api_key: str):
        try:
            from google import genai
            from google.genai import types
            self._genai = genai
            self._types = types
            self._client = genai.Client(api_key=api_key)
        except ImportError:
            raise ImportError(
                "Google GenAI SDK not installed. Install with: pip install google-genai"
            )

    @property
    def name(self) -> str:
        return "google"

    @property
    def client(self):
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
        """Generate completion using Gemini's generate_content API.

        Note: cache_key and cache_retention are OpenAI-specific and ignored here.
        Gemini has its own caching mechanism via Context Caching API.
        """
        model = model or self.TEXT_MODEL

        # Separate system message from conversation
        system_instruction = None
        contents = []

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content if isinstance(msg.content, str) else str(msg.content)
            else:
                role = "user" if msg.role == "user" else "model"
                if isinstance(msg.content, str):
                    contents.append({"role": role, "parts": [{"text": msg.content}]})
                else:
                    # Multimodal content
                    parts = []
                    for item in msg.content:
                        if item.get("type") == "input_text":
                            parts.append({"text": item["text"]})
                        elif item.get("type") == "image_url":
                            url = item["image_url"]["url"]
                            if url.startswith("data:"):
                                header, data = url.split(",", 1)
                                mime_type = header.split(":")[1].split(";")[0]
                                parts.append({"inline_data": {"mime_type": mime_type, "data": data}})
                    contents.append({"role": role, "parts": parts})

        # Build config
        config_kwargs = {}
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens
        if json_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = json_schema.schema

        config = self._types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        # Build request
        kwargs = {"model": model, "contents": contents}
        if system_instruction:
            kwargs["system_instruction"] = system_instruction
        if config:
            kwargs["config"] = config
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self._client.models.generate_content(**kwargs)
        return self._parse_text_response(response, model)

    # ========================================================================
    # IMAGE GENERATION (gemini-3-pro-image-preview)
    # ========================================================================

    async def generate_image(
        self,
        prompt: str,
        quality: str = "high",
        orientation: str = "landscape",
        n: int = 1,
    ) -> ImageResponse:
        """
        Generate image using gemini-3-pro-image-preview (Nano Banana Pro).

        Args:
            prompt: Text description for image generation
            quality: "low" (1K), "medium" (2K), or "high" (4K)
            orientation: "portrait" (2:3) or "landscape" (3:2)
            n: Number of images (generated one at a time)

        gemini-3-pro-image-preview specifics (from docs):
        - image_size: "1K", "2K", "4K" (uppercase K required)
        - aspect_ratio: "2:3" for portrait, "3:2" for landscape
        - Thinking mode: response may contain thought=true images (skip them)
        - Response: response.parts with inline_data
        """
        model = self.IMAGE_MODEL

        # Map quality to resolution
        quality_to_resolution = {
            "low": "1K",
            "medium": "2K",
            "high": "4K",
        }
        image_size = quality_to_resolution.get(quality, "4K")

        # Map orientation to aspect ratio
        if orientation == "portrait":
            aspect_ratio = "2:3"
        else:  # landscape
            aspect_ratio = "3:2"

        logger.info(f"[GOOGLE] Generating {n} image(s): model={model}, size={image_size}, aspect_ratio={aspect_ratio}")

        # Build config with image settings
        config = self._types.GenerateContentConfig(
            image_config=self._types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size=image_size,
            ),
        )

        # Generate images (one at a time for Gemini)
        all_images = []
        raw_responses = []

        for _ in range(n):
            response = self._client.models.generate_content(
                model=model,
                contents=[prompt],
                config=config,
            )
            raw_responses.append(response)

            # TEMPORARY: Log full response for debugging
            logger.info(f"[GOOGLE] === RAW IMAGE RESPONSE START ===")
            logger.info(f"[GOOGLE] Response type: {type(response)}")
            logger.info(f"[GOOGLE] Response dir: {[attr for attr in dir(response) if not attr.startswith('_')]}")
            logger.info(f"[GOOGLE] Response repr: {repr(response)}")
            if hasattr(response, 'usage_metadata'):
                logger.info(f"[GOOGLE] usage_metadata: {response.usage_metadata}")
            if hasattr(response, 'model_version'):
                logger.info(f"[GOOGLE] model_version: {response.model_version}")
            if hasattr(response, 'candidates'):
                logger.info(f"[GOOGLE] candidates: {response.candidates}")
            logger.info(f"[GOOGLE] === RAW IMAGE RESPONSE END ===")

            # Extract images from response.parts
            # Skip thought=true images (interim reasoning, not charged)
            for part in response.parts:
                # Check if this is a thinking/interim image
                if getattr(part, 'thought', False):
                    continue

                # Extract final image
                if hasattr(part, 'inline_data') and part.inline_data is not None:
                    image_data = part.inline_data.data
                    if isinstance(image_data, str):
                        all_images.append(base64.b64decode(image_data))
                    else:
                        all_images.append(image_data)

        # Calculate cost
        cost = self._calculate_image_cost(model, image_size, len(all_images))

        return ImageResponse(
            images=all_images,
            model=model,
            usage=None,  # Gemini image gen doesn't return token usage
            cost=cost,
            raw_response=raw_responses[0] if len(raw_responses) == 1 else raw_responses,
        )

    # ========================================================================
    # FILE OPERATIONS
    # ========================================================================

    async def upload_file(
        self,
        file_path: str,
        purpose: str = "user_data",
    ) -> FileReference:
        """
        Upload a file for use in Gemini.

        Note: Gemini typically uses inline base64 data. This stores
        the data as a reference for compatibility with the interface.
        """
        import mimetypes

        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

        with open(file_path, "rb") as f:
            file_data = f.read()

        file_id = f"inline:{mime_type}:{base64.b64encode(file_data).decode('utf-8')}"
        logger.info(f"[GOOGLE] Prepared file for inline use: {file_path}")
        return FileReference(file_id=file_id, provider=self.name)

    async def delete_file(self, file_ref: FileReference) -> bool:
        """Delete file reference (no-op for inline files)."""
        if file_ref.provider != self.name:
            logger.warning(f"[GOOGLE] Cannot delete file from provider: {file_ref.provider}")
            return False

        logger.info(f"[GOOGLE] Cleared file reference")
        return True

    # ========================================================================
    # INTERNAL: PARSING & COST CALCULATION
    # ========================================================================

    def _convert_tools(
        self, tools: List[Union[ToolDefinition, RawTool]]
    ) -> List[Dict[str, Any]]:
        """Convert tool definitions to Gemini format."""
        result = []
        for tool in tools:
            if isinstance(tool, RawTool):
                result.append(tool.raw)
            else:
                result.append({
                    "function_declarations": [{
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    }]
                })
        return result

    def _parse_text_response(self, response: Any, model: str) -> LLMResponse:
        """Parse text completion response."""
        content = ""
        tool_calls = []

        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and candidate.content:
                for part in candidate.content.parts:
                    if hasattr(part, "text") and part.text:
                        content = part.text
                    elif hasattr(part, "function_call"):
                        fc = part.function_call
                        tool_calls.append(
                            ToolCall(
                                id=getattr(fc, "id", ""),
                                name=fc.name,
                                arguments=dict(fc.args) if hasattr(fc, "args") else {},
                            )
                        )

        # Parse usage
        usage = None
        cost = None
        if hasattr(response, "usage_metadata"):
            usage = self._parse_text_usage(response.usage_metadata)
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
        Parse Gemini text usage.

        Structure:
        {
            "prompt_token_count": 328,
            "candidates_token_count": 52,
            "total_token_count": 380,
            "cached_content_token_count": 0,
            "thoughts_token_count": 0  # For thinking models
        }
        """
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        cached_input_tokens = getattr(usage, "cached_content_token_count", 0) or 0
        reasoning_tokens = getattr(usage, "thoughts_token_count", 0) or 0

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            reasoning_tokens=reasoning_tokens,
        )

    def _calculate_text_cost(self, model: str, usage: TokenUsage) -> CostInfo:
        """Calculate cost for text completion."""
        pricing = GEMINI_TEXT_PRICING.get(model, GEMINI_TEXT_PRICING.get("gemini-2.5-flash", {}))

        non_cached = usage.input_tokens - usage.cached_input_tokens
        input_cost = (non_cached / 1_000_000) * pricing.get("input", 0)
        input_cost += (usage.cached_input_tokens / 1_000_000) * pricing.get(
            "input_cached", pricing.get("input", 0) * 0.25
        )

        output_cost = (usage.output_tokens / 1_000_000) * pricing.get("output", 0)

        reasoning_cost = 0.0
        if usage.reasoning_tokens > 0:
            reasoning_rate = pricing.get("thinking_output", pricing.get("output", 0))
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

    def _calculate_image_cost(self, model: str, image_size: str, n: int) -> CostInfo:
        """Calculate cost for image generation."""
        pricing = GEMINI_IMAGE_PRICING.get(model, GEMINI_IMAGE_PRICING.get("gemini-3-pro-image-preview", {}))
        per_image_cost = pricing.get(image_size, pricing.get("1K", 0.040))

        return CostInfo(
            provider=self.name,
            model=model,
            total_cost=per_image_cost * n,
            image_size=image_size,
            image_count=n,
        )
