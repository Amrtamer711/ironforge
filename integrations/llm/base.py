"""
Abstract base class for LLM providers.
Each provider implements their own API-specific syntax.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class ReasoningEffort(Enum):
    """
    Reasoning effort levels for models that support it.

    OpenAI Responses API values:
    - none: No reasoning (gpt-5.1 default, not supported by older models)
    - minimal: Minimal reasoning
    - low: Low reasoning effort
    - medium: Medium reasoning effort (default for models before gpt-5.1)
    - high: High reasoning effort (only option for gpt-5-pro)
    """
    NONE = "none"
    MINIMAL = "minimal"
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
    cost: Optional["CostInfo"] = None  # Provider-calculated cost
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
        quality: str = "high",
        orientation: str = "landscape",
        n: int = 1,
    ) -> "ImageResponse":
        """
        Generate an image from a text prompt.

        Unified interface - each provider handles quality/orientation internally:
        - OpenAI (gpt-image-1): quality=low/medium/high, sizes=1024x1536/1536x1024
        - Google (gemini-3-pro): quality→resolution (1K/2K/4K), orientation→aspect_ratio

        Args:
            prompt: Text description of the image to generate
            quality: "low", "medium", or "high" - provider maps to internal settings
            orientation: "portrait" or "landscape" - provider maps to size/aspect_ratio
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
class CostInfo:
    """
    Uniform cost information calculated by the provider.

    Each provider calculates this from its own response format.
    The cost tracker logs these with full accuracy.

    Cost breakdown:
    - input_cost: Cost for non-cached input tokens
    - output_cost: Cost for output tokens (excluding reasoning)
    - reasoning_cost: Cost for reasoning/thinking tokens (separate from output)
    - total_cost: Sum of all costs

    Token breakdown:
    - input_tokens: Total input tokens (including cached)
    - output_tokens: Output tokens (excluding reasoning)
    - cached_tokens: Tokens served from cache (subset of input_tokens)
    - reasoning_tokens: Thinking/reasoning tokens (separate from output)
    """
    provider: str  # "openai", "google", etc.
    model: str
    total_cost: float
    input_cost: float = 0.0
    output_cost: float = 0.0
    reasoning_cost: float = 0.0  # Separate from output_cost

    # Token breakdown (all preserved for accuracy)
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0  # Separate from output_tokens

    # Image-specific
    image_size: Optional[str] = None  # "1K", "2K", "4K" or "1024x1024"
    image_count: int = 0


@dataclass
class ImageResponse:
    """Response from image generation."""
    images: List[bytes]  # Raw image data
    model: str
    usage: Optional[TokenUsage] = None
    cost: Optional[CostInfo] = None  # Provider-calculated cost
    raw_response: Any = None
