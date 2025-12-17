# Booking order editing JSON schemas for structured LLM outputs

from integrations.llm import JSONSchema


def get_coordinator_response_schema() -> JSONSchema:
    """
    JSON schema for coordinator thread response.

    Used to parse coordinator intent when editing booking orders in approval threads,
    determining action type (execute/edit/view) and field changes.
    """
    return JSONSchema(
        name="coordinator_response",
        schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["execute", "edit", "view"]},
                "fields": {
                    "type": "object",
                    "properties": {
                        "client": {"type": "string"},
                        "brand_campaign": {"type": "string"},
                        "bo_number": {"type": "string"},
                        "bo_date": {"type": "string"},
                        "net_pre_vat": {"type": "number"},
                        "vat_value": {"type": "number"},
                        "vat_calc": {"type": "number"},
                        "gross_amount": {"type": "number"},
                        "gross_calc": {"type": "number"},
                        "agency": {"type": "string"},
                        "sales_person": {"type": "string"},
                        "sla_pct": {"type": "number"},
                        "payment_terms": {"type": "string"},
                        "commission_pct": {"type": "number"},
                        "notes": {"type": "string"},
                        "category": {"type": "string"},
                        "municipality_fee": {"type": "number"},
                        "production_upload_fee": {"type": "number"},
                        "currency": {"type": "string"},
                        "asset": {
                            "anyOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}}
                            ]
                        },
                        "locations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "asset": {"type": "string"},
                                    "start_date": {"type": "string"},
                                    "end_date": {"type": "string"},
                                    "campaign_duration": {"type": "string"},
                                    "net_amount": {"type": "number"}
                                }
                            }
                        }
                    },
                    "additionalProperties": True
                },
                "message": {"type": "string"}
            },
            "required": ["action"],
            "additionalProperties": False
        },
        strict=False  # Not strict to allow flexible field updates
    )


def get_bo_edit_response_schema() -> JSONSchema:
    """
    JSON schema for booking order edit response.

    Used to parse user intent when editing booking orders,
    determining action type (approve/cancel/edit/view) and field changes.
    """
    return JSONSchema(
        name="booking_order_edit_response",
        schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["approve", "cancel", "edit", "view"]},
                "fields": {
                    "type": "object",
                    "properties": {
                        "client": {"type": "string"},
                        "brand_campaign": {"type": "string"},
                        "bo_number": {"type": "string"},
                        "bo_date": {"type": "string"},
                        "net_pre_vat": {"type": "number"},
                        "vat_calc": {"type": "number"},
                        "gross_calc": {"type": "number"},
                        "agency": {"type": "string"},
                        "sales_person": {"type": "string"},
                        "sla_pct": {"type": "number"},
                        "payment_terms": {"type": "string"},
                        "commission_pct": {"type": "number"},
                        "notes": {"type": "string"},
                        "category": {"type": "string"},
                        "asset": {"type": "string"}
                    },
                    "additionalProperties": True  # Allow locations and other fields
                },
                "message": {"type": "string"}
            },
            "required": ["action"],
            "additionalProperties": False
        },
        strict=False  # Not strict to allow flexible field updates
    )
