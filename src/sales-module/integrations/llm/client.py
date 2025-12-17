"""
Unified LLM Client.

Provides a single interface to interact with any LLM provider.
Handles cost tracking automatically.
"""

import logging
from typing import Any

from integrations.llm.base import (
    ContentPart,
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
from integrations.llm.providers.google import GoogleProvider
from integrations.llm.providers.openai import OpenAIProvider

logger = logging.getLogger("proposal-bot")


class LLMClient:
    """
    Unified LLM client that abstracts provider-specific implementations.

    Usage:
        from integrations.llm import LLMClient

        # Initialize with default OpenAI provider
        client = LLMClient.from_config()

        # Simple completion
        response = await client.complete([
            LLMMessage.system("You are a helpful assistant."),
            LLMMessage.user("Hello!")
        ])
        print(response.content)

        # Structured output with JSON schema
        response = await client.complete(
            messages=[LLMMessage.system("Extract data...")],
            json_schema=JSONSchema(
                name="extraction",
                schema={"type": "object", "properties": {...}}
            )
        )

        # With file attachment
        file_ref = await client.upload_file("/path/to/file.pdf")
        response = await client.complete([
            LLMMessage.user([
                ContentPart.file(file_ref.file_id),
                ContentPart.text("Analyze this document")
            ])
        ])
        await client.delete_file(file_ref)
    """

    def __init__(self, provider: LLMProvider):
        """
        Initialize the LLM client with a provider.

        Args:
            provider: The LLM provider implementation to use
        """
        self._provider = provider

    @classmethod
    def from_config(cls, provider_name: str | None = None) -> "LLMClient":
        """
        Create an LLMClient using configuration from config.py.

        Args:
            provider_name: Which provider to use ("openai" or "google").
                          If None, uses config.LLM_PROVIDER or defaults to "openai".

        Returns:
            Configured LLMClient instance
        """
        import config

        # Determine which provider to use
        provider_name = provider_name or getattr(config, "LLM_PROVIDER", "openai")

        if provider_name == "google":
            api_key = getattr(config, "GOOGLE_API_KEY", None)
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not configured")

            # Google: fixed models per task type
            provider = GoogleProvider(api_key=api_key)
        else:
            # OpenAI: fixed models per task type
            provider = OpenAIProvider(api_key=config.OPENAI_API_KEY)

        return cls(provider)

    @classmethod
    def for_images(cls, provider_name: str | None = None) -> "LLMClient":
        """
        Create an LLMClient specifically configured for image generation.

        Args:
            provider_name: Which provider to use ("openai" or "google").
                          If None, uses config.IMAGE_PROVIDER or defaults to config.LLM_PROVIDER.

        Returns:
            Configured LLMClient instance for image generation
        """
        import config

        # Check for image-specific provider first
        provider_name = provider_name or getattr(config, "IMAGE_PROVIDER", None)
        if provider_name is None:
            provider_name = getattr(config, "LLM_PROVIDER", "openai")

        return cls.from_config(provider_name)

    @property
    def provider(self) -> LLMProvider:
        """Access the underlying provider."""
        return self._provider

    @property
    def provider_name(self) -> str:
        """Get the name of the current provider."""
        return self._provider.name

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
        json_schema: JSONSchema | None = None,
        reasoning: ReasoningEffort | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        store: bool = False,
        # Prompt caching parameters (OpenAI-specific)
        cache_key: str | None = None,
        cache_retention: str | None = None,
        # Cost tracking parameters
        track_cost: bool = True,
        call_type: str = "llm_call",
        user_id: str | None = None,
        workflow: str | None = None,
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """
        Generate a completion from the LLM.

        Args:
            messages: List of messages in the conversation
            model: Model to use (uses provider default if not set)
            tools: List of ToolDefinition objects for function calling
            tool_choice: Tool choice mode ("auto", "none", "required")
            json_schema: JSON schema for structured output
            reasoning: Reasoning effort level (LOW, MEDIUM, HIGH)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            store: Whether to store the response
            cache_key: Prompt cache routing key (OpenAI: e.g., "proposal-system")
            cache_retention: Cache retention policy (OpenAI: "in_memory" or "24h")
            track_cost: Whether to track API costs (default True)
            call_type: Type of call for cost tracking
            user_id: User ID/name for cost tracking
            workflow: Workflow name for cost tracking
            context: Additional context for cost tracking
            metadata: Additional metadata for cost tracking

        Returns:
            LLMResponse with content, usage, and optional tool_calls
        """
        response = await self._provider.complete(
            messages=messages,
            model=model,
            tools=tools,
            tool_choice=tool_choice,
            json_schema=json_schema,
            reasoning=reasoning,
            temperature=temperature,
            max_tokens=max_tokens,
            store=store,
            cache_key=cache_key,
            cache_retention=cache_retention,
        )

        # Track cost if enabled and we have usage data
        if track_cost and response.usage:
            self._track_completion_cost(
                response=response,
                call_type=call_type,
                user_id=user_id,
                workflow=workflow,
                context=context,
                metadata=metadata,
            )

        return response

    async def generate_image(
        self,
        prompt: str,
        quality: str = "high",
        orientation: str = "landscape",
        n: int = 1,
        # Cost tracking parameters
        track_cost: bool = True,
        user_id: str | None = None,
        workflow: str | None = None,
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ImageResponse:
        """
        Generate an image from a text prompt.

        Unified interface - providers handle quality/orientation internally:
        - OpenAI (gpt-image-1): quality=low/medium/high, orientation→size
        - Google (gemini-3-pro): quality→resolution (1K/2K/4K), orientation→aspect_ratio

        Args:
            prompt: Text description of the image
            quality: "low", "medium", or "high"
            orientation: "portrait" or "landscape"
            n: Number of images to generate
            track_cost: Whether to track API costs
            user_id: User ID/name for cost tracking
            workflow: Workflow name for cost tracking
            context: Additional context for cost tracking
            metadata: Additional metadata for cost tracking

        Returns:
            ImageResponse with generated image bytes
        """
        response = await self._provider.generate_image(
            prompt=prompt,
            quality=quality,
            orientation=orientation,
            n=n,
        )

        # Track cost if enabled
        if track_cost:
            self._track_image_cost(
                response=response,
                n=n,
                user_id=user_id,
                workflow=workflow,
                context=context,
                metadata=metadata,
            )

        return response

    async def upload_file(
        self,
        file_path: str,
        purpose: str = "user_data",
    ) -> FileReference:
        """
        Upload a file for use in completions.

        Args:
            file_path: Path to the file to upload
            purpose: Purpose of the file upload

        Returns:
            FileReference with the file ID
        """
        return await self._provider.upload_file(file_path, purpose)

    async def delete_file(self, file_ref: FileReference) -> bool:
        """
        Delete a previously uploaded file.

        Args:
            file_ref: Reference to the file to delete

        Returns:
            True if deleted successfully
        """
        return await self._provider.delete_file(file_ref)

    def _track_completion_cost(
        self,
        response: LLMResponse,
        call_type: str,
        user_id: str | None,
        workflow: str | None,
        context: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Track cost for a completion call."""
        try:
            from integrations.llm import cost_tracker

            # Use the CostInfo from the response (calculated by provider)
            if response.cost:
                cost_tracker.track_cost(
                    cost=response.cost,
                    call_type=call_type,
                    user_id=user_id,
                    workflow=workflow,
                    context=context,
                    metadata=metadata,
                )
        except Exception as e:
            logger.warning(f"[LLM] Failed to track completion cost: {e}")

    def _track_image_cost(
        self,
        response: ImageResponse,
        n: int,
        user_id: str | None,
        workflow: str | None,
        context: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Track cost for an image generation call."""
        try:
            from integrations.llm import cost_tracker

            # Use the CostInfo from the response (calculated by provider)
            if response.cost:
                cost_tracker.track_cost(
                    cost=response.cost,
                    call_type="image_generation",
                    user_id=user_id,
                    workflow=workflow,
                    context=context,
                    metadata=metadata,
                )
        except Exception as e:
            logger.warning(f"[LLM] Failed to track image cost: {e}")


# Re-export commonly used types for convenience
__all__ = [
    "LLMClient",
    "LLMMessage",
    "LLMResponse",
    "LLMProvider",
    "ContentPart",
    "CostInfo",
    "JSONSchema",
    "ToolDefinition",
    "RawTool",
    "ToolCall",
    "TokenUsage",
    "ReasoningEffort",
    "FileReference",
    "ImageResponse",
]
