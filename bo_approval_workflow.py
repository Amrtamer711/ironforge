"""
Booking Order Approval Workflow System - REFACTORED

NEW Multi-stage approval chain:
1. ANY sales person uploads BO → Auto-parse → Send to Sales Coordinator immediately (NO edit phase)
2. Coordinator reviews parsed data in THREAD (not Excel yet)
3. Coordinator can edit via natural language in thread
4. When ready, coordinator says "execute" → Get Excel + Approve/Reject buttons IN THREAD
5. If coordinator rejects → Stay in same thread, continue editing
6. If coordinator approves → Send to Head of Sales (company-specific: Backlite or Viola)
7. If HoS approves → Send to Finance + Save to permanent database with BO reference
8. If HoS rejects → Modal with reason → REVIVE coordinator thread with rejection message

Thread lifecycle: Created on upload, stays alive through coordinator→HoS stages, revived on HoS rejection, closed on HoS approval
"""

import json
import asyncio
import os
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

# Config file path - use production path if /data/ exists, otherwise development
if os.path.exists("/data/"):
    CONFIG_PATH = Path("/data/hos_config.json")
else:
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


def get_head_of_sales_channel(company: str) -> Optional[str]:
    """Get Head of Sales Slack channel/user ID for specific company"""
    stakeholders = load_stakeholders_config()
    hos = stakeholders.get("head_of_sales", {})
    company_hos = hos.get(company, {})
    # Try user_id first (for DMs), then channel_id
    return company_hos.get("slack_user_id") or company_hos.get("slack_channel_id")


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
    Create new approval workflow after BO upload
    Immediately sends to coordinator (NO edit phase for sales person)

    Returns workflow_id
    """
    workflow_id = create_workflow_id(company)

    workflow_data = {
        "workflow_id": workflow_id,
        "sales_user_id": user_id,  # Changed from admin_user_id
        "company": company,
        "data": data,
        "warnings": warnings,
        "missing_required": missing_required,
        "original_file_path": str(original_file_path),
        "original_filename": original_filename,
        "file_type": file_type,
        "user_notes": user_notes,
        "stage": "coordinator",  # Current stage: coordinator, hos, finance
        "status": "pending",  # pending, approved, rejected
        "created_at": datetime.now().isoformat(),

        # Stage-specific data
        "coordinator_thread_ts": None,  # Thread where coordinator reviews (created immediately)
        "coordinator_thread_channel": None,
        "coordinator_approved": False,
        "coordinator_approved_by": None,
        "coordinator_approved_at": None,
        "coordinator_msg_ts": None,  # Message with buttons (only appears when they say "execute")

        "hos_approved": False,
        "hos_approved_by": None,
        "hos_approved_at": None,
        "hos_msg_ts": None,
        "hos_rejection_reason": None,  # Track HoS rejection reason for thread revival

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
        db.save_bo_workflow(
            workflow_id=workflow_id,
            workflow_data=json.dumps(workflow_data),
            updated_at=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"[BO APPROVAL] Failed to save workflow {workflow_id}: {e}")


async def get_workflow_from_db(workflow_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve workflow from database"""
    try:
        workflow_json = db.get_bo_workflow(workflow_id)
        if workflow_json:
            return json.loads(workflow_json)
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


def is_coordinator_thread_active(workflow: Dict[str, Any], thread_ts: str) -> bool:
    """
    Check if a thread is the active coordinator thread

    Returns True only if:
    1. Thread matches coordinator_thread_ts
    2. Coordinator has not approved yet (still in editing/review)
    3. Stage is still coordinator
    """
    coordinator_thread = workflow.get("coordinator_thread_ts")

    # No coordinator thread tracked
    if not coordinator_thread:
        return False

    # Thread doesn't match
    if coordinator_thread != thread_ts:
        return False

    # Coordinator already approved (thread should be closed)
    if workflow.get("coordinator_approved"):
        return False

    # Workflow moved past coordinator stage
    if workflow.get("stage") != "coordinator":
        return False

    return True


# =========================
# BUTTON INTERACTION HANDLERS
# =========================

async def handle_coordinator_approval(workflow_id: str, user_id: str, response_url: str):
    """
    Handle Sales Coordinator approval
    - Move to HoS stage
    - Send to appropriate Head of Sales with buttons
    """
    import bo_slack_messaging
    from pathlib import Path

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        logger.error(f"[BO APPROVAL] Workflow {workflow_id} not found")
        return

    logger.info(f"[BO APPROVAL] ✅ Coordinator {user_id} approved {workflow_id} - Client: {workflow['data'].get('client', 'N/A')}, Gross: AED {workflow['data'].get('gross_calc', 0):,.2f}")

    # Update workflow
    await update_workflow(workflow_id, {
        "coordinator_approved": True,
        "coordinator_approved_by": user_id,
        "coordinator_approved_at": datetime.now().isoformat(),
        "stage": "hos",
        "status": "pending"
    })

    # Update button message in thread
    coordinator_thread = workflow.get("coordinator_thread_ts")
    coordinator_channel = workflow.get("coordinator_thread_channel")

    if coordinator_thread and coordinator_channel:
        await config.slack_client.chat_postMessage(
            channel=coordinator_channel,
            thread_ts=coordinator_thread,
            text=config.markdown_to_slack("✅ **Coordinator Approved**\n\nMoving to Head of Sales for review...")
        )

    # Generate temp Excel for HoS review
    parser = BookingOrderParser(company=workflow["company"])
    temp_excel = await parser.generate_excel(workflow["data"], f"DRAFT_{workflow['company']}")

    # Get Head of Sales channel (company-specific)
    hos_channel = get_head_of_sales_channel(workflow["company"])
    if not hos_channel:
        logger.error(f"[BO APPROVAL] No Head of Sales configured for {workflow['company']}")
        return

    # Send to Head of Sales
    result = await bo_slack_messaging.send_to_head_of_sales(
        channel=hos_channel,
        workflow_id=workflow_id,
        company=workflow["company"],
        data=workflow["data"],
        warnings=workflow["warnings"],
        missing_required=workflow["missing_required"],
        excel_path=str(temp_excel)
    )

    # Update workflow with HoS message info
    await update_workflow(workflow_id, {
        "hos_msg_ts": result["message_id"]
    })

    logger.info(f"[BO APPROVAL] Sent {workflow_id} to Head of Sales")


async def handle_coordinator_rejection(workflow_id: str, user_id: str, response_url: str, rejection_reason: str, channel: str, message_ts: str):
    """
    Handle Sales Coordinator rejection
    - Stay in thread and continue editing
    - No thread revival needed (already in thread)
    """
    import bo_slack_messaging

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        return

    logger.info(f"[BO APPROVAL] ❌ Coordinator {user_id} rejected {workflow_id} - Client: {workflow['data'].get('client', 'N/A')} - Reason: {rejection_reason[:100]}")

    # Update workflow (stays in coordinator stage)
    await update_workflow(workflow_id, {
        "status": "rejected",
        "coordinator_rejection_reason": rejection_reason,
        "coordinator_rejected_by": user_id,
        "coordinator_rejected_at": datetime.now().isoformat()
    })

    # Post rejection message in thread
    coordinator_thread = workflow.get("coordinator_thread_ts")
    coordinator_channel = workflow.get("coordinator_thread_channel")

    if coordinator_thread and coordinator_channel:
        await config.slack_client.chat_postMessage(
            channel=coordinator_channel,
            thread_ts=coordinator_thread,
            text=config.markdown_to_slack(
                f"❌ **Rejected**\n\n**Reason:** {rejection_reason}\n\n"
                f"Please continue editing by telling me what changes are needed."
            )
        )

    logger.info(f"[BO APPROVAL] Coordinator continues editing in thread {coordinator_thread}")


async def handle_hos_approval(workflow_id: str, user_id: str, response_url: str):
    """
    Handle Head of Sales approval
    - Move to finance stage
    - Generate final BO reference
    - Save to permanent database
    - Move files to permanent locations
    - Notify finance (no buttons)
    - Close coordinator thread
    """
    import bo_slack_messaging
    from pathlib import Path
    import shutil

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        return

    logger.info(f"[BO APPROVAL] ✅ Head of Sales {user_id} approved {workflow_id} - Client: {workflow['data'].get('client', 'N/A')}, Gross: AED {workflow['data'].get('gross_calc', 0):,.2f}")

    # Generate final BO reference
    bo_ref = await db.generate_next_bo_ref()

    # Move original file to permanent location
    temp_file_path = Path(workflow["original_file_path"])
    company_dir = ORIGINAL_DIR / workflow["company"]
    company_dir.mkdir(parents=True, exist_ok=True)

    original_ext = temp_file_path.suffix
    final_original_path = company_dir / f"{bo_ref}{original_ext}"
    if temp_file_path.exists():
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
        "hos_approved": True,
        "hos_approved_by": user_id,
        "hos_approved_at": datetime.now().isoformat(),
        "stage": "finance",
        "status": "approved",
        "bo_ref": bo_ref,
        "saved_to_db": True
    })

    # Update HoS button message
    if workflow.get("hos_msg_ts"):
        await bo_slack_messaging.update_button_message(
            channel=workflow.get("hos_msg_ts", "").split("-")[0] if "-" in str(workflow.get("hos_msg_ts", "")) else "",
            message_ts=workflow.get("hos_msg_ts"),
            new_text=f"Approved by Head of Sales\nBO Reference: {bo_ref}\nNotifying Finance...",
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

    # Notify sales person who submitted
    await config.slack_client.chat_postMessage(
        channel=workflow["sales_user_id"],
        text=config.markdown_to_slack(
            f"✅ **Booking Order Approved & Finalized**\n\n"
            f"**BO Reference:** {bo_ref}\n"
            f"**Client:** {workflow['data'].get('client', 'N/A')}\n"
            f"**Gross Total:** AED {workflow['data'].get('gross_calc', 0):,.2f}\n\n"
            f"The booking order has been approved by all stakeholders and saved to the database."
        )
    )

    # Close coordinator thread with success message
    coordinator_thread = workflow.get("coordinator_thread_ts")
    coordinator_channel = workflow.get("coordinator_thread_channel")

    if coordinator_thread and coordinator_channel:
        await config.slack_client.chat_postMessage(
            channel=coordinator_channel,
            thread_ts=coordinator_thread,
            text=config.markdown_to_slack(
                f"✅ **APPROVED BY HEAD OF SALES**\n\n"
                f"**BO Reference:** {bo_ref}\n"
                f"This booking order has been finalized and sent to Finance."
            )
        )

    logger.info(f"[BO APPROVAL] ✅ COMPLETE - BO Reference: {bo_ref} - Client: {workflow['data'].get('client', 'N/A')}, Gross: AED {workflow['data'].get('gross_calc', 0):,.2f} - Workflow: {workflow_id}")


async def handle_hos_rejection(workflow_id: str, user_id: str, response_url: str, rejection_reason: str):
    """
    Handle Head of Sales rejection
    - REVIVE coordinator thread with rejection message
    - Move stage back to coordinator
    - Coordinator can continue editing
    """
    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        return

    logger.info(f"[BO APPROVAL] ❌ Head of Sales {user_id} rejected {workflow_id} - Client: {workflow['data'].get('client', 'N/A')} - Reason: {rejection_reason[:100]}")

    # Update workflow - move back to coordinator stage
    await update_workflow(workflow_id, {
        "status": "rejected",
        "stage": "coordinator",  # Move back to coordinator
        "hos_rejection_reason": rejection_reason,
        "hos_rejected_by": user_id,
        "hos_rejected_at": datetime.now().isoformat(),
        "hos_approved": False,  # Clear HoS approval
        "coordinator_approved": False  # Clear coordinator approval (they need to re-approve)
    })

    # REVIVE coordinator thread with rejection
    coordinator_thread = workflow.get("coordinator_thread_ts")
    coordinator_channel = workflow.get("coordinator_thread_channel")

    if coordinator_thread and coordinator_channel:
        await config.slack_client.chat_postMessage(
            channel=coordinator_channel,
            thread_ts=coordinator_thread,
            text=config.markdown_to_slack(
                f"❌ **REJECTED BY HEAD OF SALES**\n\n"
                f"**Reason:** {rejection_reason}\n\n"
                f"**Current Details:**\n"
                f"• Client: {workflow['data'].get('client', 'N/A')}\n"
                f"• Campaign: {workflow['data'].get('brand_campaign', 'N/A')}\n"
                f"• Gross Total: AED {workflow['data'].get('gross_calc', 0):,.2f}\n\n"
                f"Please make the necessary amendments. Tell me what changes are needed, or say 'execute' when ready to resubmit."
            )
        )
        logger.info(f"[BO APPROVAL] Revived coordinator thread {coordinator_thread} with HoS rejection")
    else:
        logger.error(f"[BO APPROVAL] No coordinator thread found to revive for {workflow_id}")

    # Notify sales person
    await config.slack_client.chat_postMessage(
        channel=workflow["sales_user_id"],
        text=config.markdown_to_slack(
            f"❌ **Booking Order Rejected by Head of Sales**\n\n"
            f"**Reason:** {rejection_reason}\n\n"
            f"The Sales Coordinator will make the necessary amendments and resubmit."
        )
    )


# =========================
# THREAD-BASED COORDINATOR FLOW
# =========================

async def handle_coordinator_thread_message(
    workflow_id: str,
    user_id: str,
    user_input: str,
    channel: str,
    thread_ts: str
) -> str:
    """
    Handle coordinator messages in their thread
    - Uses OpenAI Responses API with structured output
    - Parses coordinator intent and field updates
    - Re-generates Excel and buttons when they say "execute"
    - Continues editing on rejection
    """
    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        logger.error(f"[BO APPROVAL] Coordinator thread message: workflow {workflow_id} not found")
        return "Error: Workflow not found"

    current_data = workflow["data"]
    warnings = workflow.get("warnings", [])
    missing_required = workflow.get("missing_required", [])

    logger.info(f"[BO APPROVAL] Coordinator {user_id} message in thread {thread_ts}: '{user_input[:50]}...' for workflow {workflow_id}")

    # Build system prompt for OpenAI Responses API
    system_prompt = f"""
You are helping a Sales Coordinator review and amend a booking order. The user said: "{user_input}"

Determine their intent and parse any field updates:
- If they want to execute/submit/approve/done: action = 'execute'
- If they're making changes/corrections: action = 'edit' and parse the field updates
- If they're just viewing/asking: action = 'view'

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
                    'name': 'coordinator_response',
                    'strict': False,
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'action': {'type': 'string', 'enum': ['execute', 'edit', 'view']},
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

        logger.info(f"[BO APPROVAL] Coordinator thread action: {action} for {workflow_id}")

        if action == 'execute':
            # Generate Excel with updated data
            parser = BookingOrderParser(company=workflow["company"])
            temp_excel = await parser.generate_excel(current_data, f"DRAFT_{workflow['company']}_REVIEW")

            # Upload Excel to thread
            await config.slack_client.files_upload_v2(
                channel=channel,
                thread_ts=thread_ts,
                file=str(temp_excel),
                title=f"BO Draft - {current_data.get('client', 'Unknown')}"
            )

            # Send approval buttons IN THREAD
            text = f"✅ **Ready for Approval**\n\n"
            text += f"**Client:** {current_data.get('client', 'N/A')}\n"
            text += f"**Campaign:** {current_data.get('brand_campaign', 'N/A')}\n"
            text += f"**Gross Total:** AED {current_data.get('gross_calc', 0):,.2f}\n\n"
            text += "Please review the Excel file above and approve or reject:"

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

            # Post buttons in thread
            await config.slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=text,
                blocks=blocks
            )

            return message or "✅ I've generated the Excel file and approval buttons above. Please review and decide."

        elif action == 'edit':
            # Apply field updates
            fields = decision.get('fields', {})
            if fields:
                logger.info(f"[BO APPROVAL] Coordinator editing {len(fields)} fields in {workflow_id}: {list(fields.keys())}")
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
                response += "\nLet me know if you need any other changes, or say 'execute' to generate the Excel and approval buttons."
                return response
            else:
                return message or "I didn't catch any changes. What would you like to update?"

        elif action == 'view':
            # Show current draft
            preview = "📋 **Current Booking Order Details**\n\n"
            preview += f"**Client:** {current_data.get('client', 'N/A')}\n"
            preview += f"**Campaign:** {current_data.get('brand_campaign', 'N/A')}\n"
            preview += f"**BO Number:** {current_data.get('bo_number', 'N/A')}\n"
            preview += f"**BO Date:** {current_data.get('bo_date', 'N/A')}\n"
            preview += f"**Net (pre-VAT):** AED {current_data.get('net_pre_vat', 0):,.2f}\n"
            preview += f"**VAT (5%):** AED {current_data.get('vat_calc', 0):,.2f}\n"
            preview += f"**Gross Total:** AED {current_data.get('gross_calc', 0):,.2f}\n"
            preview += f"**Agency:** {current_data.get('agency', 'N/A')}\n"
            preview += f"**Sales Person:** {current_data.get('sales_person', 'N/A')}\n\n"

            if warnings:
                preview += f"⚠️ **Warnings:** {len(warnings)}\n"
            if missing_required:
                preview += f"❗ **Missing:** {', '.join(missing_required)}\n"

            preview += "\nSay 'execute' when ready to approve, or tell me what to change."
            return message or preview

        else:
            return "I didn't understand. Please tell me what to change, or say 'execute' when you're ready."

    except Exception as e:
        logger.error(f"[BO APPROVAL] Error in coordinator thread: {e}")
        return f"❌ **Error processing your request:** {str(e)}\n\nPlease try again."
