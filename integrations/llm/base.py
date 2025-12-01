"""
Abstract base class for LLM providers.
Each provider implements their own API-specific syntax.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class ReasoningEffort(Enum):
    """Reasoning effort levels for models that support it."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class LLMMessage:
    """Unified message format."""
    role: str  # "system", "user", "assistant"
    content: Union[str, List[Dict[str, Any]]]  # String or multimodal content

    @staticmethod
    def system(content: str) -> "LLMMessage":
        """Create a system message."""
        return LLMMessage(role="system", content=content)

    @staticmethod
    def user(content: Union[str, List[Dict[str, Any]]]) -> "LLMMessage":
        """Create a user message."""
        return LLMMessage(role="user", content=content)

    @staticmethod
    def assistant(content: str) -> "LLMMessage":
        """Create an assistant message."""
        return LLMMessage(role="assistant", content=content)


@dataclass
class ContentPart:
    """Helper for building multimodal content parts."""

    @staticmethod
    def text(text: str) -> Dict[str, Any]:
        """Create a text content part (OpenAI: input_text)."""
        return {"type": "input_text", "text": text}

    @staticmethod
    def file(file_id: str) -> Dict[str, Any]:
        """Create a file content part (OpenAI: input_file)."""
        return {"type": "input_file", "file_id": file_id}

    @staticmethod
    def image_url(url: str, detail: str = "auto") -> Dict[str, Any]:
        """Create an image URL content part."""
        return {"type": "image_url", "image_url": {"url": url, "detail": detail}}

    @staticmethod
    def image_base64(base64_data: str, media_type: str = "image/png") -> Dict[str, Any]:
        """Create a base64 image content part."""
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{base64_data}"}
        }


@dataclass
class LLMResponse:
    """Unified response format from any LLM provider."""
    content: str
    model: str
    usage: Optional["TokenUsage"] = None
    tool_calls: Optional[List["ToolCall"]] = None
    raw_response: Any = None  # Original provider response for advanced use


@dataclass
class TokenUsage:
    """Token usage tracking."""
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0

    # For image models
    text_input_tokens: int = 0
    image_input_tokens: int = 0


@dataclass
class ToolCall:
    """Unified tool/function call format."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ToolDefinition:
    """Unified tool definition format for function tools."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema


@dataclass
class RawTool:
    """
    Raw tool definition that passes through to the provider unchanged.

    Used for provider-specific tools that aren't function calls, like:
    - OpenAI's code_interpreter: {"type": "code_interpreter", "container": {"type": "auto"}}
    - OpenAI's file_search: {"type": "file_search", ...}

    These tools are passed directly to the API without conversion.
    """
    raw: Dict[str, Any]  # Raw tool definition to pass through


@dataclass
class JSONSchema:
    """JSON Schema for structured outputs."""
    name: str
    schema: Dict[str, Any]
    strict: bool = True


@dataclass
class FileReference:
    """Reference to an uploaded file."""
    file_id: str
    provider: str  # Which provider this file was uploaded to


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Each provider (OpenAI, Anthropic, Google, etc.) implements this interface
    with their own API-specific syntax.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'openai', 'anthropic', 'google')."""
        pass

    @abstractmethod
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
        Generate a completion from the LLM.

        Args:
            messages: List of messages in the conversation
            model: Model to use (provider-specific, uses default if not set)
            tools: List of tool definitions for function calling
            tool_choice: Tool choice mode ("auto", "none", "required", or specific tool)
            json_schema: JSON schema for structured output
            reasoning: Reasoning effort level (for models that support it)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            store: Whether to store the response (OpenAI-specific, default False)

        Returns:
            LLMResponse with the completion
        """
        pass

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
    ) -> "ImageResponse":
        """
        Generate an image from a text prompt.

        Args:
            prompt: Text description of the image to generate
            model: Image model to use
            size: Image dimensions (e.g., "1024x1024", "1792x1024")
            quality: Quality level ("standard" or "high")
            n: Number of images to generate

        Returns:
            ImageResponse with generated image data
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def delete_file(self, file_ref: FileReference) -> bool:
        """
        Delete a previously uploaded file.

        Args:
            file_ref: Reference to the file to delete

        Returns:
            True if deleted successfully
        """
        pass


@dataclass
class ImageResponse:
    """Response from image generation."""
    images: List[bytes]  # Raw image data
    model: str
    usage: Optional[TokenUsage] = None
    raw_response: Any = None
