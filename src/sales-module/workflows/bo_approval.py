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

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import config
from db.database import db
from integrations.llm import LLMClient, LLMMessage, ReasoningEffort
from integrations.llm.prompts.bo_editing import get_coordinator_thread_prompt
from integrations.llm.schemas.bo_editing import get_coordinator_response_schema
from core.utils.time import UAE_TZ, get_uae_time
from workflows.bo_parser import BookingOrderParser

logger = logging.getLogger("proposal-bot")


def _convert_booking_order_currency(data: dict[str, Any], from_currency: str, to_currency: str) -> None:
    """Mutate booking order dict to convert monetary fields between currencies."""
    if not data or from_currency == to_currency:
        return

    amount_fields = [
        "net_pre_vat",
        "net_excl_sla_calc",
        "vat_value",
        "vat_calc",
        "gross_amount",
        "gross_calc",
        "municipality_fee",
        "production_upload_fee",
        "sla_deduction",
    ]

    for field in amount_fields:
        if field in data and data[field] is not None:
            data[field] = config.convert_currency_value(data[field], from_currency, to_currency)

    # Locations
    for location in data.get("locations", []) or []:
        if location.get("net_amount") is not None:
            location["net_amount"] = config.convert_currency_value(location["net_amount"], from_currency, to_currency)
        if location.get("post_sla_amount") is not None:
            location["post_sla_amount"] = config.convert_currency_value(location["post_sla_amount"], from_currency, to_currency)

    # Notes or other numeric strings are left untouched intentionally


def _format_amount(data: dict[str, Any], amount: float | None) -> str:
    currency = data.get("currency", config.DEFAULT_CURRENCY) if data else config.DEFAULT_CURRENCY
    return config.format_currency_value(amount, currency)


# In-memory cache for active approval workflows
approval_workflows: dict[str, dict[str, Any]] = {}


async def load_workflows_from_db():
    """
    Load all active workflows from database into memory cache.
    Called on server startup to restore state after restart.
    """
    try:
        workflows = db.get_all_active_bo_workflows()
        for workflow_id, workflow_data in workflows:
            # Supabase returns JSONB as dict, SQLite returns as JSON string
            if isinstance(workflow_data, str):
                workflow_data = json.loads(workflow_data)
            approval_workflows[workflow_id] = workflow_data
        logger.info(f"[BO APPROVAL] Loaded {len(workflows)} active workflows from database")
    except Exception as e:
        logger.error(f"[BO APPROVAL] Failed to load workflows from database: {e}")

# Config file path - use production path if /data/ exists, otherwise development
if os.path.exists("/data/"):
    CONFIG_PATH = Path("/data/hos_config.json")
else:
    CONFIG_PATH = Path(__file__).parent / "render_main_data" / "hos_config.json"


def load_stakeholders_config() -> dict[str, Any]:
    """Load stakeholders configuration"""
    try:
        with open(CONFIG_PATH) as f:
            config_data = json.load(f)
            return config_data.get("booking_order_stakeholders", {})
    except Exception as e:
        logger.error(f"[BO APPROVAL] Failed to load stakeholders config: {e}")
        return {}


def get_head_of_sales_name(company: str) -> str:
    """
    Get Head of Sales name for specific company from hos_config.json.
    Used for document signatures.
    """
    stakeholders = load_stakeholders_config()
    hos = stakeholders.get("head_of_sales", {})
    company_hos = hos.get(company, {})
    return company_hos.get("name", f"{company.title()} Head of Sales")


async def get_head_of_sales_channel(company: str) -> str | None:
    """
    Get Head of Sales DM channel ID for specific company.
    Uses conversations.open to get DM channel ID from user_id.
    """
    stakeholders = load_stakeholders_config()
    hos = stakeholders.get("head_of_sales", {})
    company_hos = hos.get(company, {})

    # Try channel_id first (if already stored), otherwise get from user_id
    channel_id = company_hos.get("channel_id")
    if channel_id:
        return channel_id

    # Get user_id and open DM conversation to get channel ID
    user_id = company_hos.get("user_id")
    if user_id:
        try:
            channel_adapter = config.get_channel_adapter()
            dm_channel_id = await channel_adapter.open_dm(user_id)
            return dm_channel_id
        except Exception as e:
            logger.error(f"[BO APPROVAL] Failed to open DM with user {user_id}: {e}")
            return None

    return None


async def get_coordinator_channel(company: str) -> str | None:
    """
    Get Sales Coordinator DM channel ID for specific company.
    Uses channel adapter to get DM channel ID from user_id.
    """
    stakeholders = load_stakeholders_config()
    coordinators = stakeholders.get("coordinators", {})
    coordinator = coordinators.get(company, {})

    # Try channel_id first (if already stored), otherwise get from user_id
    channel_id = coordinator.get("channel_id")
    if channel_id:
        return channel_id

    # Get user_id and open DM conversation to get channel ID
    user_id = coordinator.get("user_id")
    if user_id:
        try:
            channel_adapter = config.get_channel_adapter()
            dm_channel_id = await channel_adapter.open_dm(user_id)
            return dm_channel_id
        except Exception as e:
            logger.error(f"[BO APPROVAL] Failed to open DM with user {user_id}: {e}")
            return None

    return None


async def get_finance_channels() -> list[str]:
    """
    Get Finance DM channel IDs for all finance users.
    Uses channel adapter to get DM channel ID from user_id.
    Returns list of channel IDs.
    """
    stakeholders = load_stakeholders_config()
    finance_users = stakeholders.get("finance", {})

    channel_ids = []
    channel_adapter = config.get_channel_adapter()

    # Iterate through all finance users
    for finance_name, finance_info in finance_users.items():
        user_id = finance_info.get("user_id")
        if user_id:
            try:
                dm_channel_id = await channel_adapter.open_dm(user_id)
                if dm_channel_id:
                    channel_ids.append(dm_channel_id)
                    logger.info(f"[BO APPROVAL] Got finance channel for {finance_name}: {dm_channel_id}")
            except Exception as e:
                logger.error(f"[BO APPROVAL] Failed to open DM with finance user {finance_name} ({user_id}): {e}")

    return channel_ids


def create_workflow_id(company: str) -> str:
    """Create unique workflow ID"""
    timestamp = datetime.now().timestamp()
    return f"bo_approval_{company}_{int(timestamp)}"


async def create_approval_workflow(
    user_id: str,
    company: str,
    data: dict[str, Any],
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
    import shutil

    from integrations.storage import store_bo_file
    from workflows.bo_parser import ORIGINAL_BOS_DIR

    workflow_id = create_workflow_id(company)

    # Copy original file to permanent storage (prevents loss if temp files are cleaned up)
    # This ensures the original BO is preserved throughout the entire workflow lifecycle
    permanent_original_path = ORIGINAL_BOS_DIR / f"{workflow_id}_{original_filename}"
    original_file_size = None
    original_file_id = None
    try:
        shutil.copy2(original_file_path, permanent_original_path)
        original_file_size = permanent_original_path.stat().st_size
        logger.info(f"[BO APPROVAL] Copied original BO to permanent storage: {permanent_original_path}")

        # Track in storage system (creates DB record with hash)
        # Note: We use a placeholder bo_id of 0 since the actual BO isn't saved yet
        # This will be updated when the BO is finalized
        tracked = await store_bo_file(
            data=permanent_original_path,
            filename=original_filename,
            bo_id=0,  # Placeholder - will be associated with actual BO after approval
            user_id=user_id,
            file_type="original_bo",
        )
        if tracked.success:
            original_file_id = tracked.file_id
            logger.info(f"[BO APPROVAL] Tracked original BO in storage system: {tracked.file_id}")
        else:
            logger.warning(f"[BO APPROVAL] Failed to track in storage system: {tracked.error}")

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
        "original_file_size": original_file_size,
        "original_file_id": original_file_id,  # Storage system file_id for tracking
        "file_type": file_type,
        "user_notes": user_notes,
        "stage": "coordinator",  # Current stage: coordinator, hos, finance
        "status": "pending",  # pending, approved, rejected
        "created_at": get_uae_time().isoformat(),

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
        "saved_to_db": False,

        # Storage tracking
        "combined_pdf_file_id": None,  # Set when combined PDF is generated
    }

    # Cache and persist
    approval_workflows[workflow_id] = workflow_data
    await save_workflow_to_db(workflow_id, workflow_data)

    logger.info(f"[BO APPROVAL] Created workflow {workflow_id} for {company}")
    return workflow_id


async def save_workflow_to_db(workflow_id: str, workflow_data: dict[str, Any]):
    """Persist workflow to database"""
    try:
        db.save_bo_workflow(
            workflow_id=workflow_id,
            workflow_data=json.dumps(workflow_data),
            updated_at=get_uae_time().isoformat()
        )
    except Exception as e:
        logger.error(f"[BO APPROVAL] Failed to save workflow {workflow_id}: {e}")


async def get_workflow_from_db(workflow_id: str) -> dict[str, Any] | None:
    """Retrieve workflow from database"""
    try:
        workflow_json = db.get_bo_workflow(workflow_id)
        if workflow_json:
            return json.loads(workflow_json)
        return None
    except Exception as e:
        logger.error(f"[BO APPROVAL] Failed to retrieve workflow {workflow_id}: {e}")
        return None


async def get_workflow_with_cache(workflow_id: str) -> dict[str, Any] | None:
    """Get workflow from cache or database"""
    # Check cache first
    if workflow_id in approval_workflows:
        return approval_workflows[workflow_id]

    # Load from database and cache
    workflow = await get_workflow_from_db(workflow_id)
    if workflow:
        approval_workflows[workflow_id] = workflow
    return workflow


async def update_workflow(workflow_id: str, updates: dict[str, Any]):
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


def is_coordinator_thread_active(workflow: dict[str, Any], thread_ts: str) -> bool:
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
    from pathlib import Path

    from core import bo_messaging

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        logger.error(f"[BO APPROVAL] Workflow {workflow_id} not found")
        return

    # Prevent double-approval (e.g., clicking old button after new one was generated)
    if workflow.get("coordinator_approved"):
        logger.warning(f"[BO APPROVAL] Workflow {workflow_id} already approved by coordinator - ignoring duplicate approval")
        await bo_messaging.post_response_url(response_url, {
            "replace_original": False,
            "text": "⚠️ This booking order has already been approved and sent to Head of Sales."
        })
        return

    workflow_data = workflow.get("data", {})
    logger.info(
        f"[BO APPROVAL] ✅ Coordinator {user_id} approved {workflow_id} - "
        f"Client: {workflow_data.get('client', 'N/A')}, Gross: {_format_amount(workflow_data, workflow_data.get('gross_calc'))}"
    )

    # IMMEDIATELY mark as approved to prevent duplicate button presses during the wait period
    await update_workflow(workflow_id, {
        "coordinator_approved": True,
        "coordinator_approved_by": user_id,
        "coordinator_approved_at": get_uae_time().isoformat(),
        "stage": "hos",
        "status": "pending"
    })

    # Update button message to show approval is being processed
    coordinator_msg_ts = workflow.get("coordinator_msg_ts")
    coordinator_channel = workflow.get("coordinator_thread_channel")

    if coordinator_msg_ts and coordinator_channel:
        approver_name = await bo_messaging.get_user_real_name(user_id)
        await bo_messaging.update_button_message(
            channel=coordinator_channel,
            message_ts=coordinator_msg_ts,
            new_text=f"✅ *APPROVED* by {approver_name}\n\n⏳ Waiting for file upload to complete...",
            approved=True
        )

    # IMPORTANT: Wait 5 seconds for file upload to complete before proceeding
    logger.info("[BO APPROVAL] Waiting 5 seconds for file upload to complete...")
    await asyncio.sleep(5)

    # Notify sales person who submitted (in their main DM, not thread)
    sales_user_id = workflow.get("sales_user_id")
    if sales_user_id:
        channel_adapter = config.get_channel_adapter()
        await channel_adapter.send_message(
            channel_id=sales_user_id,
            content=(
                f"✅ *Approved by {approver_name}*\n\n"
                f"Your booking order for **{workflow_data.get('client', 'N/A')}** has been approved by the Sales Coordinator "
                f"and is now moving to Head of Sales for review."
            )
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
    result = await bo_messaging.send_to_head_of_sales(
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

    # Update coordinator button message to show it was successfully sent to HoS
    if coordinator_msg_ts and coordinator_channel:
        await bo_messaging.update_button_message(
            channel=coordinator_channel,
            message_ts=coordinator_msg_ts,
            new_text=f"✅ *APPROVED* by {approver_name}\n\n✅ Successfully sent to Head of Sales for review",
            approved=True
        )

    logger.info(f"[BO APPROVAL] Sent {workflow_id} to Head of Sales")


async def handle_coordinator_rejection(workflow_id: str, user_id: str, response_url: str, rejection_reason: str, channel: str, message_ts: str):
    """
    Handle Sales Coordinator rejection
    - Create thread on the button message for editing
    - Allow coordinator to make natural language edits
    """
    from core import bo_messaging

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        return

    workflow_data = workflow.get("data", {})

    # Prevent duplicate rejection (clicking button multiple times)
    if workflow.get("status") == "coordinator_rejected":
        logger.warning(f"[BO APPROVAL] Workflow {workflow_id} already rejected by coordinator - ignoring duplicate")
        await bo_messaging.post_response_url(response_url, {
            "replace_original": False,
            "text": "⚠️ This booking order has already been rejected. Please use the thread to make edits."
        })
        return

    workflow_data = workflow.get("data", {})
    logger.info(f"[BO APPROVAL] ❌ Coordinator {user_id} rejected {workflow_id} - Client: {workflow_data.get('client', 'N/A')} - Reason: {rejection_reason[:100]}")

    # Update workflow
    await update_workflow(workflow_id, {
        "status": "coordinator_rejected",
        "coordinator_rejection_reason": rejection_reason,
        "coordinator_rejected_by": user_id,
        "coordinator_rejected_at": get_uae_time().isoformat(),
        "coordinator_thread_ts": message_ts,  # Use button message as thread root
        "coordinator_thread_channel": channel
    })

    # Update the button message to show rejection
    rejecter_name = await bo_messaging.get_user_real_name(user_id)
    await bo_messaging.update_button_message(
        channel=channel,
        message_ts=message_ts,
        new_text=f"❌ *REJECTED* by {rejecter_name}",
        approved=False
    )

    # Post rejection message in thread with edit instructions
    channel_adapter = config.get_channel_adapter()
    await channel_adapter.send_message(
        channel_id=channel,
        thread_id=message_ts,
        content=(
            f"❌ **Booking Order Rejected**\n\n"
            f"**Reason:** {rejection_reason}\n\n"
            f"**Current Details:**\n"
            f"• Client: {workflow_data.get('client', 'N/A')}\n"
            f"• Campaign: {workflow_data.get('brand_campaign', 'N/A')}\n"
            f"• Gross Total: {_format_amount(workflow_data, workflow_data.get('gross_calc'))}\n\n"
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
    from pathlib import Path

    from core import bo_messaging

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        return

    # Prevent double-approval
    if workflow.get("hos_approved"):
        logger.warning(f"[BO APPROVAL] Workflow {workflow_id} already approved by HoS - ignoring duplicate approval")
        await bo_messaging.post_response_url(response_url, {
            "replace_original": False,
            "text": "⚠️ This booking order has already been approved and saved to the database."
        })
        return

    workflow_data = workflow.get("data", {})

    logger.info(
        f"[BO APPROVAL] ✅ Head of Sales {user_id} approved {workflow_id} - "
        f"Client: {workflow_data.get('client', 'N/A')}, Gross: {_format_amount(workflow_data, workflow_data.get('gross_calc'))}"
    )

    # IMMEDIATELY mark as approved to prevent duplicate button presses during processing
    await update_workflow(workflow_id, {
        "hos_approved": True,
        "hos_approved_by": user_id,
        "hos_approved_at": get_uae_time().isoformat()
    })

    # Generate final BO reference
    bo_ref = db.generate_next_bo_ref()

    # Get HoS name for signature from hos_config (not the user's Slack name)
    hos_name = get_head_of_sales_name(workflow["company"])
    logger.info(f"[BO APPROVAL] Adding HoS signature for {workflow['company']}: {hos_name}")

    # Add HoS signature to data (will be added to Excel in italics)
    workflow_data["hos_signature"] = hos_name

    # Generate final combined PDF (Excel + Original BO) with HoS signature and stamp
    parser = BookingOrderParser(company=workflow["company"])
    permanent_original_path = Path(workflow["original_file_path"])
    final_combined_pdf = await parser.generate_combined_pdf(
        workflow_data,
        bo_ref,
        permanent_original_path,
        apply_stamp=True  # Apply HoS approval stamp
    )

    # Track combined PDF in storage system
    combined_pdf_file_id = None
    try:
        from integrations.storage import soft_delete_tracked_file, store_bo_file

        # Store combined PDF
        tracked = await store_bo_file(
            data=final_combined_pdf,
            filename=f"{bo_ref}_combined.pdf",
            bo_id=0,  # Placeholder - BO record created after this
            user_id=workflow.get("sales_user_id"),
            file_type="combined_bo_pdf",
        )
        if tracked.success:
            combined_pdf_file_id = tracked.file_id
            logger.info(f"[BO APPROVAL] Tracked combined PDF in storage: {tracked.file_id}")

        # Soft-delete original BO from storage (keep for audit trail)
        if workflow.get("original_file_id"):
            await soft_delete_tracked_file(workflow["original_file_id"])
            logger.info(f"[BO APPROVAL] Soft-deleted original BO from storage: {workflow['original_file_id']}")

    except Exception as e:
        logger.warning(f"[BO APPROVAL] Failed to track combined PDF in storage: {e}")

    # Clean up permanent original file (we now have the final combined PDF)
    if permanent_original_path.exists():
        try:
            permanent_original_path.unlink()
            logger.info(f"[BO APPROVAL] Cleaned up original BO file: {permanent_original_path}")
        except Exception as e:
            logger.warning(f"[BO APPROVAL] Failed to clean up original BO file: {e}")

    # Save to permanent database
    # Prepare data dictionary for database
    db_data = {
        "bo_ref": bo_ref,
        "company": workflow["company"],
        "original_file_path": str(final_combined_pdf),  # Now stores combined PDF path
        "original_file_type": workflow["file_type"],
        "original_file_size": workflow.get("original_file_size"),
        "original_filename": workflow.get("original_filename"),
        "parsed_excel_path": str(final_combined_pdf),  # Same file for both (backwards compatibility)
        "warnings": workflow["warnings"],
        "missing_required": workflow["missing_required"],
        "user_notes": workflow.get("user_notes", ""),
        "combined_pdf_file_id": combined_pdf_file_id,  # Storage system file_id
        # Copy all fields from workflow["data"]
        **workflow["data"]
    }
    # Run synchronous DB operation in thread pool to avoid blocking event loop
    await asyncio.to_thread(db.save_booking_order, db_data)

    # Update workflow with remaining fields (hos_approved already set above)
    await update_workflow(workflow_id, {
        "stage": "finance",
        "status": "approved",
        "bo_ref": bo_ref,
        "saved_to_db": True
    })

    # Get bo_number for user-facing messages
    bo_number = workflow["data"].get("bo_number", "N/A")

    # Update HoS button message (use bo_number for user-facing display)
    if workflow.get("hos_msg_ts") and workflow.get("hos_channel"):
        await bo_messaging.update_button_message(
            channel=workflow.get("hos_channel"),
            message_ts=workflow.get("hos_msg_ts"),
            new_text=f"✅ *APPROVED BY HEAD OF SALES*\nBO Number: {bo_number}\nNotifying Finance...",
            approved=True
        )

    # Notify finance (uses conversations.open to get DM channel IDs for all finance users)
    finance_channels = await get_finance_channels()
    if finance_channels:
        # Send to all finance users
        for finance_channel in finance_channels:
            result = await bo_messaging.notify_finance(
                channel=finance_channel,
                bo_ref=bo_ref,
                company=workflow["company"],
                data=workflow["data"],
                excel_path=str(final_combined_pdf)
            )

        # Update workflow after sending to all finance users
        await update_workflow(workflow_id, {
            "finance_notified": True,
            "finance_notified_at": get_uae_time().isoformat(),
            "finance_msg_ts": result["message_id"]  # Store last message ID
        })

        # Update HoS button message to show finance was notified
        if workflow.get("hos_msg_ts") and workflow.get("hos_channel"):
            await bo_messaging.update_button_message(
                channel=workflow.get("hos_channel"),
                message_ts=workflow.get("hos_msg_ts"),
                new_text=f"✅ *APPROVED BY HEAD OF SALES*\nBO Number: {bo_number}\n✅ Finance notified successfully ({len(finance_channels)} recipients)",
                approved=True
            )

    # Notify sales person who submitted
    channel_adapter = config.get_channel_adapter()
    await channel_adapter.send_message(
        channel_id=workflow["sales_user_id"],
        content=(
            f"✅ **Booking Order Approved & Finalized**\n\n"
            f"**BO Number:** {bo_number}\n"
            f"**Client:** {workflow_data.get('client', 'N/A')}\n"
            f"**Gross Total:** {_format_amount(workflow_data, workflow_data.get('gross_calc'))}\n\n"
            f"The booking order has been approved by all stakeholders and saved to the database."
        )
    )

    # Close coordinator thread with success message
    coordinator_thread = workflow.get("coordinator_thread_ts")
    coordinator_channel = workflow.get("coordinator_thread_channel")

    if coordinator_thread and coordinator_channel:
        await channel_adapter.send_message(
            channel_id=coordinator_channel,
            thread_id=coordinator_thread,
            content=(
                f"✅ *APPROVED BY HEAD OF SALES*\n\n"
                f"**BO Number:** {bo_number}\n"
                f"This booking order has been finalized and sent to Finance."
            )
        )

    logger.info(
        f"[BO APPROVAL] ✅ COMPLETE - BO Reference: {bo_ref} - "
        f"Client: {workflow_data.get('client', 'N/A')}, Gross: {_format_amount(workflow_data, workflow_data.get('gross_calc'))} - Workflow: {workflow_id}"
    )


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

    # Prevent duplicate rejection (clicking button multiple times)
    if workflow.get("status") == "coordinator_rejected":
        logger.warning(f"[BO APPROVAL] Workflow {workflow_id} already rejected by HoS - ignoring duplicate")
        from core import bo_messaging
        await bo_messaging.post_response_url(response_url, {
            "replace_original": False,
            "text": "⚠️ This booking order has already been rejected and sent back to the coordinator."
        })
        return

    workflow_data = workflow.get("data", {})
    logger.info(f"[BO APPROVAL] ❌ Head of Sales {user_id} rejected {workflow_id} - Client: {workflow_data.get('client', 'N/A')} - Reason: {rejection_reason[:100]}")

    # Update HoS button message to show rejection
    from core import bo_messaging
    hos_msg_ts = workflow.get("hos_msg_ts")
    hos_channel = workflow.get("hos_channel")
    if hos_msg_ts and hos_channel:
        rejecter_name = await bo_messaging.get_user_real_name(user_id)
        await bo_messaging.update_button_message(
            channel=hos_channel,
            message_ts=hos_msg_ts,
            new_text=f"Rejected by {rejecter_name}\n\n**Reason:** {rejection_reason}\n\nReturned to Sales Coordinator for amendments.",
            approved=False
        )

    # Update workflow - move back to coordinator stage
    await update_workflow(workflow_id, {
        "status": "coordinator_rejected",  # Reactivate coordinator thread for editing
        "stage": "coordinator",  # Move back to coordinator
        "hos_rejection_reason": rejection_reason,
        "hos_rejected_by": user_id,
        "hos_rejected_at": get_uae_time().isoformat(),
        "hos_approved": False,  # Clear HoS approval
        "coordinator_approved": False  # Clear coordinator approval (they need to re-approve)
    })

    # REVIVE coordinator thread with rejection
    coordinator_thread = workflow.get("coordinator_thread_ts")
    coordinator_channel = workflow.get("coordinator_thread_channel")

    if coordinator_thread and coordinator_channel:
        channel_adapter = config.get_channel_adapter()
        await channel_adapter.send_message(
            channel_id=coordinator_channel,
            thread_id=coordinator_thread,
            content=(
                f"❌ **REJECTED BY HEAD OF SALES**\n\n"
                f"**Reason:** {rejection_reason}\n\n"
                f"**Current Details:**\n"
                f"• Client: {workflow_data.get('client', 'N/A')}\n"
                f"• Campaign: {workflow_data.get('brand_campaign', 'N/A')}\n"
                f"• Gross Total: {_format_amount(workflow_data, workflow_data.get('gross_calc'))}\n\n"
                f"Please make the necessary amendments. Tell me what changes are needed, or say 'execute' when ready to resubmit."
            )
        )
        logger.info(f"[BO APPROVAL] Revived coordinator thread {coordinator_thread} with HoS rejection")
    else:
        logger.error(f"[BO APPROVAL] No coordinator thread found to revive for {workflow_id}")

    # Notify sales person
    channel_adapter = config.get_channel_adapter()
    await channel_adapter.send_message(
        channel_id=workflow["sales_user_id"],
        content=(
            f"❌ **Booking Order Rejected by Head of Sales**\n\n"
            f"**Reason:** {rejection_reason}\n\n"
            f"The Sales Coordinator will make the necessary amendments and resubmit."
        )
    )


# =========================
# THREAD-BASED COORDINATOR FLOW
# =========================

async def start_revision_workflow(
    bo_data: dict[str, Any],
    requester_user_id: str,
    requester_channel: str
) -> dict[str, Any]:
    """
    Start a revision workflow for an existing booking order (ADMIN ONLY)

    - Fetches existing BO data from database
    - Creates NEW workflow with revision flag
    - Sends to coordinator with NEW thread (not reusing original)
    - Full approval flow: Coordinator → HoS → Finance
    - If rejected at any stage, sends back to previous stage

    Args:
        bo_data: Dictionary containing existing booking order data from database
        requester_user_id: User ID of admin requesting revision
        requester_channel: Channel where admin made request

    Returns:
        Dictionary with workflow_id and status
    """
    from pathlib import Path

    from core import bo_messaging

    logger.info(f"[BO_REVISE] Starting revision workflow for BO: {bo_data.get('bo_ref')} requested by {requester_user_id}")

    company = bo_data.get("company")
    if not company:
        logger.error("[BO_REVISE] No company found in BO data")
        return {"success": False, "error": "Company not specified in booking order"}

    # Create new workflow for revision (similar to new BO but marked as revision)
    workflow_id = create_workflow_id(company)

    # Extract relevant data for workflow (matching structure of create_approval_workflow)
    workflow_data = {
        "workflow_id": workflow_id,
        "sales_user_id": requester_user_id,  # Admin who requested revision
        "company": company,
        "data": {
            # Copy all booking order fields
            "client": bo_data.get("client"),
            "brand_campaign": bo_data.get("brand_campaign"),
            "bo_number": bo_data.get("bo_number"),
            "bo_date": bo_data.get("bo_date"),
            "net_pre_vat": bo_data.get("net_pre_vat"),
            "vat_calc": bo_data.get("vat_calc"),
            "gross_calc": bo_data.get("gross_calc"),
            "agency": bo_data.get("agency"),
            "sales_person": bo_data.get("sales_person"),
            "sla_pct": bo_data.get("sla_pct"),
            "payment_terms": bo_data.get("payment_terms"),
            "commission_pct": bo_data.get("commission_pct"),
            "notes": bo_data.get("notes"),
            "category": bo_data.get("category"),
            "municipality_fee": bo_data.get("municipality_fee"),
            "production_upload_fee": bo_data.get("production_upload_fee"),
            "asset": bo_data.get("asset"),
            "locations": bo_data.get("locations", []),
            "tenure": bo_data.get("tenure"),
        },
        "warnings": bo_data.get("warnings", []),
        "missing_required": bo_data.get("missing_required", []),
        "original_file_path": bo_data.get("original_file_path", ""),
        "original_filename": bo_data.get("original_filename", ""),
        "file_type": bo_data.get("original_file_type", "pdf"),
        "user_notes": f"REVISION of {bo_data.get('bo_ref')}",
        "stage": "coordinator",
        "status": "pending",
        "created_at": get_uae_time().isoformat(),
        "is_revision": True,  # Mark as revision
        "original_bo_ref": bo_data.get("bo_ref"),  # Track original BO reference

        # Stage-specific data
        "coordinator_thread_ts": None,
        "coordinator_thread_channel": None,
        "coordinator_approved": False,
        "coordinator_approved_by": None,
        "coordinator_approved_at": None,
        "coordinator_msg_ts": None,

        "hos_approved": False,
        "hos_approved_by": None,
        "hos_approved_at": None,
        "hos_msg_ts": None,
        "hos_rejection_reason": None,

        "finance_notified": False,
        "finance_notified_at": None,
        "finance_msg_ts": None,

        "bo_ref": None,
        "saved_to_db": False
    }

    # Cache and persist
    approval_workflows[workflow_id] = workflow_data
    await save_workflow_to_db(workflow_id, workflow_data)

    logger.info(f"[BO_REVISE] Created revision workflow {workflow_id} for {company}")

    # Get coordinator channel
    coordinator_channel = await get_coordinator_channel(company)
    if not coordinator_channel:
        logger.error(f"[BO_REVISE] No coordinator configured for {company}")
        return {"success": False, "error": f"No coordinator configured for {company}"}

    # Send to coordinator with NEW thread (indicating this is a revision)
    try:
        # Generate combined PDF for coordinator review
        parser = BookingOrderParser(company=company)
        original_bo_path = Path(bo_data.get("original_file_path", ""))

        # If original file doesn't exist, we'll create Excel-only PDF
        if not original_bo_path.exists():
            logger.warning(f"[BO_REVISE] Original BO file not found at {original_bo_path}, will generate Excel-only PDF")
            # Generate Excel-only PDF
            temp_combined_pdf = await parser.generate_combined_pdf(
                workflow_data["data"],
                f"REVISION_{workflow_id}",
                None  # No original BO to attach
            )
        else:
            # Generate combined PDF with original BO
            temp_combined_pdf = await parser.generate_combined_pdf(
                workflow_data["data"],
                f"REVISION_{workflow_id}",
                original_bo_path
            )

        # Send to coordinator
        result = await bo_messaging.send_to_coordinator(
            channel=coordinator_channel,
            workflow_id=workflow_id,
            company=company,
            data=workflow_data["data"],
            warnings=workflow_data["warnings"],
            missing_required=workflow_data["missing_required"],
            combined_pdf_path=str(temp_combined_pdf),
            is_revision=True,  # Flag to indicate this is a revision
            original_bo_ref=bo_data.get("bo_ref"),
            user_notes=workflow_data.get("user_notes", "")
        )

        # Update workflow with coordinator message info
        await update_workflow(workflow_id, {
            "coordinator_msg_ts": result["message_id"],
            "coordinator_thread_channel": result["channel"],
            "coordinator_thread_ts": result["message_id"]  # Use message as thread root
        })

        # Notify admin that revision workflow started
        channel_adapter = config.get_channel_adapter()
        await channel_adapter.send_message(
            channel_id=requester_channel,
            content=(
                f"✅ **Revision Workflow Started**\n\n"
                f"**Original BO:** {bo_data.get('bo_ref')}\n"
                f"**Client:** {bo_data.get('client')}\n"
                f"**Workflow ID:** {workflow_id}\n\n"
                f"The booking order has been sent to the Sales Coordinator for revision."
            )
        )

        logger.info(f"[BO_REVISE] Successfully started revision workflow {workflow_id} for BO {bo_data.get('bo_ref')}")

        return {
            "success": True,
            "workflow_id": workflow_id,
            "coordinator_channel": coordinator_channel
        }

    except Exception as e:
        logger.error(f"[BO_REVISE] Failed to start revision workflow: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def handle_bo_cancellation(
    workflow_id: str,
    cancelled_by_user_id: str,
    cancellation_reason: str,
    stage: str  # "coordinator" or "hos"
):
    """
    Handle booking order cancellation from coordinator or HoS
    - Update button messages to show cancellation
    - Notify original sales person who submitted
    - Clean up workflow from database
    - Delete workflow state
    """
    from core import bo_messaging

    workflow = await get_workflow_with_cache(workflow_id)
    if not workflow:
        logger.error(f"[BO CANCEL] Workflow {workflow_id} not found")
        return

    logger.info(f"[BO CANCEL] Cancelling workflow {workflow_id} at {stage} stage by {cancelled_by_user_id}")

    # Get canceller name
    canceller_name = await bo_messaging.get_user_real_name(cancelled_by_user_id)

    # Update the button message to show cancellation
    if stage == "coordinator":
        msg_ts = workflow.get("coordinator_msg_ts")
        channel = workflow.get("coordinator_thread_channel")
        if msg_ts and channel:
            await bo_messaging.update_button_message(
                channel=channel,
                message_ts=msg_ts,
                new_text=f"🚫 *CANCELLED* by {canceller_name}\n\n**Reason:** {cancellation_reason}",
                approved=False
            )
    elif stage == "hos":
        msg_ts = workflow.get("hos_msg_ts")
        channel = workflow.get("hos_channel")
        if msg_ts and channel:
            await bo_messaging.update_button_message(
                channel=channel,
                message_ts=msg_ts,
                new_text=f"�� *CANCELLED* by {canceller_name}\n\n**Reason:** {cancellation_reason}",
                approved=False
            )

    # Notify original sales person who submitted the BO
    sales_user_id = workflow.get("sales_user_id")
    if sales_user_id:
        channel_adapter = config.get_channel_adapter()
        await channel_adapter.send_message(
            channel_id=sales_user_id,
            content=(
                f"🚫 **Booking Order Cancelled**\n\n"
                f"**Client:** {workflow['data'].get('client', 'N/A')}\n"
                f"**Campaign:** {workflow['data'].get('brand_campaign', 'N/A')}\n"
                f"**Cancelled by:** {canceller_name} ({stage.upper()})\n"
                f"**Reason:** {cancellation_reason}\n\n"
                f"The booking order workflow has been cancelled and removed from the system."
            )
        )

    # Clean up workflow from database
    try:
        db.delete_bo_workflow(workflow_id)
        logger.info(f"[BO CANCEL] Deleted workflow {workflow_id} from database")
    except Exception as e:
        logger.error(f"[BO CANCEL] Failed to delete workflow {workflow_id} from database: {e}")

    # Delete workflow state from memory
    if workflow_id in approval_workflows:
        del approval_workflows[workflow_id]
        logger.info(f"[BO CANCEL] Removed workflow {workflow_id} from memory cache")

    logger.info(f"[BO CANCEL] Successfully cancelled workflow {workflow_id}")


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
    current_currency = current_data.get("currency", config.DEFAULT_CURRENCY)
    currency_context = config.CURRENCY_PROMPT_CONTEXT

    system_prompt = get_coordinator_thread_prompt(
        current_currency=current_currency,
        currency_context=currency_context,
        current_data=current_data,
        warnings=warnings,
        missing_required=missing_required
    )

    try:
        # Build messages with thread history + current user message
        messages = [LLMMessage.system(system_prompt)]

        # Add thread history (last 20 messages to keep context manageable)
        for msg in thread_history[-20:]:
            if msg["role"] == "user":
                messages.append(LLMMessage.user(msg["content"]))
            else:
                messages.append(LLMMessage.assistant(msg["content"]))

        # Add current user message
        messages.append(LLMMessage.user(user_input))

        # Use LLMClient for abstracted LLM access
        llm_client = LLMClient.from_config()

        response = await llm_client.complete(
            messages=messages,
            json_schema=get_coordinator_response_schema(),
            reasoning=ReasoningEffort.LOW,
            store=config.IS_DEVELOPMENT,  # Store in OpenAI only in dev mode
            # Prompt caching: coordinator thread system prompt is static
            cache_key="coordinator-thread",
            cache_retention="24h",
            call_type="coordinator_thread",
            workflow="bo_editing",
            user_id=user_id,
            context=f"Workflow: {workflow_id}",
            metadata={"workflow_id": workflow_id, "thread_length": len(thread_history)}
        )

        decision = json.loads(response.content)
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
            channel_adapter = config.get_channel_adapter()
            await channel_adapter.upload_file(
                channel_id=channel,
                file_path=str(temp_combined_pdf),
                title=f"BO Draft - {current_data.get('client', 'Unknown')} (Updated)",
                thread_id=thread_ts
            )

            # Wait for file to render before sending buttons (same as original BO flow)
            import asyncio
            await asyncio.sleep(10)

            # Send approval buttons IN THREAD
            text = (
                f"✅ **Ready for Approval**\n\n"
                f"**Client:** {current_data.get('client', 'N/A')}\n"
                f"**Campaign:** {current_data.get('brand_campaign', 'N/A')}\n"
                f"**Gross Total:** {_format_amount(current_data, current_data.get('gross_calc'))}\n\n"
                f"Please review the combined PDF above and approve or reject:"
            )

            from integrations.channels import Button, ButtonStyle
            buttons = [
                Button(
                    text="✅ Approve",
                    action_id="approve_bo_coordinator",
                    value=workflow_id,
                    style=ButtonStyle.PRIMARY
                ),
                Button(
                    text="❌ Reject",
                    action_id="reject_bo_coordinator",
                    value=workflow_id,
                    style=ButtonStyle.DANGER
                )
            ]

            # Post new buttons in thread with markdown formatting
            new_button_msg = await channel_adapter.send_message(
                channel_id=channel,
                content=text,
                buttons=buttons,
                thread_id=thread_ts
            )

            # Update workflow with new button message timestamp and close thread for editing
            # Note: Old buttons were already replaced during rejection, no need to supersede
            await update_workflow(workflow_id, {
                "coordinator_msg_ts": new_button_msg.id,
                "status": "pending"  # Close thread - user must click reject again to make more edits
            })

            # Don't return a message to user - file and buttons speak for themselves
            return None

        elif action == 'edit':
            # Apply field updates
            fields = decision.get('fields', {})
            currency_changed = False
            currency_value = None

            if fields:
                if 'currency' in fields and fields['currency']:
                    currency_value = str(fields.pop('currency')).upper()
                    currency_value = currency_value.strip()
                    if currency_value:
                        previous_currency = current_data.get('currency', config.DEFAULT_CURRENCY)
                        if currency_value != previous_currency:
                            _convert_booking_order_currency(current_data, previous_currency, currency_value)
                            current_data['currency'] = currency_value
                            currency_changed = True
                            logger.info(
                                f"[BO APPROVAL] Converted amounts from {previous_currency} to {currency_value} for {workflow_id}"
                            )
                        else:
                            # No actual change, ensure canonical format
                            current_data['currency'] = previous_currency

                remaining_fields = fields
                if remaining_fields:
                    logger.info(
                        f"[BO APPROVAL] Coordinator editing {len(remaining_fields)} fields in {workflow_id}: {list(remaining_fields.keys())}"
                    )
                    for field, value in remaining_fields.items():
                        current_data[field] = value

                # Intelligent recalculation logic
                needs_recalc = currency_changed

                if any(key in remaining_fields for key in ['locations', 'municipality_fee', 'production_upload_fee']):
                    needs_recalc = True

                    locations_total = sum(
                        loc.get('net_amount', 0)
                        for loc in current_data.get('locations', [])
                    )
                    municipality_fee = current_data.get('municipality_fee', 0) or 0
                    production_upload_fee = current_data.get('production_upload_fee', 0) or 0

                    current_data['net_pre_vat'] = round(
                        locations_total + municipality_fee + production_upload_fee,
                        2
                    )
                    logger.info(
                        f"[BO APPROVAL] Recalculated net_pre_vat = {current_data['net_pre_vat']} "
                        f"(locations: {locations_total}, fees: {municipality_fee + production_upload_fee})"
                    )

                if 'net_pre_vat' in remaining_fields or needs_recalc:
                    net = current_data.get('net_pre_vat', 0) or 0
                    sla_pct = current_data.get('sla_pct', 0) or 0

                    current_data['vat_calc'] = round(net * 0.05, 2)
                    current_data['gross_calc'] = round(net + current_data['vat_calc'], 2)

                    if sla_pct > 0:
                        current_data['sla_deduction'] = round(net * sla_pct, 2)
                        current_data['net_excl_sla_calc'] = round(net - current_data['sla_deduction'], 2)

                    logger.info(
                        f"[BO APPROVAL] Recalculated totals: VAT={current_data['vat_calc']}, "
                        f"Gross={current_data['gross_calc']}, SLA={current_data.get('sla_deduction', 0)}"
                    )

                if 'sla_pct' in remaining_fields:
                    net = current_data.get('net_pre_vat', 0) or 0
                    sla_pct = current_data.get('sla_pct', 0) or 0
                    current_data['sla_deduction'] = round(net * sla_pct, 2)
                    current_data['net_excl_sla_calc'] = round(net - current_data['sla_deduction'], 2)
                    logger.info(
                        f"[BO APPROVAL] Recalculated SLA: deduction={current_data['sla_deduction']}, "
                        f"net_excl_sla={current_data['net_excl_sla_calc']}"
                    )

                await update_workflow(workflow_id, {
                    "data": current_data
                })

                if message:
                    return message

                if currency_changed and not remaining_fields:
                    display_currency = current_data.get('currency', config.DEFAULT_CURRENCY)
                    return (
                        f"✅ **All amounts converted to {display_currency}.**\n\n"
                        "Let me know if you need any other updates, or say 'execute' when you're ready."
                    )

                return "✅ **Changes applied!**\n\nLet me know if you need any other changes, or say 'execute' to generate the Excel and approval buttons."
            else:
                if currency_value and currency_changed:
                    display_currency = current_data.get('currency', config.DEFAULT_CURRENCY)
                    await update_workflow(workflow_id, {
                        "data": current_data
                    })
                    return (
                        f"✅ **All amounts converted to {display_currency}.**\n\n"
                        "Let me know if you need any other updates, or say 'execute' when you're ready."
                    )

                return message or "I didn't catch any changes. What would you like to update?"

        elif action == 'view':
            # Show current draft
            preview = "📋 **Current Booking Order Details**\n\n"
            preview += f"**Client:** {current_data.get('client', 'N/A')}\n"
            preview += f"**Campaign:** {current_data.get('brand_campaign', 'N/A')}\n"
            preview += f"**BO Number:** {current_data.get('bo_number', 'N/A')}\n"
            preview += f"**BO Date:** {current_data.get('bo_date', 'N/A')}\n"
            preview += f"**Net (pre-VAT):** {_format_amount(current_data, current_data.get('net_pre_vat'))}\n"
            preview += f"**VAT (5%):** {_format_amount(current_data, current_data.get('vat_calc'))}\n"
            preview += f"**Gross Total:** {_format_amount(current_data, current_data.get('gross_calc'))}\n"
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
        logger.error(f"[BO APPROVAL] Error in coordinator thread: {e}", exc_info=True)
        return f"❌ **Error processing your request:** {str(e)}\n\nPlease try again."
