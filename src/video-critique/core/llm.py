"""
LLM Conversation Loop for Video Critique.

Provides the main conversational interface that:
- Works with any channel (Slack, Web) via ChannelAdapter
- Uses LLMClient from integrations/llm
- Manages conversation state (confirmations, edits, deletes)
- Delegates tool execution to handlers/tool_router
- Supports vision/image analysis for design request parsing

This is channel-agnostic - the same code works for both
Slack webhooks and Web chat endpoints.
"""

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from integrations.channels import ChannelAdapter
from integrations.llm import LLMClient, LLMMessage, ToolDefinition, ContentPart
from core.tools import get_tool_definitions
from core.utils.logging import get_logger

import config

logger = get_logger(__name__)


# ============================================================================
# CONVERSATION STATE
# ============================================================================

@dataclass
class ConversationState:
    """Tracks state for a user's ongoing conversation."""
    user_id: str
    history: list[dict] = field(default_factory=list)
    pending_confirmation: dict | None = None
    pending_edit: dict | None = None
    pending_delete: dict | None = None


# In-memory conversation state storage
# In production, this could be moved to Redis/database for persistence
_conversation_states: dict[str, ConversationState] = {}


def get_conversation_state(user_id: str) -> ConversationState:
    """Get or create conversation state for a user."""
    if user_id not in _conversation_states:
        _conversation_states[user_id] = ConversationState(user_id=user_id)
    return _conversation_states[user_id]


def clear_conversation_state(user_id: str) -> None:
    """Clear all conversation state for a user."""
    if user_id in _conversation_states:
        del _conversation_states[user_id]


def append_to_history(user_id: str, role: str, content: str) -> None:
    """Append a message to user's conversation history."""
    state = get_conversation_state(user_id)
    state.history.append({"role": role, "content": content})

    # Keep history to a reasonable size (last 20 messages)
    if len(state.history) > 20:
        state.history = state.history[-20:]


# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

def create_design_request_system_prompt(
    user_name: str,
    config_data: dict[str, Any] | None = None,
) -> str:
    """
    Create the system prompt for design request handling.

    Args:
        user_name: Display name of the user
        config_data: Optional config with sales_people, locations, videographers

    Returns:
        System prompt string
    """
    now = datetime.now(config.UAE_TZ)
    today_str = now.strftime("%B %d, %Y")
    day_of_week = now.strftime("%A")
    tomorrow_str = (now + timedelta(days=1)).strftime("%B %d, %Y")

    # Get mapping data from config or use empty defaults
    config_data = config_data or {}
    sales_people = list(config_data.get("sales_people", {}).keys())
    locations = list(config_data.get("location_mappings", {}).keys())
    videographers = list(config_data.get("videographers", {}).keys())

    return f"""You are an AI assistant for design request management, helping users log and manage marketing design requests in a friendly, professional manner.

IMPORTANT: Always format your responses using proper Markdown syntax:
- Use **bold** for emphasis
- Use _italic_ for subtle emphasis
- Use `code` for reference numbers or technical terms
- Use bullet points (- item) for lists

Today's date is {today_str} ({day_of_week}).
If the user mentions dates like "today", "tomorrow", or weekdays without specific dates, interpret them relative to this date:
- "Tomorrow" means {tomorrow_str}
- "Next Monday" means the Monday after today
- "This Friday" means the upcoming Friday

IMPORTANT VALIDATION RULES:
1. Campaign End Date: ALWAYS reject any campaign where the end date has already passed.
2. Campaign Start Date: Campaigns can start today or in the future. Reject only if before today.
3. Campaign dates must be logical: start date should be before or equal to end date.

When a user wants to log a design request, they can:
- Paste an email with the request details
- Upload an image/screenshot of the request
- Provide the details manually

For ALL methods, you need to collect:
- Brand/Client name (required)
- Campaign start date (required)
- Campaign end date (required)
- Reference number (required)
- Location (required)
- Sales person name (required)
- Task type: 'videography', 'photography', or 'both' (required)
- Time block: 'day', 'night', or 'both' (required)

STRICT MAPPING RULES:
1. Sales Person MUST be one of: {sales_people}
   - Try fuzzy matching: "Nour" -> "Nourhan"

2. Location MUST be one of: {locations}
   - Common mappings: "TTC" -> "TTC Dubai", "Oryx" -> "The Oryx"

3. Videographer MUST be one of: {videographers}

When you have successfully parsed all required fields:
1. Call the `log_design_request` function with the parsed data
2. Do NOT show the parsed details - this will be handled automatically
3. The system will show the user what was parsed and ask for confirmation

Available tools:
1. `log_design_request`: Log a design request with all details
2. `export_current_data`: Export task data as Excel files
3. `edit_task`: Edit an existing task by task number
4. `delete_task`: Delete an existing task
5. `manage_videographer`: Add/remove/list videographers (admin only)
6. `manage_location`: Add/remove/list location mappings (admin only)
7. `manage_salesperson`: Add/remove/list salespeople (admin only)
8. `update_person_slack_ids`: Update Slack IDs for a person
9. `edit_reviewer`, `edit_hod`, `edit_head_of_sales`: Edit admin users

The user you're helping is named {user_name}.

Be conversational and helpful. If they seem unsure, explain the options clearly."""


def create_edit_system_prompt(
    task_number: int,
    current_data: dict[str, Any],
    user_input: str,
    config_data: dict[str, Any] | None = None,
) -> str:
    """
    Create system prompt for task editing.

    Args:
        task_number: Task number being edited
        current_data: Current task data
        user_input: What the user said
        config_data: Optional config with valid values

    Returns:
        System prompt string
    """
    now = datetime.now(config.UAE_TZ)
    today_str = now.strftime("%d-%m-%Y")

    config_data = config_data or {}
    sales_people = list(config_data.get("sales_people", {}).keys())
    locations = list(config_data.get("location_mappings", {}).keys())
    videographers = list(config_data.get("videographers", {}).keys())

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


# ============================================================================
# MAIN CONVERSATION LOOP
# ============================================================================

async def main_llm_loop(
    channel_id: str,
    user_id: str,
    user_input: str,
    files: list[dict] | None = None,
    channel: ChannelAdapter | None = None,
    user_name: str | None = None,
    tool_router: Any = None,
    config_data: dict[str, Any] | None = None,
) -> str:
    """
    Main conversational loop with LLM.

    This is channel-agnostic - works with both Slack and Web channels.

    Args:
        channel_id: Channel/conversation ID
        user_id: User's ID
        user_input: User's message text
        files: Optional list of file attachments
        channel: ChannelAdapter for sending messages (optional)
        user_name: User's display name (optional)
        tool_router: Tool router for executing tool calls (optional)
        config_data: Configuration data with valid values (optional)

    Returns:
        Assistant's response text
    """
    # Get conversation state
    state = get_conversation_state(user_id)

    # Send thinking indicator if channel provided
    thinking_msg_id = None
    if channel:
        try:
            result = await channel.send_message(
                channel_id=channel_id,
                content="Processing...",
            )
            thinking_msg_id = result.get("message_id")
        except Exception as e:
            logger.debug(f"Could not send thinking message: {e}")

    # Get user name if not provided
    if not user_name:
        user_name = "there"
        if channel:
            try:
                user_info = await channel.get_user_info(user_id)
                user_name = user_info.get("display_name") or user_info.get("name") or "there"
            except Exception:
                pass

    try:
        # Check for pending states that need special handling
        if state.pending_confirmation:
            answer = await _handle_confirmation_response(
                user_id, user_input, state, tool_router, config_data
            )
        elif state.pending_delete:
            answer = await _handle_delete_confirmation(
                user_id, user_input, state, tool_router
            )
        elif state.pending_edit:
            answer = await _handle_edit_flow(
                user_id, user_input, state, tool_router, config_data
            )
        else:
            # Normal conversation flow
            answer = await _handle_normal_conversation(
                user_id, user_input, user_name, files, state, tool_router, config_data
            )

        # Store history
        append_to_history(user_id, "user", user_input)
        append_to_history(user_id, "assistant", answer)

        # Send response
        if channel:
            # Delete thinking message
            if thinking_msg_id:
                try:
                    await channel.delete_message(channel_id, thinking_msg_id)
                except Exception:
                    pass

            # Send final response
            await channel.send_message(channel_id=channel_id, content=answer)

        return answer

    except Exception as e:
        logger.error(f"Error in main_llm_loop: {e}")
        error_msg = f"I encountered an error processing your request: {str(e)}"

        if channel:
            if thinking_msg_id:
                try:
                    await channel.delete_message(channel_id, thinking_msg_id)
                except Exception:
                    pass
            await channel.send_message(channel_id=channel_id, content=error_msg)

        return error_msg


async def _handle_normal_conversation(
    user_id: str,
    user_input: str,
    user_name: str,
    files: list[dict] | None,
    state: ConversationState,
    tool_router: Any,
    config_data: dict[str, Any] | None,
) -> str:
    """Handle normal conversation flow with LLM."""
    # Build messages
    system_prompt = create_design_request_system_prompt(user_name, config_data)

    messages = [
        LLMMessage.system(system_prompt),
        *[LLMMessage(role=m["role"], content=m["content"]) for m in state.history],
        LLMMessage.user(user_input),
    ]

    # Add file context if provided
    if files:
        # For now, note that files were provided
        # Full vision support would upload to provider first
        file_names = [f.get("name", "unknown") for f in files]
        messages[-1] = LLMMessage.user(
            f"{user_input}\n\n[Attached files: {', '.join(file_names)}]"
        )

    # Get tool definitions
    tools = get_tool_definitions()

    # Call LLM
    client = LLMClient.from_config()
    response = await client.complete(
        messages=messages,
        tools=tools,
        tool_choice="auto",
        workflow="design_request",
        user_id=user_id,
    )

    # Handle tool calls
    if response.tool_calls:
        tool_call = response.tool_calls[0]

        if tool_router:
            # Delegate to tool router
            result = await tool_router.route_tool_call(
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                user_id=user_id,
                user_name=user_name,
                state=state,
            )
            return result
        else:
            # No tool router - return info about the tool call
            return f"Tool called: {tool_call.name} with args: {tool_call.arguments}"

    # Return text response
    return response.content or "I'm not sure how to help with that. Could you rephrase?"


async def _handle_confirmation_response(
    user_id: str,
    user_input: str,
    state: ConversationState,
    tool_router: Any,
    config_data: dict[str, Any] | None,
) -> str:
    """Handle user response during design request confirmation."""
    pending_data = state.pending_confirmation

    # Check for duplicate confirmation mode
    if pending_data.get("_duplicate_confirm"):
        return await _handle_duplicate_confirmation(
            user_id, user_input, state, pending_data, tool_router
        )

    # Parse user intent
    client = LLMClient.from_config()

    system_prompt = """You are helping confirm or edit a design request.
Analyze the user's response and determine the action.
Return JSON with: action (confirm/cancel/edit/view), fields (only for edits), message.
Actions:
- confirm: User agrees (yes, yup, confirm, proceed, correct, looks good, etc.)
- cancel: User cancels (no, cancel, stop, nevermind, etc.)
- edit: User provides corrections (include ONLY changed fields)
- view: User wants to see current details"""

    current_summary = _format_request_summary(pending_data)

    response = await client.complete(
        messages=[
            LLMMessage.system(system_prompt),
            LLMMessage.user(f"Current request:\n{current_summary}\n\nUser response: {user_input}"),
        ],
        json_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["confirm", "cancel", "edit", "view"]},
                "fields": {"type": "object"},
                "message": {"type": "string"},
            },
            "required": ["action", "message"],
        },
        workflow="confirmation",
        user_id=user_id,
    )

    try:
        decision = json.loads(response.content)
    except json.JSONDecodeError:
        return "I didn't understand your response. Please say 'confirm' to save or 'cancel' to stop."

    action = decision.get("action")
    message = decision.get("message", "")

    if action == "confirm":
        # Delegate to tool router to save
        if tool_router:
            result = await tool_router.save_design_request(
                user_id=user_id,
                data=pending_data,
                state=state,
            )
            return result
        else:
            state.pending_confirmation = None
            return "Request confirmed (no handler available)."

    elif action == "cancel":
        state.pending_confirmation = None
        return message or "Request cancelled. No data was saved."

    elif action == "edit":
        # Apply edits
        fields = decision.get("fields", {})
        for key, value in fields.items():
            if value and str(value).strip():
                pending_data[key] = value.strip()

        # Show updated data
        answer = f"{message}\n\n**Updated details:**\n{_format_request_summary(pending_data)}"
        answer += "\n\nPlease confirm or continue editing."
        return answer

    elif action == "view":
        return f"**Current details:**\n{_format_request_summary(pending_data)}\n\nPlease confirm if correct or let me know what to change."

    return message or "Please say 'confirm' to save or provide corrections."


async def _handle_duplicate_confirmation(
    user_id: str,
    user_input: str,
    state: ConversationState,
    pending_data: dict,
    tool_router: Any,
) -> str:
    """Handle duplicate reference confirmation."""
    client = LLMClient.from_config()

    response = await client.complete(
        messages=[
            LLMMessage.system(
                "Parse duplicate reference confirmation. Return JSON with action: accept/cancel/edit"
            ),
            LLMMessage.user(user_input),
        ],
        json_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["accept", "cancel", "edit"]},
                "message": {"type": "string"},
            },
            "required": ["action"],
        },
        workflow="duplicate_confirm",
        user_id=user_id,
    )

    try:
        decision = json.loads(response.content)
    except json.JSONDecodeError:
        return "Please say 'yes' to proceed with duplicate, 'no' to cancel, or 'edit' to change."

    action = decision.get("action")

    if action == "accept":
        del pending_data["_duplicate_confirm"]
        if tool_router:
            result = await tool_router.save_design_request(
                user_id=user_id,
                data=pending_data,
                state=state,
                allow_duplicate=True,
            )
            return result
        state.pending_confirmation = None
        return "Request saved (duplicate accepted)."

    elif action == "cancel":
        state.pending_confirmation = None
        return "Request cancelled due to duplicate reference number."

    elif action == "edit":
        del pending_data["_duplicate_confirm"]
        return f"**Current details:**\n{_format_request_summary(pending_data)}\n\nPlease provide a different reference number."

    return "Please say 'yes', 'no', or 'edit'."


async def _handle_delete_confirmation(
    user_id: str,
    user_input: str,
    state: ConversationState,
    tool_router: Any,
) -> str:
    """Handle delete confirmation flow."""
    delete_data = state.pending_delete
    task_number = delete_data["task_number"]

    client = LLMClient.from_config()

    response = await client.complete(
        messages=[
            LLMMessage.system(
                f"Parse delete confirmation for Task #{task_number}. "
                "Return JSON with action: confirm/cancel"
            ),
            LLMMessage.user(user_input),
        ],
        json_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["confirm", "cancel"]},
                "message": {"type": "string"},
            },
            "required": ["action"],
        },
        workflow="delete_confirm",
        user_id=user_id,
    )

    try:
        decision = json.loads(response.content)
    except json.JSONDecodeError:
        return "Please say 'yes' to delete or 'no' to cancel."

    action = decision.get("action")

    if action == "confirm":
        if tool_router:
            result = await tool_router.delete_task(
                user_id=user_id,
                task_number=task_number,
                task_data=delete_data.get("task_data"),
                state=state,
            )
            return result
        state.pending_delete = None
        return f"Task #{task_number} deleted (no handler available)."

    else:
        state.pending_delete = None
        return f"Deletion cancelled. Task #{task_number} has been kept."


async def _handle_edit_flow(
    user_id: str,
    user_input: str,
    state: ConversationState,
    tool_router: Any,
    config_data: dict[str, Any] | None,
) -> str:
    """Handle task edit flow."""
    edit_data = state.pending_edit
    task_number = edit_data["task_number"]
    current_data = edit_data["current_data"]

    # Check for duplicate confirmation in edit mode
    if edit_data.get("_duplicate_confirm"):
        return await _handle_edit_duplicate_confirmation(
            user_id, user_input, state, edit_data, tool_router
        )

    # Parse edit intent
    client = LLMClient.from_config()
    system_prompt = create_edit_system_prompt(
        task_number, current_data, user_input, config_data
    )

    response = await client.complete(
        messages=[
            LLMMessage.system(system_prompt),
        ],
        json_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["save", "cancel", "edit", "view"]},
                "fields": {"type": "object"},
                "message": {"type": "string"},
            },
            "required": ["action"],
        },
        workflow="edit_task",
        user_id=user_id,
    )

    try:
        decision = json.loads(response.content)
    except json.JSONDecodeError:
        return "Please provide changes, say 'save' to commit, or 'cancel' to exit."

    action = decision.get("action")

    if action == "save":
        updates = edit_data.get("updates", {})
        if updates:
            if tool_router:
                result = await tool_router.save_task_edits(
                    user_id=user_id,
                    task_number=task_number,
                    updates=updates,
                    current_data=current_data,
                    state=state,
                )
                return result
            state.pending_edit = None
            return f"Task #{task_number} updated (no handler available)."
        else:
            state.pending_edit = None
            return f"No changes were made to Task #{task_number}."

    elif action == "cancel":
        state.pending_edit = None
        return f"Edit cancelled for Task #{task_number}. No changes were saved."

    elif action == "edit":
        fields = decision.get("fields", {})
        if fields:
            # Store updates
            if "updates" not in edit_data:
                edit_data["updates"] = {}

            actual_updates = {}
            for field, new_value in fields.items():
                if new_value and str(current_data.get(field, "")) != str(new_value):
                    actual_updates[field] = new_value

            if actual_updates:
                edit_data["updates"].update(actual_updates)

                answer = "**Updates recorded:**\n"
                for field, value in actual_updates.items():
                    answer += f"- {field}: {value}\n"
                answer += f"\n**Total pending changes:**\n"
                for field, value in edit_data["updates"].items():
                    answer += f"- {field}: {current_data.get(field, 'N/A')} -> {value}\n"
                answer += "\nContinue editing or say 'save' when done."
                return answer

        return decision.get("message", "Please provide the changes you want to make.")

    elif action == "view":
        updates = edit_data.get("updates", {})
        answer = f"**Current data for Task #{task_number}:**\n"
        for field in ["Brand", "Campaign Start Date", "Campaign End Date", "Reference Number",
                      "Location", "Sales Person", "Status", "Filming Date", "Videographer"]:
            current = current_data.get(field, "N/A")
            if field in updates:
                answer += f"- {field}: {current} -> **{updates[field]}** (pending)\n"
            else:
                answer += f"- {field}: {current}\n"
        answer += "\nContinue editing or say 'save' when done."
        return answer

    return "Please provide changes, say 'save' to commit, or 'cancel' to exit."


async def _handle_edit_duplicate_confirmation(
    user_id: str,
    user_input: str,
    state: ConversationState,
    edit_data: dict,
    tool_router: Any,
) -> str:
    """Handle duplicate reference confirmation during edit."""
    task_number = edit_data["task_number"]

    client = LLMClient.from_config()

    response = await client.complete(
        messages=[
            LLMMessage.system(
                f"Parse duplicate confirmation for Task #{task_number} edit. "
                "Return JSON with action: accept/cancel/edit"
            ),
            LLMMessage.user(user_input),
        ],
        json_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["accept", "cancel", "edit"]},
                "message": {"type": "string"},
            },
            "required": ["action"],
        },
        workflow="edit_duplicate_confirm",
        user_id=user_id,
    )

    try:
        decision = json.loads(response.content)
    except json.JSONDecodeError:
        return "Please say 'save' to proceed, 'cancel' to stop, or 'edit' to continue."

    action = decision.get("action")

    if action == "accept":
        del edit_data["_duplicate_confirm"]
        updates = edit_data.get("updates", {})
        if tool_router:
            result = await tool_router.save_task_edits(
                user_id=user_id,
                task_number=task_number,
                updates=updates,
                current_data=edit_data["current_data"],
                state=state,
                allow_duplicate=True,
            )
            return result
        state.pending_edit = None
        return f"Task #{task_number} updated (duplicate accepted)."

    elif action == "cancel":
        state.pending_edit = None
        return f"Edit cancelled for Task #{task_number}."

    elif action == "edit":
        del edit_data["_duplicate_confirm"]
        answer = "**Current pending changes:**\n"
        for field, value in edit_data.get("updates", {}).items():
            answer += f"- {field}: {edit_data['current_data'].get(field, 'N/A')} -> {value}\n"
        answer += "\nPlease provide a new reference number."
        return answer

    return "Please say 'save', 'cancel', or 'edit'."


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _format_request_summary(data: dict) -> str:
    """Format a design request for display."""
    lines = []
    lines.append(f"- **Brand:** {data.get('brand', 'N/A')}")

    start_date = data.get("start_date", data.get("campaign_start_date", ""))
    end_date = data.get("end_date", data.get("campaign_end_date", ""))

    if start_date:
        lines.append(f"- **Campaign Start:** {start_date}")
    if end_date:
        lines.append(f"- **Campaign End:** {end_date}")

    lines.append(f"- **Reference:** `{data.get('reference_number', 'N/A')}`")

    if data.get("location"):
        lines.append(f"- **Location:** {data.get('location')}")
    if data.get("sales_person"):
        lines.append(f"- **Sales Person:** {data.get('sales_person')}")
    if data.get("task_type"):
        lines.append(f"- **Task Type:** {data.get('task_type')}")
    if data.get("time_block"):
        lines.append(f"- **Time Block:** {data.get('time_block')}")

    return "\n".join(lines)


def render_task_summary(task_data: dict) -> str:
    """Format task data for display."""
    lines = []
    lines.append(f"- **Brand:** {task_data.get('Brand', 'N/A')}")
    lines.append(f"- **Campaign:** {task_data.get('Campaign Start Date', 'N/A')} to {task_data.get('Campaign End Date', 'N/A')}")
    lines.append(f"- **Reference:** `{task_data.get('Reference Number', 'N/A')}`")
    lines.append(f"- **Location:** {task_data.get('Location', 'N/A')}")
    lines.append(f"- **Sales Person:** {task_data.get('Sales Person', 'N/A')}")
    lines.append(f"- **Status:** {task_data.get('Status', 'N/A')}")

    if task_data.get("Filming Date"):
        lines.append(f"- **Filming Date:** {task_data.get('Filming Date')}")
    if task_data.get("Videographer"):
        lines.append(f"- **Videographer:** {task_data.get('Videographer')}")

    return "\n".join(lines)
