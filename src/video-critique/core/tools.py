"""
LLM Tool Definitions for Video Critique.

Provides tool definitions for the LLM conversation loop.
These tools are used by the AI assistant to interact with
the video production workflow system.
"""

from typing import Any

from integrations.llm import ToolDefinition, JSONSchema


def get_tool_definitions() -> list[ToolDefinition]:
    """
    Get all available tool definitions for the LLM.

    Returns:
        List of ToolDefinition objects
    """
    return [
        log_design_request_tool(),
        edit_task_tool(),
        delete_task_tool(),
        export_current_data_tool(),
        manage_videographer_tool(),
        manage_location_tool(),
        manage_salesperson_tool(),
        update_person_ids_tool(),
        edit_reviewer_tool(),
        edit_hod_tool(),
        edit_head_of_sales_tool(),
    ]


def get_tool_definitions_raw() -> list[dict[str, Any]]:
    """
    Get tool definitions in raw dict format for OpenAI API.

    Returns:
        List of tool definition dicts
    """
    return [
        {
            "type": "function",
            "name": "log_design_request",
            "description": "Log a new design request with specific details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "brand": {"type": "string", "description": "Brand or client name"},
                    "campaign_start_date": {
                        "type": "string",
                        "description": "Campaign start date in YYYY-MM-DD format",
                    },
                    "campaign_end_date": {
                        "type": "string",
                        "description": "Campaign end date in YYYY-MM-DD format",
                    },
                    "reference_number": {
                        "type": "string",
                        "description": "Reference number",
                    },
                    "location": {
                        "type": "string",
                        "description": "Campaign location (required)",
                    },
                    "sales_person": {
                        "type": "string",
                        "description": "Sales person name (required)",
                    },
                    "task_type": {
                        "type": "string",
                        "description": "Task type: 'videography', 'photography', or 'both'",
                        "enum": ["videography", "photography", "both"],
                    },
                    "time_block": {
                        "type": "string",
                        "description": "Time block: 'day', 'night', or 'both'. Required for all tasks.",
                        "enum": ["day", "night", "both"],
                    },
                },
                "required": [
                    "brand",
                    "campaign_start_date",
                    "campaign_end_date",
                    "reference_number",
                    "location",
                    "sales_person",
                    "task_type",
                    "time_block",
                ],
            },
        },
        {
            "type": "function",
            "name": "export_current_data",
            "description": "Export task data as Excel files. Sends live tasks and optionally historical tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_history": {
                        "type": "boolean",
                        "description": "Include historical/completed tasks. Default false.",
                        "default": False,
                    }
                },
            },
        },
        {
            "type": "function",
            "name": "edit_task",
            "description": "Edit or view details of an existing task by task number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_number": {
                        "type": "integer",
                        "description": "The task number to edit",
                    }
                },
                "required": ["task_number"],
            },
        },
        {
            "type": "function",
            "name": "delete_task",
            "description": "Delete an existing task by task number. This action archives the task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_number": {
                        "type": "integer",
                        "description": "The task number to delete",
                    }
                },
                "required": ["task_number"],
            },
        },
        {
            "type": "function",
            "name": "manage_videographer",
            "description": "Manage videographers in the system - add, remove, or list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "remove", "list"],
                        "description": "The action to perform",
                    },
                    "name": {
                        "type": "string",
                        "description": "Videographer name (required for add/remove)",
                    },
                    "email": {
                        "type": "string",
                        "description": "Videographer email (required for add)",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User ID for notifications (optional)",
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Channel ID for notifications (optional)",
                    },
                },
                "required": ["action"],
            },
        },
        {
            "type": "function",
            "name": "manage_location",
            "description": "Manage location to videographer mappings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "remove", "list"],
                        "description": "The action to perform",
                    },
                    "location": {
                        "type": "string",
                        "description": "Location name (required for add/remove)",
                    },
                    "videographer": {
                        "type": "string",
                        "description": "Videographer to assign (required for add)",
                    },
                },
                "required": ["action"],
            },
        },
        {
            "type": "function",
            "name": "manage_salesperson",
            "description": "Manage salespeople in the system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "remove", "list"],
                        "description": "The action to perform",
                    },
                    "name": {
                        "type": "string",
                        "description": "Salesperson name (required for add/remove)",
                    },
                    "email": {
                        "type": "string",
                        "description": "Salesperson email (required for add)",
                    },
                    "user_id": {"type": "string", "description": "User ID for notifications"},
                    "channel_id": {"type": "string", "description": "Channel ID for notifications"},
                },
                "required": ["action"],
            },
        },
        {
            "type": "function",
            "name": "update_person_ids",
            "description": "Update user ID and/or channel ID for a person.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_type": {
                        "type": "string",
                        "enum": ["videographers", "sales_people", "reviewer", "hod"],
                        "description": "Type of person to update",
                    },
                    "person_name": {
                        "type": "string",
                        "description": "Name of the person (not required for reviewer)",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User ID for notifications",
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Channel ID for notifications",
                    },
                },
                "required": ["person_type"],
            },
        },
        {
            "type": "function",
            "name": "edit_reviewer",
            "description": "Edit the reviewer's information. Admin only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Reviewer's name"},
                    "email": {"type": "string", "description": "Reviewer's email"},
                    "user_id": {"type": "string", "description": "User ID for notifications"},
                    "channel_id": {"type": "string", "description": "Channel ID for notifications"},
                    "active": {"type": "boolean", "description": "Whether active"},
                },
                "required": [],
            },
        },
        {
            "type": "function",
            "name": "edit_hod",
            "description": "Edit the Head of Department's information. Admin only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "HOD's name"},
                    "email": {"type": "string", "description": "HOD's email"},
                    "user_id": {"type": "string", "description": "User ID for notifications"},
                    "channel_id": {"type": "string", "description": "Channel ID for notifications"},
                    "active": {"type": "boolean", "description": "Whether active"},
                },
                "required": [],
            },
        },
        {
            "type": "function",
            "name": "edit_head_of_sales",
            "description": "Edit the Head of Sales' information. Admin only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Head of Sales' name"},
                    "email": {"type": "string", "description": "Head of Sales' email"},
                    "user_id": {"type": "string", "description": "User ID for notifications"},
                    "channel_id": {"type": "string", "description": "Channel ID for notifications"},
                    "active": {"type": "boolean", "description": "Whether active"},
                },
                "required": [],
            },
        },
    ]


# ========================================================================
# TOOL DEFINITION BUILDERS
# ========================================================================


def log_design_request_tool() -> ToolDefinition:
    """Create tool definition for logging design requests."""
    return ToolDefinition(
        name="log_design_request",
        description="Log a new design request with specific details.",
        parameters=JSONSchema(
            type="object",
            properties={
                "brand": {"type": "string", "description": "Brand or client name"},
                "campaign_start_date": {
                    "type": "string",
                    "description": "Campaign start date in YYYY-MM-DD format",
                },
                "campaign_end_date": {
                    "type": "string",
                    "description": "Campaign end date in YYYY-MM-DD format",
                },
                "reference_number": {"type": "string", "description": "Reference number"},
                "location": {"type": "string", "description": "Campaign location"},
                "sales_person": {"type": "string", "description": "Sales person name"},
                "task_type": {
                    "type": "string",
                    "description": "Task type",
                    "enum": ["videography", "photography", "both"],
                },
                "time_block": {
                    "type": "string",
                    "description": "Time block",
                    "enum": ["day", "night", "both"],
                },
            },
            required=[
                "brand",
                "campaign_start_date",
                "campaign_end_date",
                "reference_number",
                "location",
                "sales_person",
                "task_type",
                "time_block",
            ],
        ),
    )


def edit_task_tool() -> ToolDefinition:
    """Create tool definition for editing tasks."""
    return ToolDefinition(
        name="edit_task",
        description="Edit or view details of an existing task by task number.",
        parameters=JSONSchema(
            type="object",
            properties={
                "task_number": {
                    "type": "integer",
                    "description": "The task number to edit",
                },
            },
            required=["task_number"],
        ),
    )


def delete_task_tool() -> ToolDefinition:
    """Create tool definition for deleting tasks."""
    return ToolDefinition(
        name="delete_task",
        description="Delete an existing task by task number. Archives the task.",
        parameters=JSONSchema(
            type="object",
            properties={
                "task_number": {
                    "type": "integer",
                    "description": "The task number to delete",
                },
            },
            required=["task_number"],
        ),
    )


def export_current_data_tool() -> ToolDefinition:
    """Create tool definition for exporting data."""
    return ToolDefinition(
        name="export_current_data",
        description="Export task data as Excel files.",
        parameters=JSONSchema(
            type="object",
            properties={
                "include_history": {
                    "type": "boolean",
                    "description": "Include historical tasks",
                },
            },
            required=[],
        ),
    )


def manage_videographer_tool() -> ToolDefinition:
    """Create tool definition for managing videographers."""
    return ToolDefinition(
        name="manage_videographer",
        description="Manage videographers - add, remove, or list.",
        parameters=JSONSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "description": "Action to perform",
                    "enum": ["add", "remove", "list"],
                },
                "name": {"type": "string", "description": "Videographer name"},
                "email": {"type": "string", "description": "Videographer email"},
                "user_id": {"type": "string", "description": "User ID for notifications"},
                "channel_id": {"type": "string", "description": "Channel ID for notifications"},
            },
            required=["action"],
        ),
    )


def manage_location_tool() -> ToolDefinition:
    """Create tool definition for managing locations."""
    return ToolDefinition(
        name="manage_location",
        description="Manage location to videographer mappings.",
        parameters=JSONSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "description": "Action to perform",
                    "enum": ["add", "remove", "list"],
                },
                "location": {"type": "string", "description": "Location name"},
                "videographer": {"type": "string", "description": "Videographer name"},
            },
            required=["action"],
        ),
    )


def manage_salesperson_tool() -> ToolDefinition:
    """Create tool definition for managing salespeople."""
    return ToolDefinition(
        name="manage_salesperson",
        description="Manage salespeople in the system.",
        parameters=JSONSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "description": "Action to perform",
                    "enum": ["add", "remove", "list"],
                },
                "name": {"type": "string", "description": "Salesperson name"},
                "email": {"type": "string", "description": "Salesperson email"},
                "user_id": {"type": "string", "description": "User ID for notifications"},
                "channel_id": {"type": "string", "description": "Channel ID for notifications"},
            },
            required=["action"],
        ),
    )


def update_person_ids_tool() -> ToolDefinition:
    """Create tool definition for updating notification IDs."""
    return ToolDefinition(
        name="update_person_ids",
        description="Update user ID and/or channel ID for a person.",
        parameters=JSONSchema(
            type="object",
            properties={
                "person_type": {
                    "type": "string",
                    "description": "Type of person",
                    "enum": ["videographers", "sales_people", "reviewer", "hod"],
                },
                "person_name": {"type": "string", "description": "Person name"},
                "user_id": {"type": "string", "description": "User ID for notifications"},
                "channel_id": {"type": "string", "description": "Channel ID for notifications"},
            },
            required=["person_type"],
        ),
    )


def edit_reviewer_tool() -> ToolDefinition:
    """Create tool definition for editing reviewer."""
    return ToolDefinition(
        name="edit_reviewer",
        description="Edit the reviewer's information. Admin only.",
        parameters=JSONSchema(
            type="object",
            properties={
                "name": {"type": "string", "description": "Reviewer name"},
                "email": {"type": "string", "description": "Reviewer email"},
                "user_id": {"type": "string", "description": "User ID for notifications"},
                "channel_id": {"type": "string", "description": "Channel ID for notifications"},
                "active": {"type": "boolean", "description": "Whether active"},
            },
            required=[],
        ),
    )


def edit_hod_tool() -> ToolDefinition:
    """Create tool definition for editing HOD."""
    return ToolDefinition(
        name="edit_hod",
        description="Edit the Head of Department's information. Admin only.",
        parameters=JSONSchema(
            type="object",
            properties={
                "name": {"type": "string", "description": "HOD name"},
                "email": {"type": "string", "description": "HOD email"},
                "user_id": {"type": "string", "description": "User ID for notifications"},
                "channel_id": {"type": "string", "description": "Channel ID for notifications"},
                "active": {"type": "boolean", "description": "Whether active"},
            },
            required=[],
        ),
    )


def edit_head_of_sales_tool() -> ToolDefinition:
    """Create tool definition for editing Head of Sales."""
    return ToolDefinition(
        name="edit_head_of_sales",
        description="Edit the Head of Sales' information. Admin only.",
        parameters=JSONSchema(
            type="object",
            properties={
                "name": {"type": "string", "description": "Head of Sales name"},
                "email": {"type": "string", "description": "Head of Sales email"},
                "user_id": {"type": "string", "description": "User ID for notifications"},
                "channel_id": {"type": "string", "description": "Channel ID for notifications"},
                "active": {"type": "boolean", "description": "Whether active"},
            },
            required=[],
        ),
    )
