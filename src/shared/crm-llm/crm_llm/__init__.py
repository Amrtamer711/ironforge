"""
CRM LLM - Shared LLM client library.

Provides a unified interface for LLM providers with support for:
- Text completions (streaming and non-streaming)
- Image generation
- File uploads
- Cost tracking (via injectable cost logger)
- Tool/function calling

Usage:
    from crm_llm import LLMClient, LLMMessage, OpenAIProvider

    # Create provider with API key
    provider = OpenAIProvider(api_key="sk-...")

    # Create client
    client = LLMClient(provider)

    # Simple completion
    response = await client.complete([
        LLMMessage.system("You are a helpful assistant."),
        LLMMessage.user("Hello!")
    ])
    print(response.content)
"""

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
from crm_llm.client import LLMClient
from crm_llm.cost_tracker import CostLogger, ConsoleCostLogger, NullCostLogger
from crm_llm.providers.openai import OpenAIProvider

# Google provider is optional (requires google-genai package)
try:
    from crm_llm.providers.google import GoogleProvider
    _google_available = True
except ImportError:
    GoogleProvider = None  # type: ignore
    _google_available = False

__all__ = [
    # Client
    "LLMClient",
    # Base types
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
    # Cost tracking
    "CostLogger",
    "ConsoleCostLogger",
    "NullCostLogger",
    # Providers
    "OpenAIProvider",
]

# Add GoogleProvider to exports if available
if _google_available:
    __all__.append("GoogleProvider")
