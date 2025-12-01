# Booking order parsing JSON schemas for structured LLM outputs

from integrations.llm import JSONSchema


def get_classification_schema() -> JSONSchema:
    """
    JSON schema for booking order classification response.

    Used to classify uploaded documents as BOOKING_ORDER or ARTWORK
    and identify the company (backlite/viola).
    """
    return JSONSchema(
        name="classification_response",
        schema={
            "type": "object",
            "properties": {
                "classification": {
                    "type": "string",
                    "enum": ["BOOKING_ORDER", "ARTWORK"]
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"]
                },
                "company": {
                    "type": ["string", "null"],
                    "enum": ["backlite", "viola", None]
                },
                "reasoning": {
                    "type": "string"
                }
            },
            "required": ["classification", "confidence", "company", "reasoning"],
            "additionalProperties": False
        },
        strict=True
    )


def get_booking_order_extraction_schema() -> JSONSchema:
    """
    JSON schema for booking order data extraction.

    Defines the structure for extracting all booking order fields
    including locations, fees, dates, and financial information.
    """
    return JSONSchema(
        name="booking_order_extraction",
        schema={
            "type": "object",
            "properties": {
                "bo_number": {"type": ["string", "null"]},
                "bo_date": {"type": ["string", "null"]},
                "client": {"type": ["string", "null"]},
                "agency": {"type": ["string", "null"]},
                "brand_campaign": {"type": ["string", "null"]},
                "category": {"type": ["string", "null"]},
                "asset": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "null"}
                    ]
                },
                "payment_terms": {"type": ["string", "null"]},
                "sales_person": {"type": ["string", "null"]},
                "currency": {"type": ["string", "null"]},
                "commission_pct": {"type": ["number", "null"]},
                "sla_pct": {"type": ["number", "null"]},
                "municipality_fee": {"type": ["number", "null"]},
                "production_upload_fee": {"type": ["number", "null"]},
                "net_pre_vat": {"type": ["number", "null"]},
                "vat_value": {"type": ["number", "null"]},
                "gross_amount": {"type": ["number", "null"]},
                "notes": {"type": ["string", "null"]},
                "locations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "asset": {"type": ["string", "null"]},
                            "start_date": {"type": "string"},
                            "end_date": {"type": "string"},
                            "campaign_duration": {"type": "string"},
                            "net_amount": {"type": "number"}
                        },
                        "required": ["name", "start_date", "end_date", "campaign_duration", "net_amount", "asset"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["bo_number", "bo_date", "client", "agency", "brand_campaign", "category", "asset", "payment_terms", "sales_person", "currency", "commission_pct", "sla_pct", "municipality_fee", "production_upload_fee", "net_pre_vat", "vat_value", "gross_amount", "notes", "locations"],
            "additionalProperties": False
        },
        strict=True
    )
