"""
Unified LLM Client.

Provides a single interface to interact with any LLM provider.
Handles cost tracking via injectable CostLogger.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from crm_llm.base import (
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
from crm_llm.cost_tracker import CostLogger

logger = logging.getLogger("crm-llm")


class LLMClient:
    """
    Unified LLM client that abstracts provider-specific implementations.

    Usage:
        from crm_llm import LLMClient, LLMMessage, OpenAIProvider

        # Initialize with provider
        provider = OpenAIProvider(api_key="sk-...")
        client = LLMClient(provider)

        # Simple completion
        response = await client.complete([
            LLMMessage.system("You are a helpful assistant."),
            LLMMessage.user("Hello!")
        ])
        print(response.content)

        # With cost tracking
        client = LLMClient(provider, cost_logger=my_cost_logger)

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

    def __init__(
        self,
        provider: LLMProvider,
        cost_logger: CostLogger | None = None,
    ):
        """
        Initialize the LLM client with a provider.

        Args:
            provider: The LLM provider implementation to use
            cost_logger: Optional cost logger for tracking API costs
        """
        self._provider = provider
        self._cost_logger = cost_logger

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

        # Track cost if enabled and we have cost data and a logger
        if track_cost and response.cost and self._cost_logger:
            self._track_completion_cost(
                response=response,
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
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream a completion from the LLM, yielding events as they arrive.

        Yields semantic events from the provider:
        - {"type": "response.created", "response_id": str}
        - {"type": "response.output_text.delta", "delta": str, ...}
        - {"type": "response.output_text.done", "text": str, ...}
        - {"type": "response.function_call_arguments.delta", ...}
        - {"type": "response.function_call_arguments.done", ...}
        - {"type": "response.completed", "usage": TokenUsage, "cost": CostInfo}
        - {"type": "error", "message": str}

        Args:
            messages: List of messages in the conversation
            model: Model to use (uses provider default if not set)
            tools: List of ToolDefinition objects for function calling
            tool_choice: Tool choice mode ("auto", "none", "required")
            reasoning: Reasoning effort level (LOW, MEDIUM, HIGH)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            cache_key: Prompt cache routing key (OpenAI: e.g., "proposal-system")
            cache_retention: Cache retention policy (OpenAI: "in_memory" or "24h")
            track_cost: Whether to track API costs (default True)
            call_type: Type of call for cost tracking
            user_id: User ID/name for cost tracking
            workflow: Workflow name for cost tracking
            context: Additional context for cost tracking
            metadata: Additional metadata for cost tracking

        Yields:
            Event dicts with semantic information about the streaming response
        """
        # Try to use streaming, fall back to non-streaming if not supported
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
                if (
                    event.get("type") == "response.completed"
                    and track_cost
                    and event.get("cost")
                    and self._cost_logger
                ):
                    try:
                        self._cost_logger.log_cost(
                            cost=event["cost"],
                            call_type=call_type,
                            user_id=user_id,
                            workflow=workflow,
                            context=context,
                            metadata=metadata,
                        )
                    except Exception as e:
                        logger.warning(f"[LLM] Failed to track streaming cost: {e}")

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
        """
        Generate an image from a text prompt.

        Unified interface - providers handle quality/orientation internally:
        - OpenAI (gpt-image-1): quality=low/medium/high, orientation->size
        - Google (gemini-3-pro): quality->resolution (1K/2K/4K), orientation->aspect_ratio

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

        # Track cost if enabled and we have cost data and a logger
        if track_cost and response.cost and self._cost_logger:
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
        if not self._cost_logger or not response.cost:
            return

        try:
            self._cost_logger.log_cost(
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
        if not self._cost_logger or not response.cost:
            return

        try:
            self._cost_logger.log_cost(
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
