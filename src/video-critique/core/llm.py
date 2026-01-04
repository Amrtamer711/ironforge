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

Follows the same patterns as sales-module for consistency:
- WorkflowContext for request-scoped context passing
- Proper LLM parameters (cache_key, call_type, metadata, context)
- User identity passed as display name for cost tracking
"""

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from integrations.channels import ChannelAdapter
from integrations.llm import LLMClient, LLMMessage, ToolDefinition, ContentPart
from integrations.llm.prompts import create_design_request_system_prompt, create_edit_system_prompt
from integrations.llm.schemas import (
    CONFIRMATION_RESPONSE_SCHEMA,
    DELETE_CONFIRMATION_SCHEMA,
    DUPLICATE_CONFIRMATION_SCHEMA,
    EDIT_DUPLICATE_CONFIRMATION_SCHEMA,
    EDIT_TASK_SCHEMA,
)
from core.tools import get_tool_definitions
from core.workflow_context import WorkflowContext
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
# MAIN CONVERSATION LOOP
# ============================================================================

async def main_llm_loop(
    channel_id: str,
    user_id: str,
    user_input: str,
    image_data: list[tuple[bytes, str]] | None = None,
    channel: ChannelAdapter | None = None,
    user_name: str | None = None,
    user_email: str | None = None,
    user_companies: list[str] | None = None,
    tool_router: Any = None,
) -> str:
    """
    Main conversational loop with LLM.

    This is channel-agnostic - works with both Slack and Web channels.
    Follows the same patterns as sales-module for consistency.

    Args:
        channel_id: Channel/conversation ID
        user_id: User's ID (Slack ID or platform user ID)
        user_input: User's message text
        image_data: Optional list of (image_bytes, mimetype) tuples for vision
        channel: ChannelAdapter for sending messages (optional)
        user_name: User's display name (optional)
        user_email: User's email address (optional, used as primary identifier)
        user_companies: List of company schemas user has access to (for RBAC)
        tool_router: Tool router for executing tool calls (optional)

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

    # Resolve user name if not provided
    if not user_name:
        user_name = "there"
        if channel:
            try:
                user_info = await channel.get_user_info(user_id)
                user_name = user_info.get("display_name") or user_info.get("name") or "there"
            except Exception:
                pass

    # Pre-load locations for user's companies (follows sales-module pattern)
    company_locations = []
    if user_companies:
        try:
            from core.services import get_asset_service
            asset_service = get_asset_service()
            company_locations = await asset_service.get_locations_for_companies(user_companies)
            logger.debug(f"[LLM] Pre-loaded {len(company_locations)} locations for {len(user_companies)} companies")
        except Exception as e:
            logger.warning(f"[LLM] Failed to pre-load locations: {e}")

    # Validate config is accessible (ConfigService has TTL cache, called directly where needed)
    from core.services import get_config_service
    config_service = get_config_service()
    logger.debug(
        f"[LLM] Config available: "
        f"{len(config_service.get_videographer_names())} videographers, "
        f"{len(config_service.get_sales_people_names())} sales people, "
        f"{len(config_service.get_location_names())} locations"
    )

    # Create workflow context with pre-loaded locations (follows sales-module pattern)
    workflow_ctx = WorkflowContext.create(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        user_companies=user_companies or [],
        locations_list=company_locations,
    )

    try:
        # Check for pending states that need special handling
        if state.pending_confirmation:
            answer = await _handle_confirmation_response(
                user_id, user_input, state, tool_router, workflow_ctx
            )
        elif state.pending_delete:
            answer = await _handle_delete_confirmation(
                user_id, user_input, state, tool_router, workflow_ctx
            )
        elif state.pending_edit:
            answer = await _handle_edit_flow(
                user_id, user_input, state, tool_router, workflow_ctx
            )
        else:
            # Normal conversation flow
            answer = await _handle_normal_conversation(
                user_id, user_input, image_data, state, tool_router, workflow_ctx
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
    image_data: list[tuple[bytes, str]] | None,
    state: ConversationState,
    tool_router: Any,
    workflow_ctx: WorkflowContext,
) -> str:
    """Handle normal conversation flow with LLM."""
    # Build messages
    user_name = workflow_ctx.get_display_name()

    # Call ConfigService directly (follows sales-module pattern - don't store on WorkflowContext)
    from core.services import get_config_service
    config_service = get_config_service()
    system_prompt = create_design_request_system_prompt(
        user_name,
        videographers=config_service.get_videographer_names(),
        sales_people=config_service.get_sales_people_names(),
        locations=config_service.get_location_names(),
    )

    messages = [
        LLMMessage.system(system_prompt),
        *[LLMMessage(role=m["role"], content=m["content"]) for m in state.history],
    ]

    # Build user message content - with vision support if images provided
    has_images = bool(image_data)
    if image_data:
        # Create multimodal content with images
        content_parts = [ContentPart.text(user_input or "Please extract the design request details from this image.")]

        for img_bytes, mimetype in image_data:
            # Convert to base64 for vision API
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")
            content_parts.append(ContentPart.image_base64(img_base64, mimetype))

        # LLMMessage.user accepts list of content parts for multimodal
        messages.append(LLMMessage.user(content_parts))
        logger.info(f"[LLM] Processing message with {len(image_data)} image(s)")
    else:
        messages.append(LLMMessage.user(user_input))

    # Get tool definitions
    tools = get_tool_definitions()

    # Call LLM with proper parameters (follows sales-module pattern)
    client = LLMClient.from_config()
    response = await client.complete(
        messages=messages,
        tools=tools,
        tool_choice="auto",
        # Caching parameters for prompt optimization
        cache_key="design_request",
        cache_retention="24h",
        # Cost tracking parameters
        call_type="main_llm",
        workflow="design_request",
        user_id=workflow_ctx.get_tracking_name(),
        # Context for audit trail
        context=f"Channel: video-critique, State: {type(state).__name__}",
        metadata={
            "has_images": has_images,
            "message_length": len(user_input),
            "history_length": len(state.history),
        },
    )

    # Handle tool calls
    if response.tool_calls:
        tool_call = response.tool_calls[0]

        if tool_router:
            # Delegate to tool router with workflow context
            result = await tool_router.route_tool_call(
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                state=state,
                workflow_ctx=workflow_ctx,
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
    workflow_ctx: WorkflowContext,
) -> str:
    """Handle user response during design request confirmation."""
    pending_data = state.pending_confirmation

    # Check for duplicate confirmation mode
    if pending_data.get("_duplicate_confirm"):
        return await _handle_duplicate_confirmation(
            user_id, user_input, state, pending_data, tool_router, workflow_ctx
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
        json_schema=CONFIRMATION_RESPONSE_SCHEMA,
        # LLM parameters (follows sales-module pattern)
        cache_key="confirmation",
        cache_retention="24h",
        call_type="confirmation",
        workflow="confirmation",
        user_id=workflow_ctx.get_tracking_name(),
        context=f"Channel: video-critique, Flow: confirmation",
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
                data=pending_data,
                state=state,
                workflow_ctx=workflow_ctx,
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
    workflow_ctx: WorkflowContext,
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
        json_schema=DUPLICATE_CONFIRMATION_SCHEMA,
        # LLM parameters (follows sales-module pattern)
        cache_key="duplicate_confirm",
        cache_retention="24h",
        call_type="duplicate_confirm",
        workflow="duplicate_confirm",
        user_id=workflow_ctx.get_tracking_name(),
        context=f"Channel: video-critique, Flow: duplicate_confirm",
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
                data=pending_data,
                state=state,
                allow_duplicate=True,
                workflow_ctx=workflow_ctx,
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
    workflow_ctx: WorkflowContext,
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
        json_schema=DELETE_CONFIRMATION_SCHEMA,
        # LLM parameters (follows sales-module pattern)
        cache_key="delete_confirm",
        cache_retention="24h",
        call_type="delete_confirm",
        workflow="delete_confirm",
        user_id=workflow_ctx.get_tracking_name(),
        context=f"Channel: video-critique, Flow: delete_confirm, Task: {task_number}",
    )

    try:
        decision = json.loads(response.content)
    except json.JSONDecodeError:
        return "Please say 'yes' to delete or 'no' to cancel."

    action = decision.get("action")

    if action == "confirm":
        if tool_router:
            result = await tool_router.delete_task(
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
    workflow_ctx: WorkflowContext,
) -> str:
    """Handle task edit flow."""
    edit_data = state.pending_edit
    task_number = edit_data["task_number"]
    current_data = edit_data["current_data"]

    # Check for duplicate confirmation in edit mode
    if edit_data.get("_duplicate_confirm"):
        return await _handle_edit_duplicate_confirmation(
            user_id, user_input, state, edit_data, tool_router, workflow_ctx
        )

    # Parse edit intent
    client = LLMClient.from_config()

    # Call ConfigService directly (follows sales-module pattern)
    from core.services import get_config_service
    config_service = get_config_service()
    system_prompt = create_edit_system_prompt(
        task_number,
        current_data,
        user_input,
        videographers=config_service.get_videographer_names(),
        sales_people=config_service.get_sales_people_names(),
        locations=config_service.get_location_names(),
    )

    response = await client.complete(
        messages=[
            LLMMessage.system(system_prompt),
        ],
        json_schema=EDIT_TASK_SCHEMA,
        # LLM parameters (follows sales-module pattern)
        cache_key="edit_task",
        cache_retention="24h",
        call_type="edit_task",
        workflow="edit_task",
        user_id=workflow_ctx.get_tracking_name(),
        context=f"Channel: video-critique, Flow: edit_task, Task: {task_number}",
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
    workflow_ctx: WorkflowContext,
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
        json_schema=EDIT_DUPLICATE_CONFIRMATION_SCHEMA,
        # LLM parameters (follows sales-module pattern)
        cache_key="edit_duplicate_confirm",
        cache_retention="24h",
        call_type="edit_duplicate_confirm",
        workflow="edit_duplicate_confirm",
        user_id=workflow_ctx.get_tracking_name(),
        context=f"Channel: video-critique, Flow: edit_duplicate_confirm, Task: {task_number}",
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
