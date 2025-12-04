"""
Messaging functions for booking order approval workflow.

Uses the unified channel abstraction layer for all messaging operations.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

import config
from integrations.channels import Button, ButtonStyle

logger = logging.getLogger("proposal-bot")


def _format_amount(data: Optional[Dict[str, Any]], amount: Optional[float]) -> str:
    currency = (data or {}).get("currency", config.DEFAULT_CURRENCY)
    return config.format_currency_value(amount, currency)


async def get_user_real_name(user_id: str) -> str:
    """
    Get user's real name from the channel.
    Returns the real name or falls back to user_id if lookup fails.
    """
    channel = config.get_channel_adapter()
    if not channel:
        return user_id

    try:
        display_name = await channel.get_user_display_name(user_id)
        return display_name
    except Exception as e:
        logger.warning(f"[CHANNEL] Failed to get user info for {user_id}: {e}")
        return user_id


async def post_to_thread(channel_id: str, thread_ts: str, text: str) -> Dict[str, Any]:
    """
    Post a simple message to a thread.

    Returns: {"ts": message_timestamp}
    """
    channel = config.get_channel_adapter()
    if not channel:
        raise RuntimeError("No channel adapter available")

    message = await channel.send_message(
        channel_id=channel_id,
        content=text,
        thread_id=thread_ts
    )
    return {"ts": message.platform_message_id or message.id}


async def send_coordinator_approval_buttons(
    channel_id: str,
    workflow_id: str,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Send Approve/Reject buttons to Sales Coordinator for initial review.

    Returns: {"ts": message_timestamp}
    """
    channel = config.get_channel_adapter()
    if not channel:
        raise RuntimeError("No channel adapter available")

    text = "**Please review the Excel file above, then:**"

    buttons = [
        Button(
            action_id="approve_bo_coordinator",
            text="Approve",
            value=workflow_id,
            style=ButtonStyle.PRIMARY
        ),
        Button(
            action_id="reject_bo_coordinator",
            text="Reject",
            value=workflow_id,
            style=ButtonStyle.DANGER
        ),
        Button(
            action_id="cancel_bo_coordinator",
            text="Cancel",
            value=workflow_id,
            style=ButtonStyle.SECONDARY
        )
    ]

    message = await channel.send_message(
        channel_id=channel_id,
        content=text,
        buttons=buttons
    )

    return {"ts": message.platform_message_id or message.id}


async def send_to_head_of_sales(
    channel_id: str,
    workflow_id: str,
    company: str,
    data: Dict[str, Any],
    warnings: list,
    missing_required: list,
    combined_pdf_path: str
) -> Dict[str, Any]:
    """
    Send booking order to Head of Sales with Approve/Reject buttons.

    Returns: {"message_id": ts, "channel": channel}
    """
    channel = config.get_channel_adapter()
    if not channel:
        raise RuntimeError("No channel adapter available")

    # Build message text
    text = f"**New Booking Order for Approval**\n\n"
    text += f"**Company:** {company.upper()}\n"
    text += f"**Client:** {data.get('client', 'N/A')}\n"
    text += f"**Campaign:** {data.get('brand_campaign', 'N/A')}\n"
    text += f"**BO Number:** {data.get('bo_number', 'N/A')}\n"
    text += f"**Net (pre-VAT):** {_format_amount(data, data.get('net_pre_vat'))}\n"
    text += f"**VAT (5%):** {_format_amount(data, data.get('vat_calc'))}\n"
    text += f"**Gross Total:** {_format_amount(data, data.get('gross_calc'))}\n\n"

    # Locations
    locations = data.get('locations', [])
    if locations:
        text += f"**Locations ({len(locations)}):**\n"
        for i, loc in enumerate(locations[:3], 1):
            text += f"{i}. {loc.get('name', 'Unknown')}: {loc.get('start_date', '?')} to {loc.get('end_date', '?')}\n"
        if len(locations) > 3:
            text += f"...and {len(locations) - 3} more\n"

    if warnings:
        text += f"\n**Warnings:** {len(warnings)}\n"

    if missing_required:
        text += f"\n**Missing Required Fields:** {', '.join(missing_required)}\n"

    text += f"\nPlease review the combined PDF (parsed data + original BO) and approve, reject, or cancel."

    # Upload combined PDF file
    file_result = await channel.upload_file(
        channel_id=channel_id,
        file_path=combined_pdf_path,
        title=f"BO Draft - {data.get('client', 'Unknown')} - {company.upper()}",
        comment=text
    )

    # Wait for file to render before posting buttons
    await asyncio.sleep(10)

    # Post buttons as separate message
    buttons = [
        Button(
            action_id="approve_bo_hos",
            text="Approve",
            value=workflow_id,
            style=ButtonStyle.PRIMARY
        ),
        Button(
            action_id="reject_bo_hos",
            text="Reject",
            value=workflow_id,
            style=ButtonStyle.DANGER
        ),
        Button(
            action_id="cancel_bo_hos",
            text="Cancel",
            value=workflow_id,
            style=ButtonStyle.SECONDARY
        )
    ]

    button_message = await channel.send_message(
        channel_id=channel_id,
        content="Please review and approve, reject, or cancel:",
        buttons=buttons
    )

    return {
        "message_id": button_message.platform_message_id or button_message.id,
        "channel": channel_id,
        "file_id": file_result.file_id
    }


async def send_to_coordinator(
    channel_id: str,
    workflow_id: str,
    company: str,
    data: Dict[str, Any],
    combined_pdf_path: str,
    warnings: Optional[list] = None,
    missing_required: Optional[list] = None,
    is_revision: bool = False,
    original_bo_ref: Optional[str] = None,
    user_notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send booking order to Sales Coordinator with Approve/Reject buttons.

    Returns: {"message_id": ts, "channel": channel}
    """
    channel = config.get_channel_adapter()
    if not channel:
        raise RuntimeError("No channel adapter available")

    # Build message text
    if is_revision and original_bo_ref:
        text = f"**Booking Order Revision Request**\n\n"
        text += f"**Original BO:** {original_bo_ref}\n"
    else:
        text = f"**New Booking Order for Review**\n\n"

    text += f"**Company:** {company.upper()}\n"
    text += f"**Client:** {data.get('client', 'N/A')}\n"
    text += f"**Campaign:** {data.get('brand_campaign', 'N/A')}\n"
    text += f"**BO Number:** {data.get('bo_number', 'N/A')}\n"
    text += f"**Net (pre-VAT):** {_format_amount(data, data.get('net_pre_vat'))}\n"
    text += f"**VAT (5%):** {_format_amount(data, data.get('vat_calc'))}\n"
    text += f"**Gross Total:** {_format_amount(data, data.get('gross_calc'))}\n\n"

    # Show locations summary
    locations = data.get('locations', [])
    if locations:
        text += f"**Locations ({len(locations)}):**\n"
        for i, loc in enumerate(locations[:3], 1):
            text += f"{i}. {loc.get('name', 'Unknown')}: {loc.get('start_date', '?')} to {loc.get('end_date', '?')}\n"
        if len(locations) > 3:
            text += f"...and {len(locations) - 3} more\n"
        text += "\n"

    # Show sales person's notes if provided
    if user_notes and user_notes.strip():
        text += f"**Sales Person Notes:**\n{user_notes}\n\n"

    if warnings:
        text += f"**Warnings:** {len(warnings)}\n"

    if missing_required:
        text += f"**Missing Required Fields:** {', '.join(missing_required)}\n"

    text += f"\nPlease review the combined PDF (parsed data + original BO) and approve, reject, or cancel."

    # Upload combined PDF file
    file_result = await channel.upload_file(
        channel_id=channel_id,
        file_path=combined_pdf_path,
        title=f"BO Draft - {data.get('client', 'Unknown')} - {company.upper()}",
        comment=text
    )

    # Post buttons as separate message
    buttons = [
        Button(
            action_id="approve_bo_coordinator",
            text="Approve",
            value=workflow_id,
            style=ButtonStyle.PRIMARY
        ),
        Button(
            action_id="reject_bo_coordinator",
            text="Reject",
            value=workflow_id,
            style=ButtonStyle.DANGER
        ),
        Button(
            action_id="cancel_bo_coordinator",
            text="Cancel",
            value=workflow_id,
            style=ButtonStyle.SECONDARY
        )
    ]

    button_message = await channel.send_message(
        channel_id=channel_id,
        content="Please review and approve or reject:",
        buttons=buttons
    )

    return {
        "message_id": button_message.platform_message_id or button_message.id,
        "channel": channel_id,
        "file_id": file_result.file_id
    }


async def notify_finance(
    channel_id: str,
    bo_ref: str,
    company: str,
    data: Dict[str, Any],
    excel_path: str
) -> Dict[str, Any]:
    """
    Notify Finance department (no buttons, just notification).

    Returns: {"message_id": ts, "channel": channel}
    """
    from workflows.bo_parser import sanitize_filename

    channel = config.get_channel_adapter()
    if not channel:
        raise RuntimeError("No channel adapter available")

    # Get bo_number for user-facing display
    bo_number = data.get("bo_number", "N/A")
    safe_bo_number = sanitize_filename(bo_number)

    # Build message text
    text = f"**Booking Order Approved & Finalized**\n\n"
    text += f"**BO Number:** {bo_number}\n"
    text += f"**Company:** {company.upper()}\n"
    text += f"**Client:** {data.get('client', 'N/A')}\n"
    text += f"**Campaign:** {data.get('brand_campaign', 'N/A')}\n"
    text += f"**Gross Total:** {_format_amount(data, data.get('gross_calc'))}\n\n"
    text += f"This booking order has been approved by all stakeholders and is now finalized."

    # Upload Excel file
    result = await channel.upload_file(
        channel_id=channel_id,
        file_path=excel_path,
        filename=f"{safe_bo_number}.pdf",
        title=f"{bo_number} - Finalized Booking Order",
        comment=text
    )

    return {
        "message_id": None,  # File upload doesn't return message ts directly
        "channel": channel_id,
        "file_id": result.file_id
    }


async def update_button_message(
    channel_id: str,
    message_ts: str,
    new_text: str,
    approved: bool = True
):
    """
    Update message after button click (remove buttons, show status).
    """
    channel = config.get_channel_adapter()
    if not channel:
        logger.error("[BO CHANNEL] No channel adapter available")
        return

    status = "APPROVED" if approved else "REJECTED"
    content = f"**{status}**\n\n{new_text}"

    try:
        await channel.update_message(
            channel_id=channel_id,
            message_id=message_ts,
            content=content,
            buttons=None  # Remove buttons
        )
    except Exception as e:
        logger.error(f"[BO CHANNEL] Failed to update button message: {e}")


async def send_rejection_to_thread(
    channel_id: str,
    thread_ts: str,
    rejection_reason: str,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Send rejection message to thread with current BO details.

    Returns: {"message_id": ts}
    """
    channel = config.get_channel_adapter()
    if not channel:
        raise RuntimeError("No channel adapter available")

    text = f"**Booking Order Rejected**\n\n"
    text += f"**Reason:** {rejection_reason}\n\n"
    text += f"**Current Details:**\n"
    text += f"- Client: {data.get('client', 'N/A')}\n"
    text += f"- Campaign: {data.get('brand_campaign', 'N/A')}\n"
    text += f"- Gross Total: {_format_amount(data, data.get('gross_calc'))}\n\n"
    text += f"Please tell me what changes are needed, and I'll update the booking order."

    message = await channel.send_message(
        channel_id=channel_id,
        content=text,
        thread_id=thread_ts
    )

    return {"message_id": message.platform_message_id or message.id}


async def post_response_url(response_url: str, payload: Dict[str, Any]):
    """Post response to channel response_url (for deferred responses)."""
    channel = config.get_channel_adapter()
    if not channel:
        logger.error("[BO CHANNEL] No channel adapter available")
        return

    try:
        # Use channel's respond_to_action method
        content = payload.get("text", "")
        replace_original = payload.get("replace_original", True)
        await channel.respond_to_action(
            response_url=response_url,
            content=content,
            replace_original=replace_original
        )
    except Exception as e:
        logger.error(f"[BO CHANNEL] Failed to post to response_url: {e}")
