"""
Booking Order Approval Workflow System - REFACTORED

NEW Multi-stage approval chain (IMMEDIATE EXCEL FLOW):
1. ANY sales person uploads BO → Auto-parse → Generate Excel immediately
2. Send Excel + Summary + Approve/Reject buttons to Sales Coordinator
3. Coordinator reviews Excel and clicks:
   a. APPROVE → Moves to Head of Sales for approval
   b. REJECT → Opens thread on button message for natural language edits
4. If coordinator rejects: Thread opens for editing
   - Coordinator makes changes via natural language in thread
   - Says "execute" to regenerate Excel + new approval buttons in same thread
5. If coordinator approves → Send Excel + buttons to Head of Sales (company-specific: Backlite or Viola)
6. If HoS approves → Send to Finance + Save to permanent database with BO reference
7. If HoS rejects → Modal with reason → REVIVE coordinator thread with rejection message

Thread lifecycle: Created only on rejection, used for edits, revived on HoS rejection
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
from booking_parser import BookingOrderParser, COMBINED_BOS_DIR

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


async def get_head_of_sales_channel(company: str) -> Optional[str]:
    """
    Get Head of Sales DM channel ID for specific company.
    Uses conversations.open to get DM channel ID from user_id.
    """
    stakeholders = load_stakeholders_config()
    hos = stakeholders.get("head_of_sales", {})
    company_hos = hos.get(company, {})

    # Try channel_id first (if already stored), otherwise get from user_id
    channel_id = company_hos.get("slack_channel_id")
    if channel_id:
        return channel_id

    # Get user_id and open DM conversation to get channel ID
    user_id = company_hos.get("slack_user_id")
    if user_id:
        try:
            response = await config.slack_client.conversations_open(users=[user_id])
            return response["channel"]["id"]
        except Exception as e:
            logger.error(f"[BO APPROVAL] Failed to open DM with user {user_id}: {e}")
            return None

    return None


async def get_coordinator_channel(company: str) -> Optional[str]:
    """
    Get Sales Coordinator DM channel ID for specific company.
    Uses conversations.open to get DM channel ID from user_id.
    """
    stakeholders = load_stakeholders_config()
    coordinators = stakeholders.get("coordinators", {})
    coordinator = coordinators.get(company, {})

    # Try channel_id first (if already stored), otherwise get from user_id
    channel_id = coordinator.get("slack_channel_id")
    if channel_id:
        return channel_id

    # Get user_id and open DM conversation to get channel ID
    user_id = coordinator.get("slack_user_id")
    if user_id:
        try:
            response = await config.slack_client.conversations_open(users=[user_id])
            return response["channel"]["id"]
        except Exception as e:
            logger.error(f"[BO APPROVAL] Failed to open DM with user {user_id}: {e}")
            return None

    return None


async def get_finance_channel() -> Optional[str]:
    """
    Get Finance DM channel ID.
    Uses conversations.open to get DM channel ID from user_id.
    """
    stakeholders = load_stakeholders_config()
    finance = stakeholders.get("finance", {})

    # Try channel_id first (if already stored), otherwise get from user_id
    channel_id = finance.get("slack_channel_id")
    if channel_id:
        return channel_id

    # Get user_id and open DM conversation to get channel ID
    user_id = finance.get("slack_user_id")
    if user_id:
        try:
            response = await config.slack_client.conversations_open(users=[user_id])
            return response["channel"]["id"]
        except Exception as e:
            logger.error(f"[BO APPROVAL] Failed to open DM with user {user_id}: {e}")
            return None

    return None


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
    from booking_parser import ORIGINAL_BOS_DIR
    import shutil

    workflow_id = create_workflow_id(company)

    # Copy original file to permanent storage (prevents loss if temp files are cleaned up)
    # This ensures the original BO is preserved throughout the entire workflow lifecycle
    permanent_original_path = ORIGINAL_BOS_DIR / f"{workflow_id}_{original_filename}"
    try:
        shutil.copy2(original_file_path, permanent_original_path)
        logger.info(f"[BO APPROVAL] Copied original BO to permanent storage: {permanent_original_path}")
    except Exception as e:
        logger.error(f"[BO APPROVAL] Failed to copy original BO to permanent storage: {e}")
        # Fall back to temp path if copy fails
        permanent_original_path = original_file_path

    workflow_data = {
        "workflow_id": workflow_id,
        "sales_user_id": user_id,  # Changed from admin_user_id
        "company": company,
        "data": data,
        "warnings": warnings,
        "missing_required": missing_required,
        "original_file_path": str(permanent_original_path),  # Store permanent path, not temp
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
    Check if a thread is the active coordinator thread for EDITING

    Returns True only if:
    1. Thread matches coordinator_thread_ts
    2. Coordinator has REJECTED (thread opened for editing)
    3. Coordinator has not approved yet
    4. Stage is still coordinator

    NOTE: Buttons (approve/reject) work independently - this only controls text message handling
    """
    coordinator_thread = workflow.get("coordinator_thread_ts")

    # No coordinator thread tracked
    if not coordinator_thread:
        return False

    # Thread doesn't match
    if coordinator_thread != thread_ts:
        return False

    # Thread is only active for editing AFTER rejection
    # If coordinator hasn't rejected yet, they should use buttons, not type in thread
    if workflow.get("status") != "coordinator_rejected":
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
    - Update button message to show approval
    - Move to HoS stage
    - Send to appropriate Head of Sales with buttons
    """
    import bo_slack_messaging
    from pathlib import Path

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        logger.error(f"[BO APPROVAL] Workflow {workflow_id} not found")
        return

    # Prevent double-approval (e.g., clicking old button after new one was generated)
    if workflow.get("coordinator_approved"):
        logger.warning(f"[BO APPROVAL] Workflow {workflow_id} already approved by coordinator - ignoring duplicate approval")
        await bo_slack_messaging.post_response_url(response_url, {
            "replace_original": False,
            "text": "⚠️ This booking order has already been approved and sent to Head of Sales."
        })
        return

    logger.info(f"[BO APPROVAL] ✅ Coordinator {user_id} approved {workflow_id} - Client: {workflow['data'].get('client', 'N/A')}, Gross: AED {workflow['data'].get('gross_calc', 0):,.2f}")

    # Update button message to show approval is being processed
    coordinator_msg_ts = workflow.get("coordinator_msg_ts")
    coordinator_channel = workflow.get("coordinator_thread_channel")
    coordinator_thread_ts = workflow.get("coordinator_thread_ts")

    if coordinator_msg_ts and coordinator_channel:
        approver_name = await bo_slack_messaging.get_user_real_name(user_id)
        await bo_slack_messaging.update_button_message(
            channel=coordinator_channel,
            message_ts=coordinator_msg_ts,
            new_text=f"✅ **APPROVED** by {approver_name}\n\n⏳ Waiting for file upload to complete...",
            approved=True
        )

    # IMPORTANT: Wait 5 seconds for file upload to complete before proceeding
    logger.info(f"[BO APPROVAL] Waiting 5 seconds for file upload to complete...")
    await asyncio.sleep(5)

    # Update workflow
    await update_workflow(workflow_id, {
        "coordinator_approved": True,
        "coordinator_approved_by": user_id,
        "coordinator_approved_at": datetime.now().isoformat(),
        "stage": "hos",
        "status": "pending"
    })

    # Post status update in thread
    if coordinator_thread_ts and coordinator_channel:
        await bo_slack_messaging.post_to_thread(
            channel=coordinator_channel,
            thread_ts=coordinator_thread_ts,
            text=f"✅ **Approved by {approver_name}** - Moving to Head of Sales for review..."
        )

    # Generate combined PDF for HoS review (Excel + Original BO)
    parser = BookingOrderParser(company=workflow["company"])

    # Get the ORIGINAL uploaded BO file path from workflow (NOT the combined PDF)
    original_file_path = workflow.get("original_file_path")
    if not original_file_path or not Path(original_file_path).exists():
        logger.error(f"[BO APPROVAL] Original BO file not found for {workflow_id}")
        return

    original_bo_path = Path(original_file_path)

    # Generate fresh combined PDF with updated data
    temp_combined_pdf = await parser.generate_combined_pdf(
        workflow["data"],
        f"DRAFT_{workflow['company']}_HOS",
        original_bo_path
    )

    # Get Head of Sales channel (company-specific, uses conversations.open to get DM channel ID)
    hos_channel = await get_head_of_sales_channel(workflow["company"])
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
        combined_pdf_path=str(temp_combined_pdf)
    )

    # Update workflow with HoS message info
    await update_workflow(workflow_id, {
        "hos_msg_ts": result["message_id"],
        "hos_channel": result["channel"]
    })

    logger.info(f"[BO APPROVAL] Sent {workflow_id} to Head of Sales")


async def handle_coordinator_rejection(workflow_id: str, user_id: str, response_url: str, rejection_reason: str, channel: str, message_ts: str):
    """
    Handle Sales Coordinator rejection
    - Create thread on the button message for editing
    - Allow coordinator to make natural language edits
    """
    import bo_slack_messaging

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        return

    logger.info(f"[BO APPROVAL] ❌ Coordinator {user_id} rejected {workflow_id} - Client: {workflow['data'].get('client', 'N/A')} - Reason: {rejection_reason[:100]}")

    # Update workflow
    await update_workflow(workflow_id, {
        "status": "coordinator_rejected",
        "coordinator_rejection_reason": rejection_reason,
        "coordinator_rejected_by": user_id,
        "coordinator_rejected_at": datetime.now().isoformat(),
        "coordinator_thread_ts": message_ts,  # Use button message as thread root
        "coordinator_thread_channel": channel
    })

    # Update the button message to show rejection
    rejecter_name = await bo_slack_messaging.get_user_real_name(user_id)
    await bo_slack_messaging.update_button_message(
        channel=channel,
        message_ts=message_ts,
        new_text=f"❌ **REJECTED** by {rejecter_name}",
        approved=False
    )

    # Post rejection message in thread with edit instructions
    await config.slack_client.chat_postMessage(
        channel=channel,
        thread_ts=message_ts,
        text=config.markdown_to_slack(
            f"❌ **Booking Order Rejected**\n\n"
            f"**Reason:** {rejection_reason}\n\n"
            f"**Current Details:**\n"
            f"• Client: {workflow['data'].get('client', 'N/A')}\n"
            f"• Campaign: {workflow['data'].get('brand_campaign', 'N/A')}\n"
            f"• Gross Total: AED {workflow['data'].get('gross_calc', 0):,.2f}\n\n"
            f"💬 **Please tell me what changes are needed:**\n"
            f"Examples:\n"
            f"• 'Change client to Acme Corp'\n"
            f"• 'Net should be 150,000'\n"
            f"• 'Add location: Dubai Mall, start 2025-03-01, end 2025-03-31, net 50000'\n\n"
            f"When ready, say **'execute'** to regenerate the Excel and approval buttons."
        )
    )

    logger.info(f"[BO APPROVAL] Created editing thread at {message_ts} in {channel}")


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

    # Prevent double-approval
    if workflow.get("hos_approved"):
        logger.warning(f"[BO APPROVAL] Workflow {workflow_id} already approved by HoS - ignoring duplicate approval")
        await bo_slack_messaging.post_response_url(response_url, {
            "replace_original": False,
            "text": "⚠️ This booking order has already been approved and saved to the database."
        })
        return

    logger.info(f"[BO APPROVAL] ✅ Head of Sales {user_id} approved {workflow_id} - Client: {workflow['data'].get('client', 'N/A')}, Gross: AED {workflow['data'].get('gross_calc', 0):,.2f}")

    # Generate final BO reference
    bo_ref = db.generate_next_bo_ref()

    # Generate final combined PDF (Excel + Original BO)
    parser = BookingOrderParser(company=workflow["company"])
    permanent_original_path = Path(workflow["original_file_path"])
    final_combined_pdf = await parser.generate_combined_pdf(
        workflow["data"],
        bo_ref,
        permanent_original_path
    )

    # Clean up permanent original file (we now have the final combined PDF)
    if permanent_original_path.exists():
        try:
            permanent_original_path.unlink()
            logger.info(f"[BO APPROVAL] Cleaned up original BO file: {permanent_original_path}")
        except Exception as e:
            logger.warning(f"[BO APPROVAL] Failed to clean up original BO file: {e}")

    # Save to permanent database
    await db.save_booking_order(
        bo_ref=bo_ref,
        company=workflow["company"],
        data=workflow["data"],
        warnings=workflow["warnings"],
        missing_required=workflow["missing_required"],
        file_type=workflow["file_type"],
        original_file_path=str(final_combined_pdf),  # Now stores combined PDF path
        parsed_excel_path=str(final_combined_pdf),   # Same file for both (backwards compatibility)
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
    if workflow.get("hos_msg_ts") and workflow.get("hos_channel"):
        await bo_slack_messaging.update_button_message(
            channel=workflow.get("hos_channel"),
            message_ts=workflow.get("hos_msg_ts"),
            new_text=f"✅ **APPROVED BY HEAD OF SALES**\nBO Reference: {bo_ref}\nNotifying Finance...",
            approved=True
        )

    # Notify finance (uses conversations.open to get DM channel ID)
    finance_channel = await get_finance_channel()
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
    - Maintains thread-specific conversation history (separate from main chat)
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

    # Get or initialize thread-specific conversation history
    thread_history = workflow.get("thread_history", [])

    logger.info(f"[BO APPROVAL] Coordinator {user_id} message in thread {thread_ts}: '{user_input[:50]}...' for workflow {workflow_id} (history: {len(thread_history)} messages)")

    # Build system prompt for OpenAI Responses API
    system_prompt = f"""
You are helping a Sales Coordinator review and amend a booking order.

Determine their intent and parse any field updates:
- If they want to execute/submit/approve/done: action = 'execute'
- If they're making changes/corrections: action = 'edit' and parse the field updates
- If they're just viewing/asking: action = 'view'

Current booking order data: {json.dumps(current_data, indent=2)}
Warnings: {warnings}
Missing required fields: {missing_required}

Field mapping (use these exact keys when updating):

**Global Fields:**
- Client/client name/customer → "client"
- Campaign/campaign name/brand → "brand_campaign"
- BO number/booking order number → "bo_number"
- BO date/booking order date → "bo_date"
- Net/net amount/net pre-VAT → "net_pre_vat"
- VAT/vat amount → "vat_value" or "vat_calc"
- Gross/gross amount/total → "gross_amount" or "gross_calc"
- Agency/agency name → "agency"
- Sales person/salesperson → "sales_person"
- SLA percentage → "sla_pct"
- Payment terms → "payment_terms"
- Commission percentage → "commission_pct"
- Municipality fee/DM fee/Dubai Municipality → "municipality_fee" (single global total)
- Production/upload fee → "production_upload_fee" (single global total)
- Notes → "notes"
- Category → "category"
- Asset → "asset" (can be string or array of strings)

**Location Fields (provide full locations array if editing locations):**
- Locations → "locations" (array of objects)
  Each location object can have:
  - "name": location/site name
  - "asset": asset code for this location
  - "start_date": YYYY-MM-DD format
  - "end_date": YYYY-MM-DD format
  - "campaign_duration": e.g., "1 month"
  - "net_amount": rental amount for this location (fees are global, not per-location)

Return JSON with: action, fields (only changed fields), message (natural language response to user).

IMPORTANT FOR MESSAGES:
- Use natural, friendly language - NO technical field names or variable names
- Say "client" not "client field" or "client_name"
- Say "net amount" not "net_pre_vat"
- Say "campaign name" not "brand_campaign"
- Be conversational and helpful
- Confirm what changed in plain English

Examples:
- GOOD: "I've updated the client to Acme Corp and the net amount to AED 50,000."
- BAD: "Updated client field and net_pre_vat variable."
- GOOD: "Changed the campaign to Summer Sale 2025."
- BAD: "Set brand_campaign to Summer Sale 2025."
"""

    try:
        # Build input with thread history + current user message
        input_messages = [{"role": "system", "content": system_prompt}]

        # Add thread history (last 10 messages to keep context manageable)
        for msg in thread_history[-10:]:
            input_messages.append({"role": msg["role"], "content": msg["content"]})

        # Add current user message
        input_messages.append({"role": "user", "content": user_input})

        res = await config.openai_client.responses.create(
            model=config.OPENAI_MODEL,
            input=input_messages,
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
                                    'vat_value': {'type': 'number'},
                                    'vat_calc': {'type': 'number'},
                                    'gross_amount': {'type': 'number'},
                                    'gross_calc': {'type': 'number'},
                                    'agency': {'type': 'string'},
                                    'sales_person': {'type': 'string'},
                                    'sla_pct': {'type': 'number'},
                                    'payment_terms': {'type': 'string'},
                                    'commission_pct': {'type': 'number'},
                                    'notes': {'type': 'string'},
                                    'category': {'type': 'string'},
                                    'municipality_fee': {'type': 'number'},
                                    'production_upload_fee': {'type': 'number'},
                                    'asset': {
                                        'anyOf': [
                                            {'type': 'string'},
                                            {'type': 'array', 'items': {'type': 'string'}}
                                        ]
                                    },
                                    'locations': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'properties': {
                                                'name': {'type': 'string'},
                                                'asset': {'type': 'string'},
                                                'start_date': {'type': 'string'},
                                                'end_date': {'type': 'string'},
                                                'campaign_duration': {'type': 'string'},
                                                'net_amount': {'type': 'number'}
                                            }
                                        }
                                    }
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

        # Update thread history with user message and assistant response
        thread_history.append({"role": "user", "content": user_input})
        thread_history.append({"role": "assistant", "content": message or f"[Action: {action}]"})

        # Keep last 20 messages (10 exchanges) in thread history
        thread_history = thread_history[-20:]

        # Save updated history to workflow
        await update_workflow(workflow_id, {
            "thread_history": thread_history
        })

        if action == 'execute':
            # Generate combined PDF with updated data (Excel + Original BO)
            logger.info(f"[BO APPROVAL] Execute action - regenerating combined PDF for {workflow_id}")
            parser = BookingOrderParser(company=workflow["company"])

            # Get the ORIGINAL uploaded BO file path from workflow (NOT the combined PDF)
            original_file_path = workflow.get("original_file_path")
            logger.info(f"[BO APPROVAL] Original file path from workflow: {original_file_path} (type: {type(original_file_path)})")

            if not original_file_path:
                logger.error(f"[BO APPROVAL] Original file path is None or empty for {workflow_id}")
                return "❌ Error: Original booking order file path not found. Please contact support."

            original_bo_path = Path(original_file_path)
            logger.info(f"[BO APPROVAL] Original BO path object: {original_bo_path}, exists: {original_bo_path.exists()}, suffix: {original_bo_path.suffix}")

            if not original_bo_path.exists():
                logger.error(f"[BO APPROVAL] Original BO file does not exist at {original_bo_path} for {workflow_id}")
                return "❌ Error: Original booking order file not found. Please contact support."

            # Generate fresh combined PDF with updated data
            logger.info(f"[BO APPROVAL] Calling generate_combined_pdf with bo_ref: DRAFT_{workflow['company']}_REGEN")
            temp_combined_pdf = await parser.generate_combined_pdf(
                current_data,
                f"DRAFT_{workflow['company']}_REGEN",
                original_bo_path
            )
            logger.info(f"[BO APPROVAL] Successfully generated combined PDF: {temp_combined_pdf}")

            # Upload combined PDF to thread
            await config.slack_client.files_upload_v2(
                channel=channel,
                thread_ts=thread_ts,
                file=str(temp_combined_pdf),
                title=f"BO Draft - {current_data.get('client', 'Unknown')} (Updated)"
            )

            # Wait for file to render before sending buttons (same as original BO flow)
            import asyncio
            await asyncio.sleep(10)

            # Send approval buttons IN THREAD
            text = f"✅ *Ready for Approval*\n\n"
            text += f"*Client:* {current_data.get('client', 'N/A')}\n"
            text += f"*Campaign:* {current_data.get('brand_campaign', 'N/A')}\n"
            text += f"*Gross Total:* AED {current_data.get('gross_calc', 0):,.2f}\n\n"
            text += "Please review the combined PDF above and approve or reject:"

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

            # Disable old buttons if they exist (prevents clicking old approve/reject after regeneration)
            old_msg_ts = workflow.get("coordinator_msg_ts")
            if old_msg_ts:
                try:
                    await config.slack_client.chat_update(
                        channel=channel,
                        ts=old_msg_ts,
                        text="⚠️ _These buttons have been superseded by new buttons below (after regeneration)_",
                        blocks=[]  # Remove blocks to disable buttons
                    )
                    logger.info(f"[BO APPROVAL] Disabled old coordinator buttons at {old_msg_ts}")
                except Exception as e:
                    logger.warning(f"[BO APPROVAL] Failed to disable old buttons: {e}")

            # Post new buttons in thread with markdown formatting
            new_button_msg = await config.slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=config.markdown_to_slack(text),
                blocks=blocks
            )

            # Update workflow with new button message timestamp
            await update_workflow(workflow_id, {
                "coordinator_msg_ts": new_button_msg["ts"]
            })

            # Don't return a message to user - file and buttons speak for themselves
            return None

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

                # Use message from LLM (which should be in natural language)
                # Fall back to generic message if no message provided
                if message:
                    return message
                else:
                    return "✅ **Changes applied!**\n\nLet me know if you need any other changes, or say 'execute' to generate the Excel and approval buttons."
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
