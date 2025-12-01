"""
Google Gemini LLM Provider Implementation.

Handles Google Gemini-specific API syntax:
- genai.Client() for API access
- models.generate_content() for completions with response_modalities
- Native image generation with gemini-2.5-flash-image and gemini-3-pro-image-preview
- Multi-turn chat support
- Aspect ratio and resolution configuration
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

# Gemini pricing per 1M tokens (as of 2025)
# https://ai.google.dev/pricing
GEMINI_PRICING = {
    "gemini-2.5-flash": {
        "input": 0.15,
        "input_cached": 0.0375,
        "output": 0.60,
        "thinking_input": 0.15,
        "thinking_output": 3.50,
    },
    "gemini-2.5-pro": {
        "input": 1.25,
        "input_cached": 0.3125,
        "output": 10.00,
        "thinking_input": 1.25,
        "thinking_output": 10.00,
    },
    "gemini-2.0-flash": {
        "input": 0.10,
        "input_cached": 0.025,
        "output": 0.40,
    },
}

# Gemini image generation costs (per image)
# Pricing varies by resolution
GEMINI_IMAGE_COSTS = {
    "gemini-2.5-flash-image": {
        "1K": 0.039,   # 1024x1024 and similar
        "2K": 0.078,   # 2048x2048 and similar
    },
    "gemini-3-pro-image-preview": {
        "1K": 0.040,
        "2K": 0.080,
        "4K": 0.160,
    },
}


# Gemini image size mappings
# Maps common size strings to Gemini aspect_ratio and image_size
GEMINI_SIZE_MAPPINGS = {
    # Landscape sizes
    "1536x1024": {"aspect_ratio": "3:2", "image_size": "1K"},
    "1024x1024": {"aspect_ratio": "1:1", "image_size": "1K"},
    "1792x1024": {"aspect_ratio": "16:9", "image_size": "1K"},
    "1024x1792": {"aspect_ratio": "9:16", "image_size": "1K"},
    # High resolution variants
    "2048x2048": {"aspect_ratio": "1:1", "image_size": "2K"},
    "3072x2048": {"aspect_ratio": "3:2", "image_size": "2K"},
    "4096x4096": {"aspect_ratio": "1:1", "image_size": "4K"},
    # Portrait sizes
    "1024x1536": {"aspect_ratio": "2:3", "image_size": "1K"},
}

# Available Gemini aspect ratios
GEMINI_ASPECT_RATIOS = [
    "1:1", "2:3", "3:2", "3:4", "4:3",
    "4:5", "5:4", "9:16", "16:9", "21:9"
]


class GoogleProvider(LLMProvider):
    """Google Gemini API implementation."""

    def __init__(
        self,
        api_key: str,
        default_model: str = "gemini-2.5-flash",
        default_image_model: str = "gemini-2.5-flash-image",
    ):
        """
        Initialize Google Gemini provider.

        Args:
            api_key: Google API key
            default_model: Default model for completions (gemini-2.5-flash, gemini-2.5-pro)
            default_image_model: Default model for image generation
                - gemini-2.5-flash-image: Fast, good quality
                - gemini-3-pro-image-preview: Advanced, supports 4K, thinking mode
        """
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

        self._api_key = api_key
        self._default_model = default_model
        self._default_image_model = default_image_model

    @property
    def name(self) -> str:
        return "google"

    @property
    def client(self):
        """Access to raw client for advanced use cases."""
        return self._client

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
    ) -> LLMResponse:
        """
        Generate a completion using Google Gemini's generate_content API.

        Gemini-specific:
        - Uses contents= parameter with role-based messages
        - System instructions handled separately
        - JSON schema via response_schema
        """
        model = model or self._default_model

        # Separate system message from conversation
        system_instruction = None
        contents = []

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content if isinstance(msg.content, str) else str(msg.content)
            else:
                contents.append(self._convert_message(msg))

        # Build generation config
        config_kwargs = {}

        if temperature is not None:
            config_kwargs["temperature"] = temperature

        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens

        if json_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = json_schema.schema

        generation_config = self._types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        # Build request kwargs
        kwargs = {
            "model": model,
            "contents": contents,
        }

        if system_instruction:
            kwargs["system_instruction"] = system_instruction

        if generation_config:
            kwargs["config"] = generation_config

        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        # Make the API call (sync - Google SDK handles async internally)
        response = self._client.models.generate_content(**kwargs)

        # Parse the response
        return self._parse_response(response, model)

    async def generate_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
        aspect_ratio: Optional[str] = None,
        image_size: Optional[str] = None,
    ) -> ImageResponse:
        """
        Generate an image using Google Gemini's native image generation.

        Gemini uses generate_content with response_modalities=['IMAGE'].

        Args:
            prompt: Text description for image generation
            model: Image model to use (default: gemini-2.5-flash-image)
                - gemini-2.5-flash-image: Fast generation
                - gemini-3-pro-image-preview: Advanced with 4K support
            size: OpenAI-compatible size string (e.g., "1536x1024")
                  Will be converted to Gemini aspect_ratio
            quality: "standard" or "high" (maps to image_size)
            n: Number of images (Gemini generates 1 per call)
            aspect_ratio: Direct Gemini aspect ratio (overrides size)
            image_size: Direct Gemini resolution "1K", "2K", "4K" (overrides quality)

        Returns:
            ImageResponse with generated image bytes
        """
        model = model or self._default_image_model

        # Determine aspect ratio and resolution
        if aspect_ratio is None or image_size is None:
            size_config = self._convert_size_to_gemini(size, quality)
            aspect_ratio = aspect_ratio or size_config["aspect_ratio"]
            image_size = image_size or size_config["image_size"]

        # Build image config
        image_config = self._types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        )

        # Build generation config with image modality
        config = self._types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=image_config,
        )

        # Generate images
        images = []
        raw_responses = []

        for _ in range(n):
            response = self._client.models.generate_content(
                model=model,
                contents=[prompt],
                config=config,
            )
            raw_responses.append(response)

            # Extract image data from response parts
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data is not None:
                    # Get base64 data and decode
                    image_data = part.inline_data.data
                    if isinstance(image_data, str):
                        images.append(base64.b64decode(image_data))
                    else:
                        images.append(image_data)

        # Parse usage and calculate cost
        usage = self._parse_image_usage(raw_responses[0] if raw_responses else None)
        cost = self._calculate_image_cost(model, image_size, n)

        return ImageResponse(
            images=images,
            model=model,
            usage=usage,
            cost=cost,
            raw_response=raw_responses[0] if len(raw_responses) == 1 else raw_responses,
        )

    async def generate_image_with_reference(
        self,
        prompt: str,
        reference_images: List[bytes],
        model: Optional[str] = None,
        aspect_ratio: str = "3:2",
        image_size: str = "1K",
    ) -> ImageResponse:
        """
        Generate an image using reference images for style/content guidance.

        Gemini 3 Pro supports up to 14 reference images:
        - Up to 6 object images for high-fidelity inclusion
        - Up to 5 human images for character consistency

        Args:
            prompt: Text description for image generation
            reference_images: List of reference image bytes
            model: Image model (default: gemini-3-pro-image-preview for multi-ref)
            aspect_ratio: Output aspect ratio
            image_size: Output resolution ("1K", "2K", "4K")

        Returns:
            ImageResponse with generated image bytes
        """
        # Multi-reference requires gemini-3-pro-image-preview
        model = model or "gemini-3-pro-image-preview"

        # Build content parts: prompt + reference images
        content_parts = [{"text": prompt}]

        for img_bytes in reference_images:
            content_parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(img_bytes).decode("utf-8"),
                }
            })

        # Build config
        config = self._types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=self._types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size=image_size,
            ),
        )

        response = self._client.models.generate_content(
            model=model,
            contents=[{"parts": content_parts}],
            config=config,
        )

        # Extract image
        images = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data is not None:
                image_data = part.inline_data.data
                if isinstance(image_data, str):
                    images.append(base64.b64decode(image_data))
                else:
                    images.append(image_data)

        return ImageResponse(
            images=images,
            model=model,
            usage=self._parse_image_usage(response),
            cost=self._calculate_image_cost(model, image_size, 1),
            raw_response=response,
        )

    async def edit_image(
        self,
        prompt: str,
        image: bytes,
        model: Optional[str] = None,
        aspect_ratio: str = "3:2",
        image_size: str = "1K",
    ) -> ImageResponse:
        """
        Edit an existing image using text instructions.

        Args:
            prompt: Text instructions for editing
            image: Source image bytes to edit
            model: Image model to use
            aspect_ratio: Output aspect ratio
            image_size: Output resolution

        Returns:
            ImageResponse with edited image bytes
        """
        model = model or self._default_image_model

        # Build content with text prompt and image
        content_parts = [
            {"text": prompt},
            {
                "inline_data": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(image).decode("utf-8"),
                }
            }
        ]

        config = self._types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=self._types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size=image_size,
            ),
        )

        response = self._client.models.generate_content(
            model=model,
            contents=[{"parts": content_parts}],
            config=config,
        )

        # Extract image
        images = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data is not None:
                image_data = part.inline_data.data
                if isinstance(image_data, str):
                    images.append(base64.b64decode(image_data))
                else:
                    images.append(image_data)

        return ImageResponse(
            images=images,
            model=model,
            usage=self._parse_image_usage(response),
            cost=self._calculate_image_cost(model, image_size, 1),
            raw_response=response,
        )

    async def upload_file(
        self,
        file_path: str,
        purpose: str = "user_data",
    ) -> FileReference:
        """
        Upload a file to Google.

        Note: Google Gemini handles files differently - they can be passed
        inline as base64 in most cases. This method is for compatibility.
        """
        import mimetypes

        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

        with open(file_path, "rb") as f:
            file_data = f.read()

        # For Google, we store the base64 data as the "file_id"
        # since Gemini accepts inline data directly
        file_id = base64.b64encode(file_data).decode("utf-8")

        logger.info(f"[GOOGLE] Prepared file for inline use: {file_path}")
        return FileReference(
            file_id=f"inline:{mime_type}:{file_id}",
            provider=self.name
        )

    async def delete_file(self, file_ref: FileReference) -> bool:
        """
        Delete a file reference.

        Since Google uses inline data, this just clears the reference.
        """
        if file_ref.provider != self.name:
            logger.warning(
                f"[GOOGLE] Cannot delete file from provider: {file_ref.provider}"
            )
            return False

        # No actual deletion needed for inline files
        logger.info(f"[GOOGLE] Cleared file reference")
        return True

    def _convert_message(self, msg: LLMMessage) -> Dict[str, Any]:
        """Convert unified message to Gemini format."""
        role = "user" if msg.role == "user" else "model"

        if isinstance(msg.content, str):
            return {"role": role, "parts": [{"text": msg.content}]}

        # Handle multimodal content
        parts = []
        for item in msg.content:
            if item.get("type") == "input_text":
                parts.append({"text": item["text"]})
            elif item.get("type") == "input_file":
                # Parse inline file reference
                file_id = item["file_id"]
                if file_id.startswith("inline:"):
                    _, mime_type, data = file_id.split(":", 2)
                    parts.append({
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": data,
                        }
                    })
            elif item.get("type") == "image_url":
                # Handle image URLs
                url = item["image_url"]["url"]
                if url.startswith("data:"):
                    # Extract base64 from data URL
                    header, data = url.split(",", 1)
                    mime_type = header.split(":")[1].split(";")[0]
                    parts.append({
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": data,
                        }
                    })
                else:
                    # External URL - Gemini can fetch these directly
                    parts.append({"file_data": {"file_uri": url}})

        return {"role": role, "parts": parts}

    def _convert_tools(
        self, tools: List[Union[ToolDefinition, RawTool]]
    ) -> List[Dict[str, Any]]:
        """Convert unified tool definitions to Gemini format."""
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

    def _parse_response(self, response: Any, model: str) -> LLMResponse:
        """Parse Gemini response into unified format."""
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

        # Parse usage and calculate cost
        usage = None
        cost = None
        if hasattr(response, "usage_metadata"):
            usage = self._parse_usage(response.usage_metadata)
            cost = self._calculate_completion_cost(model, usage)

        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
            cost=cost,
            tool_calls=tool_calls if tool_calls else None,
            raw_response=response,
        )

    def _parse_usage(self, usage: Any) -> TokenUsage:
        """Parse Gemini usage into unified format."""
        return TokenUsage(
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            cached_input_tokens=getattr(usage, "cached_content_token_count", 0) or 0,
        )

    def _parse_image_usage(self, response: Any) -> Optional[TokenUsage]:
        """Parse Gemini image generation usage."""
        if response and hasattr(response, "usage_metadata"):
            return self._parse_usage(response.usage_metadata)
        return None

    def _convert_size_to_gemini(self, size: str, quality: str) -> Dict[str, str]:
        """
        Convert OpenAI-style size string to Gemini aspect_ratio and image_size.

        Args:
            size: Size string like "1536x1024" or "1024x1024"
            quality: "standard" or "high"

        Returns:
            Dict with aspect_ratio and image_size
        """
        # Check direct mapping first
        if size in GEMINI_SIZE_MAPPINGS:
            result = GEMINI_SIZE_MAPPINGS[size].copy()
            # Upgrade resolution for high quality
            if quality == "high" and result["image_size"] == "1K":
                result["image_size"] = "2K"
            return result

        # Parse size string and calculate aspect ratio
        try:
            width, height = map(int, size.lower().split("x"))

            # Find closest aspect ratio
            ratio = width / height
            best_match = "1:1"
            best_diff = float("inf")

            for ar in GEMINI_ASPECT_RATIOS:
                ar_w, ar_h = map(int, ar.split(":"))
                ar_ratio = ar_w / ar_h
                diff = abs(ratio - ar_ratio)
                if diff < best_diff:
                    best_diff = diff
                    best_match = ar

            # Determine resolution based on pixel count and quality
            pixels = width * height
            if quality == "high" or pixels > 2_000_000:
                image_size = "2K"
            elif pixels > 4_000_000:
                image_size = "4K"
            else:
                image_size = "1K"

            return {"aspect_ratio": best_match, "image_size": image_size}

        except (ValueError, ZeroDivisionError):
            # Default fallback
            return {"aspect_ratio": "1:1", "image_size": "1K"}

    def _calculate_completion_cost(self, model: str, usage: TokenUsage) -> CostInfo:
        """Calculate cost for a completion call with separate reasoning costs."""
        # Find pricing for this model, fallback to flash pricing
        pricing = GEMINI_PRICING.get(model, GEMINI_PRICING.get("gemini-2.5-flash", {}))

        # Calculate non-cached and cached input costs
        non_cached = usage.input_tokens - usage.cached_input_tokens
        input_cost = (non_cached / 1_000_000) * pricing.get("input", 0)
        input_cost += (usage.cached_input_tokens / 1_000_000) * pricing.get(
            "input_cached", pricing.get("input", 0) * 0.25
        )

        # Output tokens (excluding reasoning)
        output_cost = (usage.output_tokens / 1_000_000) * pricing.get("output", 0)

        # Reasoning/thinking tokens priced separately (Gemini thinking mode)
        reasoning_cost = 0.0
        if usage.reasoning_tokens > 0:
            # Use thinking-specific pricing if available
            reasoning_rate = pricing.get("thinking_output", pricing.get("output", 0))
            reasoning_cost = (usage.reasoning_tokens / 1_000_000) * reasoning_rate

        total_cost = input_cost + output_cost + reasoning_cost

        return CostInfo(
            provider=self.name,
            model=model,
            total_cost=total_cost,
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
        # Get model-specific pricing
        model_pricing = GEMINI_IMAGE_COSTS.get(
            model, GEMINI_IMAGE_COSTS.get("gemini-2.5-flash-image", {})
        )

        # Get per-image cost for this resolution
        per_image_cost = model_pricing.get(image_size, model_pricing.get("1K", 0.039))
        total_cost = per_image_cost * n

        return CostInfo(
            provider=self.name,
            model=model,
            total_cost=total_cost,
            image_size=image_size,
            image_count=n,
        )
