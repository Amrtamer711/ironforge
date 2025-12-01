"""
Unified LLM Client.

Provides a single interface to interact with any LLM provider.
Handles cost tracking automatically.
"""

import logging
from typing import Any, Dict, List, Optional

from integrations.llm.base import (
    ContentPart,
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
    def from_config(cls) -> "LLMClient":
        """
        Create an LLMClient using configuration from config.py.

        Returns:
            Configured LLMClient instance
        """
        import config

        provider = OpenAIProvider(
            api_key=config.OPENAI_API_KEY,
            default_model=config.OPENAI_MODEL,
        )
        return cls(provider)

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
        messages: List[LLMMessage],
        model: Optional[str] = None,
        tools: Optional[List[ToolDefinition]] = None,
        tool_choice: Optional[str] = None,
        json_schema: Optional[JSONSchema] = None,
        reasoning: Optional[ReasoningEffort] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        store: bool = False,
        # Cost tracking parameters
        track_cost: bool = True,
        call_type: str = "llm_call",
        user_id: Optional[str] = None,
        workflow: Optional[str] = None,
        context: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
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
        model: Optional[str] = None,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
        # Cost tracking parameters
        track_cost: bool = True,
        user_id: Optional[str] = None,
        workflow: Optional[str] = None,
        context: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ImageResponse:
        """
        Generate an image from a text prompt.

        Args:
            prompt: Text description of the image
            model: Image model to use
            size: Image dimensions (e.g., "1024x1024", "1024x1536")
            quality: Quality level ("standard" or "high")
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
            model=model,
            size=size,
            quality=quality,
            n=n,
        )

        # Track cost if enabled
        if track_cost:
            self._track_image_cost(
                response=response,
                size=size,
                quality=quality,
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
        user_id: Optional[str],
        workflow: Optional[str],
        context: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        """Track cost for a completion call."""
        try:
            from integrations.openai import cost_tracker

            # Build a minimal response object that cost_tracker expects
            # The raw_response contains the original provider response
            if response.raw_response:
                cost_tracker.track_openai_call(
                    response=response.raw_response,
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
        size: str,
        quality: str,
        n: int,
        user_id: Optional[str],
        workflow: Optional[str],
        context: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        """Track cost for an image generation call."""
        try:
            from integrations.openai import cost_tracker

            if response.raw_response:
                cost_tracker.track_image_generation(
                    response=response.raw_response,
                    model=response.model,
                    size=size,
                    quality=quality,
                    n=n,
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
    "JSONSchema",
    "ToolDefinition",
    "RawTool",
    "ToolCall",
    "TokenUsage",
    "ReasoningEffort",
    "FileReference",
    "ImageResponse",
]
