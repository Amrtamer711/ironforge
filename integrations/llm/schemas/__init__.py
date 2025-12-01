# JSON schemas for structured LLM outputs

from integrations.llm import JSONSchema
from integrations.llm.schemas.bo_parsing import (
    get_classification_schema,
    get_booking_order_extraction_schema,
)
from integrations.llm.schemas.bo_editing import (
    get_bo_edit_response_schema,
    get_coordinator_response_schema,
)

__all__ = [
    "JSONSchema",
    "get_classification_schema",
    "get_booking_order_extraction_schema",
    "get_bo_edit_response_schema",
    "get_coordinator_response_schema",
]
