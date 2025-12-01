"""
OpenAI LLM Provider Implementation.

Handles OpenAI-specific API syntax:
- responses.create() with input= parameter
- text= parameter for JSON schema structured outputs
- reasoning= parameter for reasoning effort
- files.create() / files.delete() for file handling
- images.generate() for image generation
"""

import base64
import logging
from typing import Any, Dict, List, Optional, Union

from openai import AsyncOpenAI

from integrations.llm.base import (
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


class OpenAIProvider(LLMProvider):
    """OpenAI API implementation."""

    def __init__(
        self,
        api_key: str,
        default_model: str = "gpt-5",
        default_image_model: str = "gpt-image-1",
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            default_model: Default model for completions
            default_image_model: Default model for image generation
        """
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
        Generate a completion using OpenAI's responses.create API.

        OpenAI-specific:
        - Uses 'input' parameter instead of 'messages'
        - Uses 'text' parameter for JSON schema
        - Uses 'reasoning' parameter for effort levels
        - Uses 'store' parameter to control response storage
        """
        model = model or self._default_model

        # Convert unified messages to OpenAI format
        input_messages = self._convert_messages(messages)

        # Build request kwargs
        kwargs: Dict[str, Any] = {
            "model": model,
            "input": input_messages,
            "store": store,
        }

        # Add optional parameters
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
            kwargs["max_tokens"] = max_tokens

        # Make the API call
        response = await self._client.responses.create(**kwargs)

        # Parse the response
        return self._parse_response(response)

    async def generate_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
    ) -> ImageResponse:
        """
        Generate an image using OpenAI's images.generate API.
        """
        model = model or self._default_image_model

        response = await self._client.images.generate(
            model=model,
            prompt=prompt,
            n=n,
            size=size,
            quality=quality,
            response_format="b64_json",
        )

        # Extract image data
        images = []
        for img_data in response.data:
            if hasattr(img_data, "b64_json") and img_data.b64_json:
                images.append(base64.b64decode(img_data.b64_json))

        # Extract usage if available
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = self._parse_image_usage(response.usage)

        return ImageResponse(
            images=images,
            model=model,
            usage=usage,
            raw_response=response,
        )

    async def upload_file(
        self,
        file_path: str,
        purpose: str = "user_data",
    ) -> FileReference:
        """
        Upload a file to OpenAI.
        """
        with open(file_path, "rb") as f:
            file_obj = await self._client.files.create(
                file=f,
                purpose=purpose,
            )

        logger.info(f"[OPENAI] Uploaded file: {file_obj.id}")
        return FileReference(file_id=file_obj.id, provider=self.name)

    async def delete_file(self, file_ref: FileReference) -> bool:
        """
        Delete a file from OpenAI.
        """
        if file_ref.provider != self.name:
            logger.warning(
                f"[OPENAI] Cannot delete file from provider: {file_ref.provider}"
            )
            return False

        try:
            await self._client.files.delete(file_ref.file_id)
            logger.info(f"[OPENAI] Deleted file: {file_ref.file_id}")
            return True
        except Exception as e:
            logger.warning(f"[OPENAI] Failed to delete file {file_ref.file_id}: {e}")
            return False

    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """Convert unified messages to OpenAI format."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def _convert_tools(
        self, tools: List[Union[ToolDefinition, RawTool]]
    ) -> List[Dict[str, Any]]:
        """
        Convert unified tool definitions to OpenAI format.

        Handles both:
        - ToolDefinition: Converted to OpenAI function format
        - RawTool: Passed through unchanged (e.g., code_interpreter)
        """
        result = []
        for tool in tools:
            if isinstance(tool, RawTool):
                # Raw tools pass through unchanged
                result.append(tool.raw)
            else:
                # Function tools get converted
                result.append({
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                })
        return result

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse OpenAI response into unified format."""
        # Extract text content
        content = ""
        tool_calls = []

        if hasattr(response, "output") and response.output:
            for item in response.output:
                if hasattr(item, "type"):
                    if item.type == "message" and hasattr(item, "content"):
                        # Handle message content
                        for content_item in item.content:
                            if hasattr(content_item, "text"):
                                content = content_item.text
                    elif item.type == "function_call":
                        # Handle function calls
                        import json

                        tool_calls.append(
                            ToolCall(
                                id=getattr(item, "call_id", ""),
                                name=getattr(item, "name", ""),
                                arguments=json.loads(
                                    getattr(item, "arguments", "{}")
                                ),
                            )
                        )

        # Also check for direct output_text (structured outputs)
        if hasattr(response, "output_text") and response.output_text:
            content = response.output_text

        # Parse usage
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = self._parse_usage(response.usage)

        return LLMResponse(
            content=content,
            model=getattr(response, "model", self._default_model),
            usage=usage,
            tool_calls=tool_calls if tool_calls else None,
            raw_response=response,
        )

    def _parse_usage(self, usage: Any) -> TokenUsage:
        """Parse OpenAI usage into unified format."""
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        # Handle cached input tokens
        cached_input_tokens = 0
        if hasattr(usage, "input_tokens_details"):
            details = usage.input_tokens_details
            cached_input_tokens = getattr(details, "cached_tokens", 0) or 0

        # Handle reasoning tokens
        reasoning_tokens = 0
        if hasattr(usage, "output_tokens_details"):
            details = usage.output_tokens_details
            reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
        )

    def _parse_image_usage(self, usage: Any) -> TokenUsage:
        """Parse OpenAI image generation usage."""
        total_input = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        text_input_tokens = 0
        image_input_tokens = 0

        if hasattr(usage, "input_tokens_details"):
            details = usage.input_tokens_details
            text_input_tokens = getattr(details, "text_tokens", 0) or 0
            image_input_tokens = getattr(details, "image_tokens", 0) or 0

        return TokenUsage(
            input_tokens=total_input,
            output_tokens=output_tokens,
            text_input_tokens=text_input_tokens,
            image_input_tokens=image_input_tokens,
        )
