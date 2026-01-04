"""
LLM Prompts for Video Critique.

Centralized prompt management for all LLM interactions.
"""

from integrations.llm.prompts.design_request import create_design_request_system_prompt
from integrations.llm.prompts.editing import create_edit_system_prompt

__all__ = [
    "create_design_request_system_prompt",
    "create_edit_system_prompt",
]
