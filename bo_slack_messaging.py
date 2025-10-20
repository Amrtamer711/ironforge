"""
Slack messaging functions for booking order approval workflow
"""

import logging
from typing import Dict, Any, Optional

import config

logger = logging.getLogger("proposal-bot")


async def post_to_thread(channel: str, thread_ts: str, text: str) -> Dict[str, Any]:
    """
    Post a simple message to a thread.

    Returns: {"ts": message_timestamp}
    """
    result = await config.slack_client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=config.markdown_to_slack(text)
    )
    return {"ts": result.get("ts")}


async def send_coordinator_approval_buttons(
    channel: str,
    workflow_id: str,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Send Approve/Reject buttons to Sales Coordinator for initial review

    Returns: {"ts": message_timestamp}
    """

    # Build message text
    text = "📎 **Please review the Excel file above, then:**"

    # Create blocks with buttons
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": text
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve"},
                    "style": "primary",
                    "value": workflow_id,
                    "action_id": "approve_bo_coordinator"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Reject"},
                    "style": "danger",
                    "value": workflow_id,
                    "action_id": "reject_bo_coordinator"
                }
            ]
        }
    ]

    # Post buttons as separate message
    button_result = await config.slack_client.chat_postMessage(
        channel=channel,
        text="Please review and approve or reject:",
        blocks=blocks
    )

    return {"ts": button_result.get("ts")}


async def send_to_head_of_sales(
    channel: str,
    workflow_id: str,
    company: str,
    data: Dict[str, Any],
    warnings: list,
    missing_required: list,
    excel_path: str
) -> Dict[str, Any]:
    """
    Send booking order to Head of Sales with Approve/Reject buttons

    Returns: {"message_id": ts, "channel": channel}
    """

    # Build message text
    text = f"📋 **New Booking Order for Approval**\n\n"
    text += f"**Company:** {company.upper()}\n"
    text += f"**Client:** {data.get('client', 'N/A')}\n"
    text += f"**Campaign:** {data.get('brand_campaign', 'N/A')}\n"
    text += f"**BO Number:** {data.get('bo_number', 'N/A')}\n"
    text += f"**Net (pre-VAT):** AED {data.get('net_pre_vat', 0):,.2f}\n"
    text += f"**VAT (5%):** AED {data.get('vat_calc', 0):,.2f}\n"
    text += f"**Gross Total:** AED {data.get('gross_calc', 0):,.2f}\n\n"

    # Locations
    locations = data.get('locations', [])
    if locations:
        text += f"**Locations ({len(locations)}):**\n"
        for i, loc in enumerate(locations[:3], 1):
            text += f"{i}. {loc.get('name', 'Unknown')}: {loc.get('start_date', '?')} to {loc.get('end_date', '?')}\n"
        if len(locations) > 3:
            text += f"...and {len(locations) - 3} more\n"

    if warnings:
        text += f"\n⚠️ **Warnings:** {len(warnings)}\n"

    if missing_required:
        text += f"\n❗ **Missing Required Fields:** {', '.join(missing_required)}\n"

    # Create blocks with buttons
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": text
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve"},
                    "style": "primary",
                    "value": workflow_id,
                    "action_id": "approve_bo_hos"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Reject"},
                    "style": "danger",
                    "value": workflow_id,
                    "action_id": "reject_bo_hos"
                }
            ]
        }
    ]

    # Upload Excel file
    file_result = await config.slack_client.files_upload_v2(
        channel=channel,
        file=excel_path,
        title=f"BO Draft - {data.get('client', 'Unknown')} - {company.upper()}",
        initial_comment=config.markdown_to_slack(text)
    )

    # Post buttons as separate message (blocks with file upload don't show buttons reliably)
    button_result = await config.slack_client.chat_postMessage(
        channel=channel,
        text="Please review and approve or reject:",
        blocks=blocks
    )

    return {
        "message_id": button_result.get("ts"),
        "channel": channel,
        "file_id": file_result.get("file", {}).get("id")
    }


async def send_to_coordinator(
    channel: str,
    workflow_id: str,
    company: str,
    data: Dict[str, Any],
    excel_path: str
) -> Dict[str, Any]:
    """
    Send booking order to Sales Coordinator with Approve/Reject buttons

    Returns: {"message_id": ts, "channel": channel}
    """

    # Build message text
    text = f"✅ **Booking Order Approved by Head of Sales**\n\n"
    text += f"**Company:** {company.upper()}\n"
    text += f"**Client:** {data.get('client', 'N/A')}\n"
    text += f"**Campaign:** {data.get('brand_campaign', 'N/A')}\n"
    text += f"**Gross Total:** AED {data.get('gross_calc', 0):,.2f}\n\n"
    text += f"Please review the booking order details and confirm."

    # Create blocks with buttons
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": text
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve"},
                    "style": "primary",
                    "value": workflow_id,
                    "action_id": "approve_bo_coordinator"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Reject"},
                    "style": "danger",
                    "value": workflow_id,
                    "action_id": "reject_bo_coordinator"
                }
            ]
        }
    ]

    # Upload Excel file
    file_result = await config.slack_client.files_upload_v2(
        channel=channel,
        file=excel_path,
        title=f"BO Draft - {data.get('client', 'Unknown')} - {company.upper()}",
        initial_comment=config.markdown_to_slack(text)
    )

    # Post buttons as separate message
    button_result = await config.slack_client.chat_postMessage(
        channel=channel,
        text="Please review and approve or reject:",
        blocks=blocks
    )

    return {
        "message_id": button_result.get("ts"),
        "channel": channel,
        "file_id": file_result.get("file", {}).get("id")
    }


async def notify_finance(
    channel: str,
    bo_ref: str,
    company: str,
    data: Dict[str, Any],
    excel_path: str
) -> Dict[str, Any]:
    """
    Notify Finance department (no buttons, just notification)

    Returns: {"message_id": ts, "channel": channel}
    """

    # Build message text
    text = f"✅ **Booking Order Approved & Finalized**\n\n"
    text += f"**BO Reference:** {bo_ref}\n"
    text += f"**Company:** {company.upper()}\n"
    text += f"**Client:** {data.get('client', 'N/A')}\n"
    text += f"**Campaign:** {data.get('brand_campaign', 'N/A')}\n"
    text += f"**Gross Total:** AED {data.get('gross_calc', 0):,.2f}\n\n"
    text += f"This booking order has been approved by all stakeholders and is now finalized."

    # Upload Excel file
    result = await config.slack_client.files_upload_v2(
        channel=channel,
        file=excel_path,
        title=f"{bo_ref} - Finalized Booking Order",
        initial_comment=config.markdown_to_slack(text)
    )

    return {
        "message_id": result.get("file", {}).get("shares", {}).get("public", {}).get(channel, [{}])[0].get("ts"),
        "channel": channel,
        "file_id": result.get("file", {}).get("id")
    }


async def update_button_message(
    channel: str,
    message_ts: str,
    new_text: str,
    approved: bool = True
):
    """
    Update message after button click (remove buttons, show status)
    """
    emoji = "✅" if approved else "❌"
    status = "APPROVED" if approved else "REJECTED"

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} **{status}**\n\n{new_text}"
            }
        }
    ]

    try:
        await config.slack_client.chat_update(
            channel=channel,
            ts=message_ts,
            text=new_text,
            blocks=blocks
        )
    except Exception as e:
        logger.error(f"[BO SLACK] Failed to update button message: {e}")


async def send_rejection_to_thread(
    channel: str,
    thread_ts: str,
    rejection_reason: str,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Send rejection message to thread with current BO details

    Returns: {"message_id": ts}
    """

    text = f"❌ **Booking Order Rejected**\n\n"
    text += f"**Reason:** {rejection_reason}\n\n"
    text += f"**Current Details:**\n"
    text += f"• Client: {data.get('client', 'N/A')}\n"
    text += f"• Campaign: {data.get('brand_campaign', 'N/A')}\n"
    text += f"• Gross Total: AED {data.get('gross_calc', 0):,.2f}\n\n"
    text += f"Please tell me what changes are needed, and I'll update the booking order."

    result = await config.slack_client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=config.markdown_to_slack(text)
    )

    return {"message_id": result.get("ts")}


async def post_response_url(response_url: str, payload: Dict[str, Any]):
    """Post response to Slack response_url"""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(response_url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"[BO SLACK] Response URL failed: {response.status}")
    except Exception as e:
        logger.error(f"[BO SLACK] Failed to post to response_url: {e}")
