"""
Sales Module LLM Client.

Thin wrapper around crm-llm that adds:
- from_config() factory method using sales-module config
- for_images() factory method for image generation
- Automatic cost tracking to database via cost_tracker

Usage:
    from integrations.llm import LLMClient

    # Initialize with default OpenAI provider (reads from config)
    client = LLMClient.from_config()

    # For image generation (uses IMAGE_PROVIDER config)
    client = LLMClient.for_images()

    # Simple completion
    response = await client.complete([
        LLMMessage.system("You are a helpful assistant."),
        LLMMessage.user("Hello!")
    ])
    print(response.content)
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

# Import everything from crm-llm
from crm_llm import LLMClient as BaseLLMClient
from crm_llm import (
    ContentPart,
    CostInfo,
    FileReference,
    GoogleProvider,
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


class LLMClient(BaseLLMClient):
    """
    Sales-module LLM client with config integration and cost tracking.

    Extends crm-llm's LLMClient with:
    - from_config(): Create client from sales-module config
    - for_images(): Create client for image generation
    - Automatic cost tracking to database
    """

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
        from crm_llm import OpenAIProvider

        # Determine which provider to use
        provider_name = provider_name or getattr(config, "LLM_PROVIDER", "openai")

        if provider_name == "google":
            api_key = getattr(config, "GOOGLE_API_KEY", None)
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not configured")
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

    # =========================================================================
    # Override methods to add cost tracking
    # =========================================================================

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
        """Generate a completion from the LLM with automatic cost tracking."""
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
        if track_cost and response.cost:
            self._track_cost(
                cost=response.cost,
                call_type=call_type,
                user_id=user_id,
                workflow=workflow,
                context=context,
                metadata=metadata,
            )

        return response

    async def stream_complete(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
        reasoning: ReasoningEffort | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        cache_key: str | None = None,
        cache_retention: str | None = None,
        # Cost tracking parameters
        track_cost: bool = True,
        call_type: str = "llm_call",
        user_id: str | None = None,
        workflow: str | None = None,
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a completion from the LLM with automatic cost tracking."""
        try:
            async for event in self._provider.stream_complete(
                messages=messages,
                model=model,
                tools=tools,
                tool_choice=tool_choice,
                reasoning=reasoning,
                temperature=temperature,
                max_tokens=max_tokens,
                cache_key=cache_key,
                cache_retention=cache_retention,
            ):
                # Track cost on completion event
                if event.get("type") == "response.completed" and track_cost and event.get("cost"):
                    self._track_cost(
                        cost=event["cost"],
                        call_type=call_type,
                        user_id=user_id,
                        workflow=workflow,
                        context=context,
                        metadata=metadata,
                    )

                yield event

        except NotImplementedError:
            # Fall back to non-streaming for providers that don't support it
            logger.warning(f"[LLM] Provider {self._provider.name} doesn't support streaming, falling back to complete()")
            response = await self.complete(
                messages=messages,
                model=model,
                tools=tools,
                tool_choice=tool_choice,
                reasoning=reasoning,
                temperature=temperature,
                max_tokens=max_tokens,
                cache_key=cache_key,
                cache_retention=cache_retention,
                track_cost=track_cost,
                call_type=call_type,
                user_id=user_id,
                workflow=workflow,
                context=context,
                metadata=metadata,
            )
            # Emit completed response as events
            if response.content:
                yield {"type": "response.output_text.done", "text": response.content}
            if response.tool_calls:
                for tc in response.tool_calls:
                    yield {
                        "type": "response.function_call_arguments.done",
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "item_id": tc.id,
                    }
            yield {
                "type": "response.completed",
                "usage": response.usage,
                "cost": response.cost,
            }

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
        """Generate an image from a text prompt with automatic cost tracking."""
        response = await self._provider.generate_image(
            prompt=prompt,
            quality=quality,
            orientation=orientation,
            n=n,
        )

        # Track cost if enabled
        if track_cost and response.cost:
            self._track_cost(
                cost=response.cost,
                call_type="image_generation",
                user_id=user_id,
                workflow=workflow,
                context=context,
                metadata=metadata,
            )

        return response

    def _track_cost(
        self,
        cost: CostInfo,
        call_type: str,
        user_id: str | None,
        workflow: str | None,
        context: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Track cost using sales-module's cost_tracker."""
        try:
            from integrations.llm import cost_tracker

            cost_tracker.track_cost(
                cost=cost,
                call_type=call_type,
                user_id=user_id,
                workflow=workflow,
                context=context,
                metadata=metadata,
            )
        except Exception as e:
            logger.warning(f"[LLM] Failed to track cost: {e}")


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
