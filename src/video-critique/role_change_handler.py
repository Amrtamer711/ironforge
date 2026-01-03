"""
Role Change Handler
Manages pending approval reassignments when reviewer or head of sales roles change
"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from logger import logger
from config import UAE_TZ, HISTORY_DB_PATH
import sqlite3
import messaging
import business_messaging


def _connect() -> sqlite3.Connection:
    """Create database connection"""
    conn = sqlite3.connect(HISTORY_DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
    except Exception as e:
        logger.warning(f"PRAGMA setup failed: {e}")
    return conn


async def find_pending_approvals_for_reviewer(old_reviewer_id: str) -> List[Dict[str, Any]]:
    """
    Find all workflows pending approval from the reviewer

    Args:
        old_reviewer_id: Slack user ID of the old reviewer

    Returns:
        List of workflow dictionaries pending reviewer approval
    """
    try:
        with _connect() as conn:
            cursor = conn.execute("""
                SELECT workflow_id, task_number, folder_name, dropbox_path,
                       videographer_id, task_data, version_info, reviewer_id,
                       reviewer_msg_ts, hos_id, hos_msg_ts, reviewer_approved,
                       hos_approved, created_at, updated_at, status
                FROM approval_workflows
                WHERE reviewer_id = ?
                AND reviewer_approved = 0
                AND status = 'pending'
            """, (old_reviewer_id,))

            rows = cursor.fetchall()
            workflows = []

            for row in rows:
                workflow = {
                    'workflow_id': row[0],
                    'task_number': row[1],
                    'folder_name': row[2],
                    'dropbox_path': row[3],
                    'videographer_id': row[4],
                    'task_data': json.loads(row[5]) if row[5] else {},
                    'version_info': json.loads(row[6]) if row[6] else {},
                    'reviewer_id': row[7],
                    'reviewer_msg_ts': row[8],
                    'hos_id': row[9],
                    'hos_msg_ts': row[10],
                    'reviewer_approved': row[11],
                    'hos_approved': row[12],
                    'created_at': row[13],
                    'updated_at': row[14],
                    'status': row[15]
                }
                workflows.append(workflow)

            logger.info(f"Found {len(workflows)} pending workflows for reviewer {old_reviewer_id}")
            return workflows

    except Exception as e:
        logger.error(f"Error finding pending approvals for reviewer: {e}")
        return []


async def find_pending_approvals_for_hos(old_hos_id: str) -> List[Dict[str, Any]]:
    """
    Find all workflows pending approval from head of sales

    Args:
        old_hos_id: Slack user ID of the old head of sales

    Returns:
        List of workflow dictionaries pending HOS approval
    """
    try:
        with _connect() as conn:
            cursor = conn.execute("""
                SELECT workflow_id, task_number, folder_name, dropbox_path,
                       videographer_id, task_data, version_info, reviewer_id,
                       reviewer_msg_ts, hos_id, hos_msg_ts, reviewer_approved,
                       hos_approved, created_at, updated_at, status
                FROM approval_workflows
                WHERE hos_id = ?
                AND hos_approved = 0
                AND reviewer_approved = 1
                AND status = 'pending'
            """, (old_hos_id,))

            rows = cursor.fetchall()
            workflows = []

            for row in rows:
                workflow = {
                    'workflow_id': row[0],
                    'task_number': row[1],
                    'folder_name': row[2],
                    'dropbox_path': row[3],
                    'videographer_id': row[4],
                    'task_data': json.loads(row[5]) if row[5] else {},
                    'version_info': json.loads(row[6]) if row[6] else {},
                    'reviewer_id': row[7],
                    'reviewer_msg_ts': row[8],
                    'hos_id': row[9],
                    'hos_msg_ts': row[10],
                    'reviewer_approved': row[11],
                    'hos_approved': row[12],
                    'created_at': row[13],
                    'updated_at': row[14],
                    'status': row[15]
                }
                workflows.append(workflow)

            logger.info(f"Found {len(workflows)} pending workflows for HOS {old_hos_id}")
            return workflows

    except Exception as e:
        logger.error(f"Error finding pending approvals for HOS: {e}")
        return []


async def disable_old_approval_message(channel_id: str, message_ts: str, role_name: str) -> bool:
    """
    Update the old approval message to indicate the role has changed

    Args:
        channel_id: Slack channel ID where message was sent
        message_ts: Message timestamp
        role_name: Name of the role (for display)

    Returns:
        True if successful, False otherwise
    """
    try:
        if not message_ts or not channel_id:
            logger.warning(f"Missing channel_id or message_ts for disabling message")
            return False

        # Update message with disabled buttons and notification
        result = await messaging.update_message(
            channel=channel_id,
            message_id=message_ts,
            text=f"⚠️ This approval request has been reassigned due to {role_name} role change.",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚠️ *Role Change Detected*\n\nThis approval request has been reassigned to the new {role_name}.\nYour action is no longer required for this task."
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"_Message disabled on {datetime.now(UAE_TZ).strftime('%Y-%m-%d %H:%M:%S')} (UAE)_"
                        }
                    ]
                }
            ]
        )

        if result.get('ok'):
            logger.info(f"Successfully disabled approval message {message_ts} in channel {channel_id}")
            return True
        else:
            logger.error(f"Failed to disable approval message: {result.get('error')}")
            return False

    except Exception as e:
        logger.error(f"Error disabling approval message: {e}")
        return False


async def send_new_reviewer_approval(workflow: Dict[str, Any], new_reviewer_channel: str, new_reviewer_id: str) -> Optional[str]:
    """
    Send a new approval request to the new reviewer

    Args:
        workflow: Workflow data dictionary
        new_reviewer_channel: New reviewer's Slack channel ID
        new_reviewer_id: New reviewer's Slack user ID

    Returns:
        New message timestamp if successful, None otherwise
    """
    try:
        task_data = workflow.get('task_data', {})
        task_number = workflow.get('task_number')
        folder_name = workflow.get('folder_name')
        videographer_name = workflow.get('videographer_id', 'Unknown')
        version_info = workflow.get('version_info', {})
        uploaded_files = version_info.get('files', [])

        # Send using business messaging
        uploaded_file_names = [f.get('dropbox_name', f.get('name', '')) for f in uploaded_files if isinstance(f, dict)]

        result = await business_messaging.send_folder_to_reviewer(
            reviewer_channel=new_reviewer_channel,
            task_number=task_number,
            folder_name=folder_name,
            folder_url=workflow.get('dropbox_path', ''),
            videographer_name=videographer_name,
            task_data=task_data,
            uploaded_files=uploaded_file_names,
            workflow_id=workflow['workflow_id']
        )

        new_msg_ts = result.get('message_id')

        if new_msg_ts:
            logger.info(f"✅ Sent new reviewer approval for workflow {workflow['workflow_id']} to {new_reviewer_id}")
            return new_msg_ts
        else:
            logger.error(f"Failed to send new reviewer approval: {result}")
            return None

    except Exception as e:
        logger.error(f"Error sending new reviewer approval: {e}")
        return None


async def send_new_hos_approval(workflow: Dict[str, Any], new_hos_channel: str, new_hos_id: str) -> Optional[str]:
    """
    Send a new approval request to the new head of sales

    Args:
        workflow: Workflow data dictionary
        new_hos_channel: New HOS's Slack channel ID
        new_hos_id: New HOS's Slack user ID

    Returns:
        New message timestamp if successful, None otherwise
    """
    try:
        task_data = workflow.get('task_data', {})
        task_number = workflow.get('task_number')
        folder_name = workflow.get('folder_name')
        version_info = workflow.get('version_info', {})
        version = version_info.get('version', 1)

        # Import dropbox_manager to get folder link
        from video_upload_system import dropbox_manager

        # Build blocks for HOS approval
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🎥 *Final Approval Required (Reassigned)*\n\n*Task #{task_number} - Version {version}*\n*Folder:* `{folder_name}`\n*Approved by Reviewer* ✅\n\n_This task was reassigned to you due to a role change._"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Brand:* {task_data.get('Brand', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Reference:* {task_data.get('Reference Number', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Location:* {task_data.get('Location', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Sales Person:* {task_data.get('Sales Person', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Campaign Start:* {task_data.get('Campaign Start Date', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Campaign End:* {task_data.get('Campaign End Date', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Videographer:* {task_data.get('Videographer', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Filming Date:* {task_data.get('Filming Date', 'N/A')}"},
                ]
            }
        ]

        # Add folder link
        try:
            folder_link = await dropbox_manager.get_shared_link(workflow.get('dropbox_path', ''))
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📁 <{folder_link}|*Click to View/Download Files*>"
                }
            })
        except Exception as e:
            logger.warning(f"Could not get folder link: {e}")

        # Add action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Accept"},
                    "style": "primary",
                    "action_id": "approve_folder_hos",
                    "value": workflow['workflow_id']
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "↩️ Return for Revision"},
                    "style": "danger",
                    "action_id": "reject_folder_hos",
                    "value": workflow['workflow_id']
                }
            ]
        })

        # Send message
        result = await messaging.send_message(
            channel=new_hos_channel,
            text=f"🎥 Final approval needed for Task #{task_number} (Reassigned)",
            blocks=blocks
        )

        new_msg_ts = result.get('message_id')

        if new_msg_ts:
            logger.info(f"✅ Sent new HOS approval for workflow {workflow['workflow_id']} to {new_hos_id}")
            return new_msg_ts
        else:
            logger.error(f"Failed to send new HOS approval: {result}")
            return None

    except Exception as e:
        logger.error(f"Error sending new HOS approval: {e}")
        return None


async def update_workflow_reviewer(workflow_id: str, new_reviewer_id: str, new_msg_ts: str) -> bool:
    """Update workflow with new reviewer info"""
    try:
        with _connect() as conn:
            conn.execute("""
                UPDATE approval_workflows
                SET reviewer_id = ?,
                    reviewer_msg_ts = ?,
                    updated_at = ?
                WHERE workflow_id = ?
            """, (new_reviewer_id, new_msg_ts, datetime.now(UAE_TZ).isoformat(), workflow_id))
            conn.commit()
            logger.info(f"Updated workflow {workflow_id} with new reviewer {new_reviewer_id}")
            return True
    except Exception as e:
        logger.error(f"Error updating workflow reviewer: {e}")
        return False


async def update_workflow_hos(workflow_id: str, new_hos_id: str, new_msg_ts: str) -> bool:
    """Update workflow with new HOS info"""
    try:
        with _connect() as conn:
            conn.execute("""
                UPDATE approval_workflows
                SET hos_id = ?,
                    hos_msg_ts = ?,
                    updated_at = ?
                WHERE workflow_id = ?
            """, (new_hos_id, new_msg_ts, datetime.now(UAE_TZ).isoformat(), workflow_id))
            conn.commit()
            logger.info(f"Updated workflow {workflow_id} with new HOS {new_hos_id}")
            return True
    except Exception as e:
        logger.error(f"Error updating workflow HOS: {e}")
        return False


async def reassign_reviewer_approvals(old_reviewer_id: str, old_reviewer_channel: str,
                                      new_reviewer_id: str, new_reviewer_channel: str) -> Dict[str, Any]:
    """
    Reassign all pending reviewer approvals from old to new reviewer

    Args:
        old_reviewer_id: Old reviewer's Slack user ID
        old_reviewer_channel: Old reviewer's Slack channel ID
        new_reviewer_id: New reviewer's Slack user ID
        new_reviewer_channel: New reviewer's Slack channel ID

    Returns:
        Dictionary with reassignment results
    """
    logger.info(f"🔄 Starting reviewer approval reassignment: {old_reviewer_id} → {new_reviewer_id}")

    results = {
        'total': 0,
        'disabled': 0,
        'reassigned': 0,
        'failed': 0,
        'workflows': []
    }

    try:
        # Find all pending approvals
        workflows = await find_pending_approvals_for_reviewer(old_reviewer_id)
        results['total'] = len(workflows)

        if not workflows:
            logger.info("No pending reviewer approvals to reassign")
            return results

        logger.info(f"Found {len(workflows)} pending approvals to reassign")

        # Process each workflow
        for workflow in workflows:
            workflow_id = workflow['workflow_id']
            old_msg_ts = workflow.get('reviewer_msg_ts')

            try:
                # Step 1: Disable old message
                if old_msg_ts:
                    disabled = await disable_old_approval_message(
                        old_reviewer_channel,
                        old_msg_ts,
                        "Reviewer"
                    )
                    if disabled:
                        results['disabled'] += 1

                # Step 2: Send new approval to new reviewer
                new_msg_ts = await send_new_reviewer_approval(
                    workflow,
                    new_reviewer_channel,
                    new_reviewer_id
                )

                if new_msg_ts:
                    # Step 3: Update workflow in database
                    updated = await update_workflow_reviewer(
                        workflow_id,
                        new_reviewer_id,
                        new_msg_ts
                    )

                    if updated:
                        results['reassigned'] += 1
                        results['workflows'].append({
                            'workflow_id': workflow_id,
                            'task_number': workflow['task_number'],
                            'status': 'success'
                        })
                        logger.info(f"✅ Successfully reassigned workflow {workflow_id}")
                    else:
                        results['failed'] += 1
                        results['workflows'].append({
                            'workflow_id': workflow_id,
                            'task_number': workflow['task_number'],
                            'status': 'failed_to_update_db'
                        })
                else:
                    results['failed'] += 1
                    results['workflows'].append({
                        'workflow_id': workflow_id,
                        'task_number': workflow['task_number'],
                        'status': 'failed_to_send_new_message'
                    })

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error reassigning workflow {workflow_id}: {e}")
                results['failed'] += 1
                results['workflows'].append({
                    'workflow_id': workflow_id,
                    'task_number': workflow.get('task_number'),
                    'status': 'error',
                    'error': str(e)
                })

        logger.info(f"✅ Reviewer reassignment complete: {results['reassigned']}/{results['total']} successful")
        return results

    except Exception as e:
        logger.error(f"Error in reviewer reassignment: {e}")
        results['error'] = str(e)
        return results


async def reassign_hos_approvals(old_hos_id: str, old_hos_channel: str,
                                 new_hos_id: str, new_hos_channel: str) -> Dict[str, Any]:
    """
    Reassign all pending HOS approvals from old to new head of sales

    Args:
        old_hos_id: Old HOS's Slack user ID
        old_hos_channel: Old HOS's Slack channel ID
        new_hos_id: New HOS's Slack user ID
        new_hos_channel: New HOS's Slack channel ID

    Returns:
        Dictionary with reassignment results
    """
    logger.info(f"🔄 Starting HOS approval reassignment: {old_hos_id} → {new_hos_id}")

    results = {
        'total': 0,
        'disabled': 0,
        'reassigned': 0,
        'failed': 0,
        'workflows': []
    }

    try:
        # Find all pending approvals
        workflows = await find_pending_approvals_for_hos(old_hos_id)
        results['total'] = len(workflows)

        if not workflows:
            logger.info("No pending HOS approvals to reassign")
            return results

        logger.info(f"Found {len(workflows)} pending HOS approvals to reassign")

        # Process each workflow
        for workflow in workflows:
            workflow_id = workflow['workflow_id']
            old_msg_ts = workflow.get('hos_msg_ts')

            try:
                # Step 1: Disable old message
                if old_msg_ts:
                    disabled = await disable_old_approval_message(
                        old_hos_channel,
                        old_msg_ts,
                        "Head of Sales"
                    )
                    if disabled:
                        results['disabled'] += 1

                # Step 2: Send new approval to new HOS
                new_msg_ts = await send_new_hos_approval(
                    workflow,
                    new_hos_channel,
                    new_hos_id
                )

                if new_msg_ts:
                    # Step 3: Update workflow in database
                    updated = await update_workflow_hos(
                        workflow_id,
                        new_hos_id,
                        new_msg_ts
                    )

                    if updated:
                        results['reassigned'] += 1
                        results['workflows'].append({
                            'workflow_id': workflow_id,
                            'task_number': workflow['task_number'],
                            'status': 'success'
                        })
                        logger.info(f"✅ Successfully reassigned workflow {workflow_id}")
                    else:
                        results['failed'] += 1
                        results['workflows'].append({
                            'workflow_id': workflow_id,
                            'task_number': workflow['task_number'],
                            'status': 'failed_to_update_db'
                        })
                else:
                    results['failed'] += 1
                    results['workflows'].append({
                        'workflow_id': workflow_id,
                        'task_number': workflow['task_number'],
                        'status': 'failed_to_send_new_message'
                    })

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error reassigning workflow {workflow_id}: {e}")
                results['failed'] += 1
                results['workflows'].append({
                    'workflow_id': workflow_id,
                    'task_number': workflow.get('task_number'),
                    'status': 'error',
                    'error': str(e)
                })

        logger.info(f"✅ HOS reassignment complete: {results['reassigned']}/{results['total']} successful")
        return results

    except Exception as e:
        logger.error(f"Error in HOS reassignment: {e}")
        results['error'] = str(e)
        return results
