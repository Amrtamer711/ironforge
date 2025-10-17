"""
Booking Order Approval Workflow System

Multi-stage approval chain:
1. Admin completes edit → Send to Head of Sales with buttons
2. HoS Approves → Send to Sales Coordinator (company-specific) with buttons
3. Coordinator Approves → Notify Finance (no buttons) + Save to permanent database
4. Coordinator Rejects → Thread-based edit loop until they approve

Thread tracking: Only active during rejection, cleared on approval
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import logging

import config
import db
from booking_parser import BookingOrderParser, ORIGINAL_DIR, PARSED_DIR

logger = logging.getLogger("proposal-bot")

# In-memory cache for active approval workflows
approval_workflows: Dict[str, Dict[str, Any]] = {}

# Config file path
CONFIG_PATH = Path(__file__).parent / "render_main_data" / "hos_config.json"


def load_stakeholders_config() -> Dict[str, Any]:
    """Load stakeholders configuration"""
    try:
        with open(CONFIG_PATH, 'r') as f:
            config_data = json.load(f)
            return config_data.get("booking_order_stakeholders", {})
    except Exception as e:
        logger.error(f"[BO APPROVAL] Failed to load stakeholders config: {e}")
        return {}


def get_head_of_sales_channel() -> Optional[str]:
    """Get Head of Sales Slack channel/user ID"""
    stakeholders = load_stakeholders_config()
    hos = stakeholders.get("head_of_sales", {})
    # Try user_id first (for DMs), then channel_id
    return hos.get("slack_user_id") or hos.get("slack_channel_id")


def get_coordinator_channel(company: str) -> Optional[str]:
    """Get Sales Coordinator Slack channel/user ID for specific company"""
    stakeholders = load_stakeholders_config()
    coordinators = stakeholders.get("coordinators", {})
    coordinator = coordinators.get(company, {})
    # Try user_id first (for DMs), then channel_id
    return coordinator.get("slack_user_id") or coordinator.get("slack_channel_id")


def get_finance_channel() -> Optional[str]:
    """Get Finance Slack channel/user ID"""
    stakeholders = load_stakeholders_config()
    finance = stakeholders.get("finance", {})
    # Try user_id first (for DMs), then channel_id
    return finance.get("slack_user_id") or finance.get("slack_channel_id")


def create_workflow_id(company: str) -> str:
    """Create unique workflow ID"""
    timestamp = datetime.now().timestamp()
    return f"bo_approval_{company}_{int(timestamp)}"


async def create_approval_workflow(
    user_id: str,
    company: str,
    data: Dict[str, Any],
    warnings: list,
    missing_required: list,
    original_file_path: Path,
    original_filename: str,
    file_type: str,
    user_notes: str
) -> str:
    """
    Create new approval workflow after admin finishes editing

    Returns workflow_id
    """
    workflow_id = create_workflow_id(company)

    workflow_data = {
        "workflow_id": workflow_id,
        "admin_user_id": user_id,
        "company": company,
        "data": data,
        "warnings": warnings,
        "missing_required": missing_required,
        "original_file_path": str(original_file_path),
        "original_filename": original_filename,
        "file_type": file_type,
        "user_notes": user_notes,
        "stage": "hos",  # Current stage: hos, coordinator, finance
        "status": "pending",  # pending, approved, rejected
        "created_at": datetime.now().isoformat(),

        # Stage-specific data
        "hos_approved": False,
        "hos_approved_by": None,
        "hos_approved_at": None,
        "hos_msg_ts": None,

        "coordinator_approved": False,
        "coordinator_approved_by": None,
        "coordinator_approved_at": None,
        "coordinator_msg_ts": None,
        "coordinator_rejection_thread_ts": None,  # Track rejection thread (cleared on approval)

        "finance_notified": False,
        "finance_notified_at": None,
        "finance_msg_ts": None,

        # Final BO reference (only set after finance stage)
        "bo_ref": None,
        "saved_to_db": False
    }

    # Cache and persist
    approval_workflows[workflow_id] = workflow_data
    await save_workflow_to_db(workflow_id, workflow_data)

    logger.info(f"[BO APPROVAL] Created workflow {workflow_id} for {company}")
    return workflow_id


async def save_workflow_to_db(workflow_id: str, workflow_data: Dict[str, Any]):
    """Persist workflow to database"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO bo_approval_workflows
            (workflow_id, workflow_data, updated_at)
            VALUES (?, ?, ?)
        """, (workflow_id, json.dumps(workflow_data), datetime.now().isoformat()))

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[BO APPROVAL] Failed to save workflow {workflow_id}: {e}")


async def get_workflow_from_db(workflow_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve workflow from database"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT workflow_data FROM bo_approval_workflows WHERE workflow_id = ?
        """, (workflow_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return json.loads(row[0])
        return None
    except Exception as e:
        logger.error(f"[BO APPROVAL] Failed to retrieve workflow {workflow_id}: {e}")
        return None


async def get_workflow_with_cache(workflow_id: str) -> Optional[Dict[str, Any]]:
    """Get workflow from cache or database"""
    # Check cache first
    if workflow_id in approval_workflows:
        return approval_workflows[workflow_id]

    # Load from database and cache
    workflow = await get_workflow_from_db(workflow_id)
    if workflow:
        approval_workflows[workflow_id] = workflow
    return workflow


async def update_workflow(workflow_id: str, updates: Dict[str, Any]):
    """Update workflow with new data"""
    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        logger.error(f"[BO APPROVAL] Workflow {workflow_id} not found")
        return

    # Apply updates
    workflow.update(updates)

    # Cache and persist
    approval_workflows[workflow_id] = workflow
    await save_workflow_to_db(workflow_id, workflow)


def is_rejection_thread_active(workflow: Dict[str, Any], thread_ts: str) -> bool:
    """
    Check if a thread is an active rejection thread

    Returns True only if:
    1. Thread matches coordinator_rejection_thread_ts
    2. Thread has not been cleared (still rejecting, not approved yet)
    """
    rejection_thread = workflow.get("coordinator_rejection_thread_ts")

    # No rejection thread tracked
    if not rejection_thread:
        return False

    # Thread doesn't match
    if rejection_thread != thread_ts:
        return False

    # Thread was cleared (they already approved)
    # This shouldn't happen if we clear it properly, but double-check
    if workflow.get("coordinator_approved"):
        return False

    return True


async def clear_rejection_thread(workflow_id: str):
    """Clear rejection thread tracking after approval"""
    await update_workflow(workflow_id, {
        "coordinator_rejection_thread_ts": None
    })
    logger.info(f"[BO APPROVAL] Cleared rejection thread for {workflow_id}")


# =========================
# BUTTON INTERACTION HANDLERS
# =========================

async def handle_hos_approval(workflow_id: str, user_id: str, response_url: str):
    """
    Handle Head of Sales approval
    - Update workflow stage to coordinator
    - Send to appropriate coordinator with buttons
    """
    import bo_slack_messaging
    from pathlib import Path

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        logger.error(f"[BO APPROVAL] Workflow {workflow_id} not found")
        return

    logger.info(f"[BO APPROVAL] HoS approved {workflow_id}")

    # Update workflow
    await update_workflow(workflow_id, {
        "hos_approved": True,
        "hos_approved_by": user_id,
        "hos_approved_at": datetime.now().isoformat(),
        "stage": "coordinator",
        "status": "pending"
    })

    # Update button message
    await bo_slack_messaging.update_button_message(
        channel=workflow["hos_msg_ts"].split("-")[0] if "-" in str(workflow.get("hos_msg_ts", "")) else config.slack_client,
        message_ts=workflow.get("hos_msg_ts"),
        new_text=f"Approved by Head of Sales\nMoving to Sales Coordinator review...",
        approved=True
    )

    # Generate temp Excel for coordinator review
    parser = BookingOrderParser(company=workflow["company"])
    temp_excel = await parser.generate_excel(workflow["data"], f"DRAFT_{workflow['company']}")

    # Get coordinator channel
    coordinator_channel = get_coordinator_channel(workflow["company"])
    if not coordinator_channel:
        logger.error(f"[BO APPROVAL] No coordinator configured for {workflow['company']}")
        return

    # Send to coordinator
    result = await bo_slack_messaging.send_to_coordinator(
        channel=coordinator_channel,
        workflow_id=workflow_id,
        company=workflow["company"],
        data=workflow["data"],
        excel_path=str(temp_excel)
    )

    # Update workflow with coordinator message info
    await update_workflow(workflow_id, {
        "coordinator_msg_ts": result["message_id"]
    })

    logger.info(f"[BO APPROVAL] Sent {workflow_id} to coordinator")


async def handle_hos_rejection(workflow_id: str, user_id: str, response_url: str, rejection_reason: str):
    """
    Handle Head of Sales rejection
    - Notify admin to make amendments
    - Return to edit flow
    """
    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        return

    logger.info(f"[BO APPROVAL] HoS rejected {workflow_id}: {rejection_reason}")

    # Update workflow
    await update_workflow(workflow_id, {
        "status": "rejected",
        "hos_rejection_reason": rejection_reason,
        "hos_rejected_by": user_id,
        "hos_rejected_at": datetime.now().isoformat()
    })

    # Notify admin
    admin_channel = workflow["admin_user_id"]
    await config.slack_client.chat_postMessage(
        channel=admin_channel,
        text=config.markdown_to_slack(
            f"❌ **Booking Order Rejected by Head of Sales**\n\n"
            f"**Reason:** {rejection_reason}\n\n"
            f"Please make the necessary amendments and resubmit."
        )
    )

    # Return admin to edit flow
    from llm import pending_booking_orders
    pending_booking_orders[admin_channel] = {
        "data": workflow["data"],
        "warnings": workflow["warnings"],
        "missing_required": workflow["missing_required"],
        "original_file_path": Path(workflow["original_file_path"]),
        "original_filename": workflow["original_filename"],
        "company": workflow["company"],
        "file_type": workflow["file_type"],
        "user_notes": workflow["user_notes"]
    }


async def handle_coordinator_approval(workflow_id: str, user_id: str, response_url: str):
    """
    Handle Sales Coordinator approval
    - Move to finance stage
    - Generate final BO reference
    - Save to permanent database
    - Move files to permanent locations
    - Notify finance (no buttons)
    """
    import bo_slack_messaging
    from pathlib import Path
    import shutil

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        return

    logger.info(f"[BO APPROVAL] Coordinator approved {workflow_id}")

    # Clear rejection thread if it was set
    await clear_rejection_thread(workflow_id)

    # Generate final BO reference
    bo_ref = await db.generate_next_bo_ref()

    # Move original file to permanent location
    temp_file_path = Path(workflow["original_file_path"])
    company_dir = ORIGINAL_DIR / workflow["company"]
    company_dir.mkdir(parents=True, exist_ok=True)

    original_ext = temp_file_path.suffix
    final_original_path = company_dir / f"{bo_ref}{original_ext}"
    shutil.move(str(temp_file_path), str(final_original_path))

    # Generate final parsed Excel
    parser = BookingOrderParser(company=workflow["company"])
    final_excel_path = await parser.generate_excel(workflow["data"], bo_ref)

    # Save to permanent database
    await db.save_booking_order(
        bo_ref=bo_ref,
        company=workflow["company"],
        data=workflow["data"],
        warnings=workflow["warnings"],
        missing_required=workflow["missing_required"],
        file_type=workflow["file_type"],
        original_file_path=str(final_original_path),
        parsed_excel_path=str(final_excel_path),
        user_notes=workflow.get("user_notes", "")
    )

    # Update workflow
    await update_workflow(workflow_id, {
        "coordinator_approved": True,
        "coordinator_approved_by": user_id,
        "coordinator_approved_at": datetime.now().isoformat(),
        "stage": "finance",
        "status": "approved",
        "bo_ref": bo_ref,
        "saved_to_db": True
    })

    # Update button message
    if workflow.get("coordinator_msg_ts"):
        await bo_slack_messaging.update_button_message(
            channel=workflow.get("coordinator_msg_ts", "").split("-")[0] if "-" in str(workflow.get("coordinator_msg_ts", "")) else "",
            message_ts=workflow.get("coordinator_msg_ts"),
            new_text=f"Approved by Sales Coordinator\nBO Reference: {bo_ref}\nNotifying Finance...",
            approved=True
        )

    # Notify finance
    finance_channel = get_finance_channel()
    if finance_channel:
        result = await bo_slack_messaging.notify_finance(
            channel=finance_channel,
            bo_ref=bo_ref,
            company=workflow["company"],
            data=workflow["data"],
            excel_path=str(final_excel_path)
        )

        await update_workflow(workflow_id, {
            "finance_notified": True,
            "finance_notified_at": datetime.now().isoformat(),
            "finance_msg_ts": result["message_id"]
        })

    # Notify admin of completion
    await config.slack_client.chat_postMessage(
        channel=workflow["admin_user_id"],
        text=config.markdown_to_slack(
            f"✅ **Booking Order Approved & Finalized**\n\n"
            f"**BO Reference:** {bo_ref}\n"
            f"**Client:** {workflow['data'].get('client', 'N/A')}\n"
            f"**Gross Total:** AED {workflow['data'].get('gross_calc', 0):,.2f}\n\n"
            f"The booking order has been approved by all stakeholders and saved to the database."
        )
    )

    logger.info(f"[BO APPROVAL] {workflow_id} complete - BO Reference: {bo_ref}")


async def handle_coordinator_rejection(workflow_id: str, user_id: str, response_url: str, rejection_reason: str, channel: str, message_ts: str):
    """
    Handle Sales Coordinator rejection
    - Start thread-based edit loop
    - Track thread_ts for future messages
    - Coordinator can make amendments via conversation in thread
    """
    import bo_slack_messaging

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        return

    logger.info(f"[BO APPROVAL] Coordinator rejected {workflow_id}: {rejection_reason}")

    # Update button message to show rejection
    await bo_slack_messaging.update_button_message(
        channel=channel,
        message_ts=message_ts,
        new_text=f"Rejected by Sales Coordinator\nReason: {rejection_reason}\nStarting amendment process in thread...",
        approved=False
    )

    # Start thread with rejection details
    thread_result = await bo_slack_messaging.send_rejection_to_thread(
        channel=channel,
        thread_ts=message_ts,  # Reply to the button message
        rejection_reason=rejection_reason,
        data=workflow["data"]
    )

    # Track thread in workflow (this is the ACTIVE rejection thread)
    await update_workflow(workflow_id, {
        "status": "rejected",
        "coordinator_rejection_reason": rejection_reason,
        "coordinator_rejected_by": user_id,
        "coordinator_rejected_at": datetime.now().isoformat(),
        "coordinator_rejection_thread_ts": message_ts,  # Track thread for edit loop
        "coordinator_rejection_channel": channel
    })

    logger.info(f"[BO APPROVAL] Started rejection thread {message_ts} for {workflow_id}")


# =========================
# THREAD-BASED EDIT LOOP
# =========================

async def handle_coordinator_thread_message(
    workflow_id: str,
    user_id: str,
    user_input: str,
    channel: str,
    thread_ts: str
) -> str:
    """
    Handle coordinator messages in rejection thread
    - Similar to handle_booking_order_edit_flow but for coordinator amendments
    - Uses LLM to parse intent and field updates
    - Re-generates temp Excel after edits
    - Sends new approval buttons when they say they're done
    """
    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        return "Error: Workflow not found"

    current_data = workflow["data"]
    warnings = workflow.get("warnings", [])
    missing_required = workflow.get("missing_required", [])

    # Build system prompt for LLM
    system_prompt = f"""
You are helping a Sales Coordinator amend a rejected booking order. The user said: "{user_input}"

Determine their intent and parse any field updates:
- If they want to re-submit/approve/done: action = 'resubmit'
- If they're making changes/corrections: action = 'edit' and parse the field updates

Current booking order data: {json.dumps(current_data, indent=2)}
Warnings: {warnings}
Missing required fields: {missing_required}

Field mapping (use these exact keys when updating):
- Client/client name/customer → "client"
- Campaign/campaign name/brand → "brand_campaign"
- BO number/booking order number → "bo_number"
- BO date/booking order date → "bo_date"
- Net/net amount/net pre-VAT → "net_pre_vat"
- VAT/vat amount → "vat_calc"
- Gross/gross amount/total → "gross_calc"
- Agency/agency name → "agency"
- Sales person/salesperson → "sales_person"
- SLA percentage → "sla_pct"
- Payment terms → "payment_terms"
- Commission percentage → "commission_pct"
- Notes → "notes"
- Category → "category"
- Asset → "asset"

Return JSON with: action, fields (only changed fields), message (natural language response to user).
IMPORTANT: Use natural language in messages. Be friendly and conversational.
"""

    try:
        res = await config.openai_client.responses.create(
            model=config.OPENAI_MODEL,
            input=[{"role": "system", "content": system_prompt}],
            text={
                'format': {
                    'type': 'json_schema',
                    'name': 'coordinator_edit_response',
                    'strict': False,
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'action': {'type': 'string', 'enum': ['resubmit', 'edit']},
                            'fields': {
                                'type': 'object',
                                'properties': {
                                    'client': {'type': 'string'},
                                    'brand_campaign': {'type': 'string'},
                                    'bo_number': {'type': 'string'},
                                    'bo_date': {'type': 'string'},
                                    'net_pre_vat': {'type': 'number'},
                                    'vat_calc': {'type': 'number'},
                                    'gross_calc': {'type': 'number'},
                                    'agency': {'type': 'string'},
                                    'sales_person': {'type': 'string'},
                                    'sla_pct': {'type': 'number'},
                                    'payment_terms': {'type': 'string'},
                                    'commission_pct': {'type': 'number'},
                                    'notes': {'type': 'string'},
                                    'category': {'type': 'string'},
                                    'asset': {'type': 'string'}
                                },
                                'additionalProperties': True
                            },
                            'message': {'type': 'string'}
                        },
                        'required': ['action'],
                        'additionalProperties': False
                    }
                }
            },
            store=False
        )

        decision = json.loads(res.output[0].content[-1].text)
        action = decision.get('action')
        message = decision.get('message', '')

        if action == 'resubmit':
            # Re-generate Excel with updated data
            parser = BookingOrderParser(company=workflow["company"])
            temp_excel = await parser.generate_excel(current_data, f"DRAFT_{workflow['company']}_AMENDED")

            # Send new approval buttons in thread
            import bo_slack_messaging

            text = f"✅ **Updated Booking Order - Ready for Re-Approval**\n\n"
            text += f"**Client:** {current_data.get('client', 'N/A')}\n"
            text += f"**Campaign:** {current_data.get('brand_campaign', 'N/A')}\n"
            text += f"**Gross Total:** AED {current_data.get('gross_calc', 0):,.2f}\n\n"
            text += "Please review the updated booking order:"

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
                            "text": {"type": "plain_text", "text": "❌ Reject Again"},
                            "style": "danger",
                            "value": workflow_id,
                            "action_id": "reject_bo_coordinator"
                        }
                    ]
                }
            ]

            # Upload Excel
            await config.slack_client.files_upload_v2(
                channel=channel,
                thread_ts=thread_ts,
                file=str(temp_excel),
                title=f"BO Draft (Amended) - {current_data.get('client', 'Unknown')}"
            )

            # Post buttons in thread
            await config.slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="Please review and approve or reject:",
                blocks=blocks
            )

            return message or "✅ I've updated the booking order with your changes and generated a new version. Please review the Excel file above and use the buttons to approve or reject."

        elif action == 'edit':
            # Apply field updates
            fields = decision.get('fields', {})
            if fields:
                # Update the data
                for field, value in fields.items():
                    current_data[field] = value

                # Recalculate VAT and gross if net changed
                if 'net_pre_vat' in fields:
                    current_data['vat_calc'] = round(current_data['net_pre_vat'] * 0.05, 2)
                    current_data['gross_calc'] = round(current_data['net_pre_vat'] + current_data['vat_calc'], 2)

                # Save updated data back to workflow
                await update_workflow(workflow_id, {
                    "data": current_data
                })

                response = message or "✅ **Changes applied:**\n"
                for field, value in fields.items():
                    response += f"• {field}: {value}\n"
                response += "\nLet me know if you need any other changes, or say 'done' to resubmit for approval."
                return response
            else:
                return message or "I didn't catch any changes. What would you like to update?"

        else:
            return "I didn't understand. Please tell me what to change, or say 'done' when you're ready to resubmit."

    except Exception as e:
        logger.error(f"[BO APPROVAL] Error in coordinator thread edit: {e}")
        return f"❌ **Error processing your request:** {str(e)}\n\nPlease try again."
