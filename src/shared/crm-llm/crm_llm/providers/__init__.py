"""
LLM Provider implementations.

Available providers:
- OpenAIProvider: OpenAI API (GPT-5.1, gpt-image-1)
- GoogleProvider: Google Gemini API (gemini-2.5-flash, gemini-3-pro-image-preview)
"""

from crm_llm.providers.openai import OpenAIProvider

# Google provider is optional (requires google-genai package)
try:
    from crm_llm.providers.google import GoogleProvider
    __all__ = ["OpenAIProvider", "GoogleProvider"]
except ImportError:
    __all__ = ["OpenAIProvider"]
