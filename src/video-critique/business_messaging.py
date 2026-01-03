"""
Business Messaging Functions
=============================
Platform-agnostic business logic for all messaging operations.
Each function represents a specific business action (e.g., "send HoS approval request").

When switching platforms (Slack → Teams), only the low-level messaging.py needs to change.
This file stays the same because it deals with WHAT to send, not HOW to send it.
"""

from typing import Dict, Any, Optional, List
import json
import messaging
from utils import markdown_to_slack
from clients import logger


# ============================================================================
# REVIEWER WORKFLOW MESSAGES
# ============================================================================

async def send_folder_to_reviewer(
    reviewer_channel: str,
    task_number: int,
    folder_name: str,
    folder_url: str,
    videographer_name: str,
    task_data: Dict[str, Any],
    uploaded_files: List[str],
    workflow_id: str
) -> Dict[str, Any]:
    """
    Send a folder approval request to the reviewer.

    Returns: {'ok': bool, 'message_id': str}
    """
    # Build message blocks
    files_list = "\n".join([f"• {f}" for f in uploaded_files[:10]])
    if len(uploaded_files) > 10:
        files_list += f"\n• ... and {len(uploaded_files) - 10} more files"

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🎥 *New Folder Submission for Review*\n\n"
                       f"*Task #{task_number}* - {task_data.get('Brand', 'Unknown Brand')}\n"
                       f"*Reference:* {task_data.get('Reference Number', 'N/A')}\n"
                       f"*Videographer:* {videographer_name}\n"
                       f"*Folder:* `{folder_name}`\n"
                       f"*Files:* {len(uploaded_files)} file(s)\n\n"
                       f"{files_list}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📁 <{folder_url}|Open Folder in Dropbox>"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve Folder"},
                    "style": "primary",
                    "value": workflow_id,
                    "action_id": "approve_folder_reviewer"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Reject Folder"},
                    "style": "danger",
                    "value": workflow_id,
                    "action_id": "reject_folder_reviewer"
                }
            ]
        }
    ]

    return await messaging.send_message(
        channel=reviewer_channel,
        text=f"🎥 New folder: Task #{task_number} - {task_data.get('Brand', 'N/A')} ({task_data.get('Reference Number', 'N/A')}) - {folder_name}",
        blocks=blocks
    )


async def send_video_to_reviewer(
    reviewer_channel: str,
    task_number: int,
    filename: str,
    video_url: str,
    videographer_name: str,
    task_data: Dict[str, Any],
    workflow_id: str
) -> Dict[str, Any]:
    """
    Send a video approval request to the reviewer.

    Returns: {'ok': bool, 'message_id': str}
    """
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🎥 *New Video for Review*\n\n"
                       f"*Task #{task_number}* - {task_data.get('Brand', 'Unknown Brand')}\n"
                       f"*Reference:* {task_data.get('Reference Number', 'N/A')}\n"
                       f"*Videographer:* {videographer_name}\n"
                       f"*Filename:* `{filename}`"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📹 <{video_url}|Watch Video>"
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
                    "action_id": "approve_video_reviewer"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Reject"},
                    "style": "danger",
                    "value": workflow_id,
                    "action_id": "reject_video_reviewer"
                }
            ]
        }
    ]

    return await messaging.send_message(
        channel=reviewer_channel,
        text=f"🎥 New video: Task #{task_number} - {task_data.get('Brand', 'N/A')} ({task_data.get('Reference Number', 'N/A')}) - {filename}",
        blocks=blocks
    )


async def notify_reviewer_of_sales_approval(
    reviewer_channel: str,
    task_number: int,
    filename: str
) -> Dict[str, Any]:
    """
    Notify reviewer that sales approved a video.

    Returns: {'ok': bool, 'message_id': str}
    """
    text = f"✅ Video approved by sales, pending Head of Sales approval\n\nTask #{task_number}: `{filename}`"
    return await messaging.send_message(channel=reviewer_channel, text=text)


async def notify_reviewer_of_final_acceptance(
    reviewer_channel: str,
    task_number: int,
    filename: str,
    video_url: str
) -> Dict[str, Any]:
    """
    Notify reviewer that HoS accepted a video.

    Returns: {'ok': bool, 'message_id': str}
    """
    text = (f"✅ Video fully accepted by Head of Sales\n\n"
           f"Task #{task_number}: `{filename}`\n"
           f"The video has been moved to the Accepted folder.\n\n"
           f"📹 <{video_url}|Click to View Final Video>")
    return await messaging.send_message(channel=reviewer_channel, text=text)


# ============================================================================
# HEAD OF SALES WORKFLOW MESSAGES
# ============================================================================

async def send_video_to_hos(
    hos_channel: str,
    task_number: int,
    filename: str,
    video_url: str,
    task_data: Dict[str, Any],
    workflow_id: str
) -> Dict[str, Any]:
    """
    Send a video approval request to Head of Sales.

    Returns: {'ok': bool, 'message_id': str}
    """
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🎥 *Video Ready for Final Approval*\n\n"
                       f"*Task #{task_number}* - {task_data.get('Brand', 'Unknown Brand')}\n"
                       f"*Reference:* {task_data.get('Reference Number', 'N/A')}\n"
                       f"*Location:* {task_data.get('Location', 'N/A')}\n"
                       f"*Filename:* `{filename}`\n\n"
                       f"_This video has been approved by the reviewer and is ready for your final approval._"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📹 <{video_url}|Watch Video>"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Accept"},
                    "style": "primary",
                    "value": workflow_id,
                    "action_id": "approve_video_hos"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔄 Return for Revision"},
                    "style": "danger",
                    "value": workflow_id,
                    "action_id": "return_video_hos"
                }
            ]
        }
    ]

    return await messaging.send_message(
        channel=hos_channel,
        text=f"🎥 Video for Task #{task_number} - {task_data.get('Brand', 'N/A')} ({task_data.get('Reference Number', 'N/A')}) - {filename}",
        blocks=blocks
    )


async def send_reviewer_upload_to_hos(
    hos_channel: str,
    task_number: int,
    folder_name: str,
    folder_url: str,
    videographer_name: str,
    reviewer_name: str,
    task_data: Dict[str, Any],
    uploaded_files: List[str],
    workflow_id: str
) -> Dict[str, Any]:
    """
    Send a folder approval request to Head of Sales for Reviewer-uploaded videos.
    Clearly indicates the upload was done by Reviewer on behalf of the videographer.

    Returns: {'ok': bool, 'message_id': str}
    """
    # Build files list
    files_list = "\n".join([f"• {f}" for f in uploaded_files[:10]])
    if len(uploaded_files) > 10:
        files_list += f"\n• ... and {len(uploaded_files) - 10} more files"

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🎥 *Folder Ready for Final Approval*\n\n"
                       f"*Task #{task_number}* - {task_data.get('Brand', 'Unknown Brand')}\n"
                       f"*Reference:* {task_data.get('Reference Number', 'N/A')}\n"
                       f"*Location:* {task_data.get('Location', 'N/A')}\n"
                       f"*Folder:* `{folder_name}`\n"
                       f"*Files:* {len(uploaded_files)} file(s)\n\n"
                       f"⚡ *Uploaded by {reviewer_name} on behalf of {videographer_name}*\n\n"
                       f"{files_list}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📁 <{folder_url}|Open Folder in Dropbox>"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Accept"},
                    "style": "primary",
                    "value": workflow_id,
                    "action_id": "approve_video_hos"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔄 Return for Revision"},
                    "style": "danger",
                    "value": workflow_id,
                    "action_id": "return_video_hos"
                }
            ]
        }
    ]

    return await messaging.send_message(
        channel=hos_channel,
        text=f"🎥 Reviewer Upload: Task #{task_number} - {task_data.get('Brand', 'N/A')} ({task_data.get('Reference Number', 'N/A')}) - {folder_name}",
        blocks=blocks
    )


# ============================================================================
# SALES WORKFLOW MESSAGES
# ============================================================================

async def send_video_to_sales(
    sales_channel: str,
    task_number: int,
    filename: str,
    video_url: str,
    task_data: Dict[str, Any],
    workflow_id: str
) -> Dict[str, Any]:
    """
    Send a video approval request to sales person.

    Returns: {'ok': bool, 'message_id': str}
    """
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🎥 *Video Ready for Sales Approval*\n\n"
                       f"*Task #{task_number}* - {task_data.get('Brand', 'Unknown Brand')}\n"
                       f"*Reference:* {task_data.get('Reference Number', 'N/A')}\n"
                       f"*Location:* {task_data.get('Location', 'N/A')}\n"
                       f"*Filename:* `{filename}`"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📹 <{video_url}|Watch Video>"
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
                    "action_id": "approve_video_sales"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Reject"},
                    "style": "danger",
                    "value": workflow_id,
                    "action_id": "reject_video_sales"
                }
            ]
        }
    ]

    return await messaging.send_message(
        channel=sales_channel,
        text=f"Video submitted for approval: {filename}",
        blocks=blocks
    )


async def notify_sales_of_final_video(
    sales_channel: str,
    task_number: int,
    filename: str,
    video_url: str,
    task_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Notify sales person that video is ready to use.

    Returns: {'ok': bool, 'message_id': str}
    """
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🎉 *Video Ready for Use*\n\n"
                       f"Task #{task_number}\n"
                       f"Filename: `{filename}`\n"
                       f"Brand: {task_data.get('Brand', '')}\n"
                       f"Location: {task_data.get('Location', '')}\n"
                       f"Campaign: {task_data.get('Campaign Start Date', '')} to {task_data.get('Campaign End Date', '')}\n\n"
                       f"_This video has been approved by both the Reviewer and Head of Sales and is ready for your campaign._"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📹 <{video_url}|Download Final Video>"
            }
        }
    ]

    return await messaging.send_message(
        channel=sales_channel,
        text="🎉 Video ready for use - Approved by Head of Sales",
        blocks=blocks
    )


# ============================================================================
# VIDEOGRAPHER NOTIFICATIONS
# ============================================================================

async def notify_videographer_approval(
    videographer_id: str,
    task_number: int,
    filename: str,
    video_url: str,
    stage: str = "reviewer"
) -> Dict[str, Any]:
    """
    Notify videographer that their video was approved.

    Args:
        stage: "reviewer" or "hos" (head of sales)

    Returns: {'ok': bool, 'message_id': str}
    """
    if stage == "reviewer":
        text = (f"✅ Good news! Your video for Task #{task_number} has been approved by the reviewer "
               f"and sent to Head of Sales for final approval.\n\n"
               f"Filename: `{filename}`\n\n"
               f"📹 <{video_url}|Click to View Video>")
    elif stage == "sales":
        text = (f"✅ Good news! Your video for Task #{task_number} has been approved by sales "
               f"and is now pending Head of Sales approval.\n\n"
               f"Filename: `{filename}`")
    else:  # hos
        text = (f"🎉 Excellent news! Your video for Task #{task_number} has been fully accepted by Head of Sales!\n\n"
               f"Filename: `{filename}`\n"
               f"Status: Done\n\n"
               f"📹 <{video_url}|Click to View Final Video>")

    return await messaging.send_message(channel=videographer_id, text=text)


async def notify_videographer_rejection(
    videographer_id: str,
    task_number: int,
    filename: str,
    rejection_class: str,
    rejection_comments: str,
    stage: str = "reviewer"
) -> Dict[str, Any]:
    """
    Notify videographer that their video was rejected.

    Args:
        stage: "reviewer", "sales", or "hos"

    Returns: {'ok': bool, 'message_id': str}
    """
    stage_name = {"reviewer": "Reviewer", "sales": "Sales", "hos": "Head of Sales"}.get(stage, stage)

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"❌ *Video Rejected by {stage_name}*\n\n"
                       f"Task #{task_number}: `{filename}`\n"
                       f"*Category:* {rejection_class}\n"
                       f"*Comments:* {rejection_comments or 'No comments provided'}\n\n"
                       f"Please review the feedback and resubmit."
            }
        }
    ]

    return await messaging.send_message(
        channel=videographer_id,
        text=f"❌ Video rejected by {stage_name}",
        blocks=blocks
    )


async def notify_videographer_returned(
    videographer_id: str,
    task_number: int,
    filename: str,
    return_comments: str
) -> Dict[str, Any]:
    """
    Notify videographer that their video was returned for revision.

    Returns: {'ok': bool, 'message_id': str}
    """
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔄 *Video Returned for Revision*\n\n"
                       f"Task #{task_number}: `{filename}`\n"
                       f"*Comments:* {return_comments or 'No comments provided'}\n\n"
                       f"Please make the requested revisions and resubmit."
            }
        }
    ]

    return await messaging.send_message(
        channel=videographer_id,
        text="🔄 Video returned for revision",
        blocks=blocks
    )


# ============================================================================
# UPLOAD VALIDATION MESSAGES
# ============================================================================

async def send_upload_error(
    channel: str,
    error_message: str
) -> Dict[str, Any]:
    """
    Send an upload validation error to the user.

    Returns: {'ok': bool, 'message_id': str}
    """
    return await messaging.send_message(channel=channel, text=error_message)


async def send_upload_success(
    channel: str,
    task_number: int,
    folder_name: str,
    file_count: int
) -> Dict[str, Any]:
    """
    Confirm successful upload to the user.

    Returns: {'ok': bool, 'message_id': str}
    """
    text = (f"✅ Successfully extracted and uploaded {file_count} file{'s' if file_count > 1 else ''} "
           f"from zip to folder `{folder_name}`!\n"
           f"📁 Location: Pending folder\n"
           f"🔍 Sent to reviewer for approval")

    return await messaging.send_message(channel=channel, text=text)


async def send_processing_message(
    channel: str,
    task_number: int
) -> Dict[str, Any]:
    """
    Send a "processing..." message.

    Returns: {'ok': bool, 'message_id': str}
    """
    text = f"📥 Processing zip file for Task #{task_number}..."
    return await messaging.send_message(channel=channel, text=text)


# ============================================================================
# REJECTION MODAL
# ============================================================================

async def open_rejection_modal(
    trigger_id: str,
    workflow_id: str,
    task_number: int,
    stage: str,
    response_url: str
) -> Dict[str, Any]:
    """
    Open a modal to collect rejection feedback.

    Args:
        stage: "reviewer", "sales", or "hos"

    Returns: {'ok': bool, 'view_id': str}
    """
    view = {
        "type": "modal",
        "callback_id": f"reject_video_modal_{workflow_id}",
        "title": {"type": "plain_text", "text": "Reject Video"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Please provide a reason for rejecting the video for Task #{task_number}"
                }
            },
            {
                "type": "input",
                "block_id": "rejection_reason",
                "label": {"type": "plain_text", "text": "Rejection Reason"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "reason_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Enter the reason for rejection..."}
                }
            }
        ],
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": json.dumps({
            "workflow_id": workflow_id,
            "response_url": response_url,
            "stage": stage
        })
    }

    return await messaging.open_modal(trigger_id=trigger_id, view=view)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def update_approval_message(
    channel: str,
    message_id: str,
    status: str,
    task_number: int,
    filename: str,
    comments: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update an approval request message with the outcome.

    Args:
        status: "approved", "rejected", "returned"

    Returns: {'ok': bool, 'message_id': str}
    """
    emoji = {"approved": "✅", "rejected": "❌", "returned": "🔄"}.get(status, "📝")
    status_text = status.title()

    text = f"{emoji} *Video {status_text}*\n\nTask #{task_number}: `{filename}`"
    if comments:
        text += f"\n*Comments:* {comments}"

    return await messaging.update_message(
        channel=channel,
        message_id=message_id,
        text=text
    )


async def send_video_ready_notification(
    sales_channel: str,
    task_number: int,
    filename: str,
    video_url: str,
    task_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Notify sales person that video is ready for use after HoS approval.

    Returns: {'ok': bool, 'message_id': str, 'channel': str}
    """
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🎉 *Video Ready for Use*\n\n"
                       f"*Task #{task_number}*\n"
                       f"*Filename:* `{filename}`\n"
                       f"*Brand:* {task_data.get('Brand', 'N/A')}\n"
                       f"*Location:* {task_data.get('Location', 'N/A')}\n"
                       f"*Campaign:* {task_data.get('Campaign Start Date', 'N/A')} to {task_data.get('Campaign End Date', 'N/A')}\n\n"
                       f"_This video has been approved by both the Reviewer and Head of Sales and is ready for your campaign._"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📹 <{video_url}|*Download Final Video*>"
            }
        }
    ]

    return await messaging.send_message(
        channel=sales_channel,
        text=f"🎉 Video ready for use - Task #{task_number}",
        blocks=blocks
    )
