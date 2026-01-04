"""
JSON Schemas for LLM Responses.

Defines structured response schemas for various LLM interactions.
These schemas are used with json_schema parameter in LLM calls
to ensure consistent, parseable responses.
"""

from typing import Any

# Schema for confirmation responses (confirm/cancel/edit/view)
CONFIRMATION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["confirm", "cancel", "edit", "view"]},
        "fields": {"type": "object"},
        "message": {"type": "string"},
    },
    "required": ["action", "message"],
}

# Schema for duplicate confirmation responses
DUPLICATE_CONFIRMATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["accept", "cancel", "edit"]},
        "message": {"type": "string"},
    },
    "required": ["action"],
}

# Schema for delete confirmation responses
DELETE_CONFIRMATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["confirm", "cancel"]},
        "message": {"type": "string"},
    },
    "required": ["action"],
}

# Schema for task edit responses
EDIT_TASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["save", "cancel", "edit", "view"]},
        "fields": {"type": "object"},
        "message": {"type": "string"},
    },
    "required": ["action"],
}

# Schema for edit duplicate confirmation responses
EDIT_DUPLICATE_CONFIRMATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["accept", "cancel", "edit"]},
        "message": {"type": "string"},
    },
    "required": ["action"],
}
