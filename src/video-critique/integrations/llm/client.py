"""
Video Critique LLM Client.

Thin wrapper around crm-llm that adds:
- from_config() factory method using video-critique config
- Automatic cost tracking to database via cost_tracker

Usage:
    from integrations.llm import LLMClient

    # Initialize with default OpenAI provider (reads from config)
    client = LLMClient.from_config()

    # Simple completion
    response = await client.complete([
        LLMMessage.system("You are a design request assistant."),
        LLMMessage.user("I need a video for our new campaign...")
    ])
    print(response.content)

    # With vision (image analysis)
    response = await client.complete([
        LLMMessage.system("You are a design request assistant."),
        LLMMessage.user_with_images("What brand is this?", [image_bytes])
    ])
"""

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
    OpenAIProvider,
    RawTool,
    ReasoningEffort,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)

from core.utils.logging import get_logger

logger = get_logger(__name__)


class LLMClient(BaseLLMClient):
    """
    Video-critique LLM client with config integration and cost tracking.

    Extends crm-llm's LLMClient with:
    - from_config(): Create client from video-critique config
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

        # Determine which provider to use
        provider_name = provider_name or getattr(config, "LLM_PROVIDER", "openai")

        if provider_name == "google":
            api_key = getattr(config, "GOOGLE_API_KEY", None)
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not configured")
            provider = GoogleProvider(api_key=api_key)
        else:
            # Default to OpenAI
            api_key = getattr(config, "OPENAI_API_KEY", None)
            if not api_key:
                raise ValueError("OPENAI_API_KEY not configured")
            provider = OpenAIProvider(api_key=api_key)

        return cls(provider)

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

    def _track_cost(
        self,
        cost: CostInfo,
        call_type: str,
        user_id: str | None,
        workflow: str | None,
        context: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Track cost using video-critique's cost_tracker."""
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
