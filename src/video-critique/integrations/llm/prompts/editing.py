"""
Task Editing System Prompt.

Provides the system prompt for the LLM when handling task edits.
"""

import json
from datetime import datetime
from typing import Any

import config


def create_edit_system_prompt(
    task_number: int,
    current_data: dict[str, Any],
    user_input: str,
    videographers: list[str] | None = None,
    sales_people: list[str] | None = None,
    locations: list[str] | None = None,
) -> str:
    """
    Create system prompt for task editing.

    Args:
        task_number: Task number being edited
        current_data: Current task data
        user_input: What the user said
        videographers: List of valid videographer names/emails
        sales_people: List of valid sales person names
        locations: List of valid location keys

    Returns:
        System prompt string
    """
    now = datetime.now(config.UAE_TZ)
    today_str = now.strftime("%d-%m-%Y")

    # Use provided lists or empty defaults
    videographers = videographers or []
    sales_people = sales_people or []
    locations = locations or []

    return f"""You are helping edit Task #{task_number}. The user said: "{user_input}"

Determine their intent and parse any field updates:
- If they want to save/confirm/done: action = 'save'
- If they want to cancel/stop/exit: action = 'cancel'
- If they want to see current values: action = 'view'
- If they're making changes: action = 'edit' and parse the field updates

Current task data: {json.dumps(current_data, indent=2)}

VALIDATION RULES:
1. Sales Person MUST be one of: {sales_people}
2. Location MUST be one of: {locations}
3. Videographer MUST be one of: {videographers}
4. Status MUST be one of:
   - "Not assigned yet"
   - "Assigned to [Videographer Name]"
   - "Raw", "Critique", "Editing"
   - "Submitted to Sales", "Returned", "Done"
   - "Permanently Rejected"

DATE VALIDATION (today: {today_str}):
- Campaign dates must be today or in the future
- End date must be >= start date
- Filming date should be between campaign dates

Return JSON with: action, fields (only changed fields with VALID values), message.
Use natural language in messages - say 'Sales Person' not 'sales_person'."""
