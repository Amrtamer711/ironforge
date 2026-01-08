import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import config
from core import bo_messaging
from core.utils.file_utils import _convert_pdf_to_pptx, _validate_pdf_file, download_file
from core.tools import get_admin_tools, get_base_tools
from db.cache import (
    get_mockup_history,
    pending_booking_orders,
    pending_location_additions,
    user_history,
)
from integrations.channels import ChannelType
from integrations.llm.prompts.bo_editing import get_bo_edit_prompt
from integrations.llm.prompts.chat import get_main_system_prompt
from integrations.llm.schemas.bo_editing import get_bo_edit_response_schema
from core.utils.task_queue import mockup_queue
from workflows.bo_parser import BookingOrderParser
from core.workflow_context import WorkflowContext


async def _generate_mockup_queued(
    location_key: str,
    creative_paths: list,
    time_of_day: str,
    side: str,
    specific_photo: str = None,
    config_override: dict = None,
    company_schemas: list = None,
    company_hint: str = None,
):
    """
    Wrapper function for mockup generation that runs through the task queue.
    This limits concurrent mockup generation to prevent memory exhaustion.

    Args:
        location_key: Location identifier
        creative_paths: List of creative file paths
        time_of_day: Time of day variation
        side: Side type
        specific_photo: Optional specific photo to use
        config_override: Optional config override
        company_schemas: List of company schemas to search for mockup data
        company_hint: Optional company to try first for O(1) asset lookups

    Returns:
        Tuple of (result_path, metadata)
    """
    from generators import mockup as mockup_generator
    from core.utils.memory import cleanup_memory

    logger = config.logger
    logger.info(f"[QUEUE] Mockup generation requested for {location_key}")

    # This function will be queued and executed when a slot is available
    async def _generate():
        try:
            logger.info(f"[QUEUE] Starting mockup generation for {location_key}")
            result_path, metadata = await mockup_generator.generate_mockup_async(
                location_key,
                creative_paths,
                time_of_day=time_of_day,
                side=side,
                specific_photo=specific_photo,
                config_override=config_override,
                company_schemas=company_schemas,
                company_hint=company_hint,
            )
            logger.info(f"[QUEUE] Mockup generation completed for {location_key}")
            cleanup_memory(context="mockup_queue", aggressive=False, log_stats=False)
            return result_path, metadata
        except Exception as e:
            logger.error(f"[QUEUE] Mockup generation failed for {location_key}: {e}")
            raise

    # Submit to queue and wait for result
    return await mockup_queue.submit(_generate)


async def _generate_ai_mockup_queued(
    ai_prompts: list[str],
    location_key: str,
    time_of_day: str,
    side: str,
    user_id: str | None = None,
    company_schemas: list = None,
    company_hint: str = None,
):
    """
    Wrapper for AI mockup generation (AI creative generation + mockup) through the queue.
    This ensures the entire AI workflow (fetch from OpenAI + image processing + mockup)
    is treated as ONE queued task to prevent memory spikes.

    Args:
        ai_prompts: List of user creative briefs (1 for tiled, N for multi-frame)
        location_key: Location identifier
        time_of_day: Time of day variation
        side: Side type
        user_id: Optional Slack user ID for cost tracking
        company_schemas: List of company schemas to search for mockup data
        company_hint: Optional company to try first for O(1) asset lookups

    Returns:
        Tuple of (result_path, ai_creative_paths)
    """
    from generators import mockup as mockup_generator
    from core.utils.memory import cleanup_memory

    logger = config.logger
    num_prompts = len(ai_prompts)
    logger.info(f"[QUEUE] AI mockup requested for {location_key} ({num_prompts} prompt(s))")

    async def _generate():
        try:
            logger.info(f"[QUEUE] Generating {num_prompts} AI creative(s) for {location_key} in parallel")

            # Generate all creatives in parallel (asyncio.gather preserves order)
            # generate_ai_creative applies the system prompt internally
            logger.info(f"[AI QUEUE] Executing {num_prompts} image generation(s) in parallel...")
            creative_tasks = [
                mockup_generator.generate_ai_creative(
                    prompt=user_prompt,
                    location_key=location_key,
                    user_id=user_id
                )
                for user_prompt in ai_prompts
            ]
            ai_creative_paths = await asyncio.gather(*creative_tasks)

            # Check if any failed
            for i, creative_path in enumerate(ai_creative_paths, 1):
                if not creative_path:
                    raise Exception(f"Failed to generate AI creative {i}/{num_prompts}")

            logger.info(f"[QUEUE] All AI creatives ready, generating mockup for {location_key}")

            # Generate mockup with AI creatives
            result_path, metadata = await mockup_generator.generate_mockup_async(
                location_key,
                ai_creative_paths,
                time_of_day=time_of_day,
                side=side,
                company_schemas=company_schemas,
                company_hint=company_hint,
            )

            if not result_path:
                raise Exception("Failed to generate mockup")

            logger.info(f"[QUEUE] AI mockup completed for {location_key}")
            cleanup_memory(context="ai_mockup_queue", aggressive=False, log_stats=False)
            return result_path, ai_creative_paths

        except Exception as e:
            logger.error(f"[QUEUE] AI mockup failed for {location_key}: {e}")
            raise

    # Submit entire AI workflow to queue as ONE task
    return await mockup_queue.submit(_generate)


async def _persist_location_upload(
    location_key: str,
    pptx_path: Path,
    metadata_text: str,
    company: str,
) -> None:
    """
    Upload template to Asset-Management storage.

    Args:
        location_key: Location identifier
        pptx_path: Path to the PPTX file
        metadata_text: Metadata text (kept for backwards compatibility)
        company: Target company to upload to (explicitly selected by user)

    Note: The metadata_text parameter is kept for backwards compatibility but
    location metadata should be managed through Asset-Management's location API.
    """
    from core.services.template_service import TemplateService

    if not company:
        raise ValueError("Company must be specified for template upload")

    # Read file data
    with open(pptx_path, "rb") as f:
        file_data = f.read()

    # Upload to Asset-Management storage
    service = TemplateService(companies=[company])
    success = await service.upload(location_key, file_data, company=company)

    if not success:
        raise Exception(f"Failed to upload template for {location_key} to {company}")

    # Clean up the temp file
    try:
        import os
        os.unlink(pptx_path)
    except OSError:
        pass

    config.logger.info(f"[LOCATION_UPLOAD] Template uploaded to {company}: {location_key}")


async def _handle_booking_order_parse(
    company: str,
    channel_event: dict[str, Any],
    channel: str,
    status_ts: str,
    user_notes: str,
    user_id: str,
    user_message: str = ""
):
    """Handle booking order parsing workflow"""
    logger = config.logger

    # Extract files from slack event
    files = channel_event.get("files", [])
    if not files and channel_event.get("subtype") == "file_share" and "file" in channel_event:
        files = [channel_event["file"]]

    if not files:
        channel_adapter = config.get_channel_adapter()
        await channel_adapter.update_message(
            channel_id=channel,
            message_id=status_ts,
            content="**Error:** No file detected. Please upload a booking order document (Excel, PDF, or image)."
        )
        return

    file_info = files[0]
    logger.info(f"[BOOKING] Processing file: {file_info.get('name')}")

    # Download file
    try:
        tmp_file = await download_file(file_info)
    except Exception as e:
        logger.error(f"[BOOKING] Download failed: {e}")
        channel_adapter = config.get_channel_adapter()
        await channel_adapter.update_message(
            channel_id=channel,
            message_id=status_ts,
            content=f"**Error:** Failed to download file: {e}"
        )
        return

    # Initialize parser
    parser = BookingOrderParser(company=company)
    file_type = parser.detect_file_type(tmp_file)

    # Classify document
    try:
        channel_adapter = config.get_channel_adapter()
        await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="🔍 _Classifying document..._")
    except Exception as e:
        logger.error(f"[CHANNEL] Failed to update status message while classifying: {e}", exc_info=True)
        # Continue processing - status update failure shouldn't stop the workflow

    # Convert user_id to user_name for cost tracking
    from core.bo_messaging import get_user_real_name
    user_name = await get_user_real_name(user_id) if user_id else None

    classification = await parser.classify_document(tmp_file, user_message=user_message, user_id=user_name)
    logger.info(f"[BOOKING] Classification: {classification}")

    # Check if it's actually a booking order
    if classification.get("classification") != "BOOKING_ORDER" or classification.get("confidence") in {"low", None}:
        try:
            channel_adapter = config.get_channel_adapter()
            await channel_adapter.update_message(
                channel_id=channel,
                message_id=status_ts,
                content=(
                    f"This doesn't look like a booking order (confidence: {classification.get('confidence', 'unknown')}).\n\n"
                    f"Reasoning: {classification.get('reasoning', 'N/A')}\n\n"
                    f"If this is artwork for a mockup, please request a mockup instead."
                )
            )
        except Exception as e:
            logger.error(f"[CHANNEL] Failed to send classification result to user: {e}", exc_info=True)
        tmp_file.unlink(missing_ok=True)
        return

    # Parse the booking order
    # TODO: Re-enable timeout protection once we optimize parsing speed
    # Current issue: High reasoning effort can take 10-15+ minutes on complex BOs
    try:
        channel_adapter = config.get_channel_adapter()
        await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="📋 _Extracting booking order data..._")
    except Exception as e:
        logger.error(f"[CHANNEL] Failed to update status message while parsing: {e}", exc_info=True)
    try:
        result = await parser.parse_file(tmp_file, file_type, user_message=user_message, user_id=user_name)
    except Exception as e:
        logger.error(f"[BOOKING] Parsing failed: {e}", exc_info=True)
        try:
            channel_adapter = config.get_channel_adapter()
            await channel_adapter.update_message(
                channel_id=channel,
                message_id=status_ts,
                content=(
                    f"**Error:** Failed to extract data from the booking order.\n\n"
                    f"If you believe this is a bug, please contact the AI team with the timestamp: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}`"
                )
            )
        except Exception as channel_error:
            logger.error(f"[CHANNEL] Failed to send parsing error to user: {channel_error}", exc_info=True)
        tmp_file.unlink(missing_ok=True)
        return

    # NEW FLOW: Generate Excel immediately and send with Approve/Reject buttons
    try:
        channel_adapter = config.get_channel_adapter()
        await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="📊 _Generating Excel file..._")
    except Exception as e:
        logger.error(f"[CHANNEL] Failed to update status message while generating Excel: {e}", exc_info=True)

    try:
        # Generate combined PDF (Excel + Original BO concatenated)
        from workflows import bo_approval as bo_approval_workflow
        combined_pdf_path = await parser.generate_combined_pdf(result.data, f"DRAFT_{company}_REVIEW", Path(tmp_file))

        # Create approval workflow
        workflow_id = await bo_approval_workflow.create_approval_workflow(
            user_id=user_id,
            company=company,
            data=result.data,
            warnings=result.warnings,
            missing_required=result.missing_required,
            original_file_path=tmp_file,
            original_filename=file_info.get("name"),
            file_type=file_type,
            user_notes=user_notes
        )

        # Get coordinator channel (uses conversations.open to get DM channel ID)
        coordinator_channel = await bo_approval_workflow.get_coordinator_channel(company)
        logger.info(f"[BO APPROVAL] Coordinator channel for {company}: {coordinator_channel}")
        if not coordinator_channel:
            try:
                channel_adapter = config.get_channel_adapter()
                await channel_adapter.update_message(
                    channel_id=channel,
                    message_id=status_ts,
                    content=f"**Error:** Sales Coordinator for {company} not configured. Please contact the AI team to set this up."
                )
            except Exception as e:
                logger.error(f"[CHANNEL] Failed to send config error to user: {e}", exc_info=True)
            return

        # Send Excel + summary + Approve/Reject buttons to coordinator
        submitter_name = await bo_messaging.get_user_real_name(user_id)
        preview_text = "📋 **New Booking Order - Ready for Approval**\n\n"
        preview_text += f"**Company:** {company.upper()}\n"
        preview_text += f"**Submitted by:** {submitter_name}\n\n"
        preview_text += f"**Client:** {result.data.get('client', 'N/A')}\n"
        preview_text += f"**Campaign:** {result.data.get('brand_campaign', 'N/A')}\n"
        preview_text += f"**BO Number:** {result.data.get('bo_number', 'N/A')}\n"

        # Format monetary values safely (handle None from parser failures)
        net_pre_vat = result.data.get('net_pre_vat')
        vat_calc = result.data.get('vat_calc')
        gross_calc = result.data.get('gross_calc')

        # Log warning if critical financial fields are missing (parser should have extracted these)
        if net_pre_vat is None or vat_calc is None or gross_calc is None:
            logger.warning(f"[BO APPROVAL] Parser failed to extract financial fields: net_pre_vat={net_pre_vat}, vat_calc={vat_calc}, gross_calc={gross_calc}")

        preview_text += f"**Net (pre-VAT):** AED {net_pre_vat or 0:,.2f}\n"
        preview_text += f"**VAT (5%):** AED {vat_calc or 0:,.2f}\n"
        preview_text += f"**Gross Total:** AED {gross_calc or 0:,.2f}\n"

        if result.data.get("locations"):
            preview_text += f"\n**Locations:** {len(result.data['locations'])}\n"
            for loc in result.data["locations"][:3]:  # Show first 3
                net_amount = loc.get('net_amount')
                preview_text += f"  • {loc.get('name', 'Unknown')}: {loc.get('start_date', '?')} to {loc.get('end_date', '?')} (AED {net_amount or 0:,.2f})\n"
            if len(result.data["locations"]) > 3:
                preview_text += f"  ...and {len(result.data['locations']) - 3} more\n"

        if result.warnings:
            preview_text += "\n⚠️ **Warnings:**\n" + "\n".join(f"• {w}" for w in result.warnings)

        if result.missing_required:
            preview_text += "\n❌ **Missing Required:**\n" + "\n".join(f"• {m}" for m in result.missing_required)

        # Always include the sales person's message (from user_message or user_notes)
        sales_message = user_notes or user_message
        if sales_message:
            preview_text += f"\n📝 **Sales Person Message:** {sales_message}\n"

        preview_text += "\n\n📎 **Please review the Excel file attached below, then:**\n"
        preview_text += "• Press **Approve** to send to Head of Sales\n"
        preview_text += "• Press **Reject** to request changes in a thread"

        # NEW FLOW: Post notification in main channel, then file + buttons in thread
        try:
            channel_adapter = config.get_channel_adapter()
            await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="📤 _Sending to coordinator..._")
        except Exception as e:
            logger.error(f"[CHANNEL] Failed to update status message: {e}", exc_info=True)

        logger.info(f"[BO APPROVAL] Posting notification to coordinator channel: {coordinator_channel}")

        # Get submitter's real name
        submitter_name = await bo_messaging.get_user_real_name(user_id)

        # Step 1: Post notification message in main channel
        notification_text = (
            f"**New Booking Order Submitted**\n\n"
            f"**Client:** {result.data.get('client', 'N/A')}\n"
            f"**Campaign:** {result.data.get('brand_campaign', 'N/A')}\n"
            f"**Gross Total:** AED {result.data.get('gross_calc', 0):,.2f}\n\n"
            f"**Submitted by:** {submitter_name}\n\n"
            f"_Please review the details in the thread below..._"
        )

        channel_adapter = config.get_channel_adapter()
        notification_msg = await channel_adapter.send_message(
            channel_id=coordinator_channel,
            content=notification_text
        )
        notification_ts = notification_msg.platform_message_id or notification_msg.id
        logger.info(f"[BO APPROVAL] Posted notification with ts: {notification_ts}")

        # Step 2: Upload combined PDF file as threaded reply
        logger.info("[BO APPROVAL] Uploading combined PDF in thread...")
        try:
            await channel_adapter.upload_file(
                channel_id=coordinator_channel,
                file_path=str(combined_pdf_path),
                title=f"BO Draft - {result.data.get('client', 'Unknown')}",
                comment=preview_text,
                thread_id=notification_ts  # Post in thread
            )
            logger.info("[BO APPROVAL] Combined PDF uploaded in thread successfully")
        except Exception as upload_error:
            logger.error(f"[BO APPROVAL] Failed to upload combined PDF: {upload_error}", exc_info=True)
            raise Exception(f"Failed to send combined PDF to coordinator. Channel/User ID: {coordinator_channel}")

        # Wait for file to fully appear in Slack before posting buttons
        logger.info("[BO APPROVAL] Waiting 10 seconds for file to render in Slack...")
        await asyncio.sleep(10)

        # Step 3: Post buttons in the same thread
        logger.info("[BO APPROVAL] Posting approval buttons in thread...")
        from integrations.channels import Button, ButtonStyle

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

        button_msg = await channel_adapter.send_message(
            channel_id=coordinator_channel,
            content="**Please review the PDF above (Excel + Original BO), then:**",
            buttons=buttons,
            thread_id=notification_ts  # Post in same thread
        )
        coordinator_msg_ts = button_msg.platform_message_id or button_msg.id
        logger.info(f"[BO APPROVAL] Posted buttons in thread with ts: {coordinator_msg_ts}")

        # Update workflow with coordinator message info
        await bo_approval_workflow.update_workflow(workflow_id, {
            "coordinator_thread_channel": coordinator_channel,
            "coordinator_thread_ts": notification_ts,  # The notification message is the thread root
            "coordinator_msg_ts": coordinator_msg_ts,  # The button message
            "combined_pdf_path": str(combined_pdf_path)
        })

        # Notify sales person
        try:
            await channel_adapter.update_message(
                channel_id=channel,
                message_id=status_ts,
                content=(
                    f"**Booking Order Submitted**\n\n"
                    f"**Client:** {result.data.get('client', 'N/A')}\n"
                    f"**Campaign:** {result.data.get('brand_campaign', 'N/A')}\n"
                    f"**Gross Total:** AED {result.data.get('gross_calc', 0):,.2f}\n\n"
                    f"Your booking order has been sent to the Sales Coordinator with a combined PDF (parsed data + original BO) for immediate review. "
                    f"You'll be notified once the approval process is complete."
                )
            )
        except Exception as e:
            logger.error(f"[CHANNEL] Failed to send success message to user: {e}", exc_info=True)

        logger.info(f"[BO APPROVAL] Sent {workflow_id} to coordinator with combined PDF and approval buttons")

    except Exception as e:
        logger.error(f"[BO APPROVAL] Error creating workflow: {e}", exc_info=True)
        try:
            channel_adapter = config.get_channel_adapter()
            await channel_adapter.update_message(
                channel_id=channel,
                message_id=status_ts,
                content=(
                    f"**Error:** Failed to start the approval workflow.\n\n"
                    f"If you believe this is a bug, please contact the AI team with the timestamp: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}`"
                )
            )
        except Exception as channel_error:
            logger.error(f"[CHANNEL] Failed to send workflow error to user: {channel_error}", exc_info=True)


async def handle_booking_order_edit_flow(channel: str, user_id: str, user_input: str) -> str:
    """Handle booking order edit flow with structured LLM response"""
    from core.bo_messaging import get_user_real_name
    from integrations.llm import LLMClient, LLMMessage

    try:
        edit_data = pending_booking_orders.get(user_id, {})
        current_data = edit_data.get("data", {})
        warnings = edit_data.get("warnings", [])
        missing_required = edit_data.get("missing_required", [])

        # Build system prompt for LLM to parse user intent
        system_prompt = get_bo_edit_prompt(
            user_input=user_input,
            current_data=current_data,
            warnings=warnings,
            missing_required=missing_required
        )

        # Use LLMClient for abstracted LLM access
        llm_client = LLMClient.from_config()
        user_name = await get_user_real_name(user_id) if user_id else None

        response = await llm_client.complete(
            messages=[LLMMessage.system(system_prompt)],
            json_schema=get_bo_edit_response_schema(),
            store=config.IS_DEVELOPMENT,  # Store in OpenAI only in dev mode
            # Prompt caching: BO edit prompts share common structure
            cache_key="bo-edit",
            cache_retention="24h",
            call_type="bo_edit",
            workflow="bo_editing",
            user_id=user_name,
            context=f"Channel: {channel}",
        )

        decision = json.loads(response.content)
        action = decision.get('action')
        message = decision.get('message', '')

        if action == 'approve':
            # Start approval workflow - send directly to Sales Coordinator (admin is HoS)
            try:
                from workflows import bo_approval as bo_approval_workflow

                # Generate combined PDF for coordinator review
                parser = BookingOrderParser(company=edit_data.get("company"))
                combined_pdf = await parser.generate_combined_pdf(
                    current_data,
                    f"DRAFT_{edit_data.get('company')}",
                    Path(edit_data.get("original_file_path"))
                )

                # Create approval workflow (start at coordinator stage since admin is HoS)
                workflow_id = await bo_approval_workflow.create_approval_workflow(
                    user_id=user_id,
                    company=edit_data.get("company"),
                    data=current_data,
                    warnings=warnings,
                    missing_required=missing_required,
                    original_file_path=edit_data.get("original_file_path"),
                    original_filename=edit_data.get("original_filename"),
                    file_type=edit_data.get("file_type"),
                    user_notes=edit_data.get("user_notes", "")
                )

                # Get coordinator channel (uses conversations.open to get DM channel ID)
                coordinator_channel = await bo_approval_workflow.get_coordinator_channel(edit_data.get("company"))
                if not coordinator_channel:
                    return f"❌ **Error:** Sales Coordinator for {edit_data.get('company')} not configured. Please update hos_config.json"

                # Send to Sales Coordinator with buttons
                result = await bo_messaging.send_to_coordinator(
                    channel=coordinator_channel,
                    workflow_id=workflow_id,
                    company=edit_data.get("company"),
                    data=current_data,
                    combined_pdf_path=str(combined_pdf),
                    warnings=edit_data.get("warnings", []),
                    missing_required=edit_data.get("missing_required", []),
                    user_notes=edit_data.get("user_notes", "")
                )

                # Update workflow with coordinator message info
                await bo_approval_workflow.update_workflow(workflow_id, {
                    "coordinator_msg_ts": result["message_id"]
                })

                # Clean up edit session
                del pending_booking_orders[user_id]

                return f"✅ **Booking Order Submitted for Approval**\n\n**Client:** {current_data.get('client', 'N/A')}\n**Campaign:** {current_data.get('brand_campaign', 'N/A')}\n**Gross Total:** AED {current_data.get('gross_calc', 0):,.2f}\n\nSent to Sales Coordinator for approval. You'll be notified once the approval process is complete."

            except Exception as e:
                config.logger.error(f"[BOOKING ORDER] Error starting approval workflow: {e}")
                return f"❌ **Error starting approval workflow:** {str(e)}\n\nPlease try again or say 'cancel' to discard."

        elif action == 'cancel':
            # Clean up temp file and session
            try:
                original_file_path = edit_data.get("original_file_path")
                if original_file_path and Path(original_file_path).exists():
                    Path(original_file_path).unlink()
            except Exception as e:
                config.logger.error(f"[BOOKING ORDER] Error deleting temp file: {e}")

            del pending_booking_orders[user_id]
            return message or "❌ **Booking order draft discarded.**"

        elif action == 'view':
            # Show current draft
            preview = "📋 **Current Booking Order Draft**\n\n"

            # Core fields
            preview += f"**Client:** {current_data.get('client', 'N/A')}\n"
            preview += f"**Campaign:** {current_data.get('brand_campaign', 'N/A')}\n"
            preview += f"**BO Number:** {current_data.get('bo_number', 'N/A')}\n"
            preview += f"**BO Date:** {current_data.get('bo_date', 'N/A')}\n"
            preview += f"**Net (pre-VAT):** AED {current_data.get('net_pre_vat', 0):,.2f}\n"
            preview += f"**VAT (5%):** AED {current_data.get('vat_calc', 0):,.2f}\n"
            preview += f"**Gross Total:** AED {current_data.get('gross_calc', 0):,.2f}\n\n"

            # Locations
            locations = current_data.get('locations', [])
            if locations:
                preview += f"**Locations ({len(locations)}):**\n"
                for i, loc in enumerate(locations, 1):
                    preview += f"{i}. {loc.get('name', 'Unknown')}: {loc.get('start_date', '?')} to {loc.get('end_date', '?')} (AED {loc.get('net_amount', 0):,.2f})\n"

            if warnings:
                preview += f"\n⚠️ **Warnings ({len(warnings)}):**\n"
                for w in warnings[:3]:
                    preview += f"• {w}\n"

            if missing_required:
                preview += f"\n❗ **Missing Required Fields:** {', '.join(missing_required)}\n"

            preview += "\n**What would you like to do?**\n"
            preview += "• Tell me any corrections\n"
            preview += "• Say 'approve' to save\n"
            preview += "• Say 'cancel' to discard"

            return preview

        elif action == 'edit':
            # Apply field updates
            fields = decision.get('fields', {})
            if fields:
                # Update the draft data
                for field, value in fields.items():
                    current_data[field] = value

                # Recalculate VAT and gross if net changed
                if 'net_pre_vat' in fields:
                    current_data['vat_calc'] = round(current_data['net_pre_vat'] * 0.05, 2)
                    current_data['gross_calc'] = round(current_data['net_pre_vat'] + current_data['vat_calc'], 2)

                # Save updated draft
                pending_booking_orders[user_id]["data"] = current_data

                response = message or "✅ **Changes applied:**\n"
                for field, value in fields.items():
                    response += f"• {field}: {value}\n"
                response += "\nSay 'approve' to save or continue editing."
                return response
            else:
                return message or "I didn't catch any changes. What would you like to update?"

        else:
            return "I didn't understand. Please tell me what to change, or say 'approve' to save or 'cancel' to discard."

    except Exception as e:
        config.logger.error(f"[BOOKING ORDER] Error in edit flow: {e}")
        return f"❌ **Error processing your request:** {str(e)}\n\nPlease try again."


async def _process_llm_streaming(
    llm_client,
    llm_messages: list,
    all_tools: list,
    channel: str,
    user_id: str,
    user_name: str | None,
    status_ts: str | None,
    channel_event: dict | None,
    user_input: str,
    has_files: bool,
    history: list,
    channel_adapter,
    user_companies: list[str] | None,
    workflow_ctx: WorkflowContext | None = None,
) -> None:
    """
    Process LLM response using streaming for real-time token display.

    This function handles:
    - Text responses: streams tokens to the WebAdapter for real-time display
    - Tool calls: collects full arguments and dispatches to tool router
    """
    import uuid
    import re

    logger = config.logger
    workflow = "general_chat"

    # Generate message ID for this response
    message_id = str(uuid.uuid4())

    # Track streaming state
    text_content = ""
    tool_calls_data = {}  # item_id -> {name, arguments}
    has_tool_call = False

    try:
        async for event in llm_client.stream_complete(
            messages=llm_messages,
            tools=all_tools,
            tool_choice="auto",
            cache_key="main-chat",
            cache_retention="24h",
            call_type="main_llm",
            workflow=workflow,
            user_id=user_name,
            context=f"Channel: {channel}",
            metadata={"has_files": has_files, "message_length": len(user_input)}
        ):
            event_type = event.get("type")

            if event_type == "response.output_text.delta":
                # Stream text delta to frontend
                delta = event.get("delta", "")
                if delta:
                    text_content += delta
                    channel_adapter.push_stream_delta(user_id, message_id, delta)

            elif event_type == "response.output_text.done":
                # Text streaming complete - we'll finalize after all events
                pass

            elif event_type == "response.output_item.added":
                # New output item - check if it's a function call
                item = event.get("item", {})
                if item.get("type") == "function_call":
                    has_tool_call = True
                    item_id = item.get("id") or item.get("call_id")
                    tool_calls_data[item_id] = {
                        "name": item.get("name", ""),
                        "arguments": "",
                        "call_id": item.get("call_id", item_id),
                    }

            elif event_type == "response.function_call_arguments.delta":
                # Accumulate function call arguments
                item_id = event.get("item_id")
                if item_id and item_id in tool_calls_data:
                    tool_calls_data[item_id]["arguments"] += event.get("delta", "")

            elif event_type == "response.function_call_arguments.done":
                # Function call arguments complete
                item_id = event.get("item_id")
                if item_id and item_id in tool_calls_data:
                    tool_calls_data[item_id]["name"] = event.get("name", tool_calls_data[item_id]["name"])
                    tool_calls_data[item_id]["arguments"] = event.get("arguments", tool_calls_data[item_id]["arguments"])

            elif event_type == "response.completed":
                # Streaming complete
                logger.info(f"[LLM:STREAM] Streaming complete for {user_id}")

            elif event_type == "error" or event_type == "response.failed":
                # Handle errors
                error_msg = event.get("message") or event.get("error", {}).get("message", "Unknown error")
                logger.error(f"[LLM:STREAM] Error: {error_msg}")
                await channel_adapter.send_message(channel_id=channel, content=f"❌ **Error:** {error_msg}")
                return

        # Process results after streaming complete
        if has_tool_call and tool_calls_data:
            # Handle tool call
            tool_data = list(tool_calls_data.values())[0]  # Get first tool call

            from integrations.llm import ToolCall
            import json as json_module

            try:
                args = json_module.loads(tool_data["arguments"])
            except json_module.JSONDecodeError:
                args = {}

            tool_call = ToolCall(
                id=tool_data["call_id"],
                name=tool_data["name"],
                arguments=args,
            )

            logger.info(f"[LLM:STREAM] Tool call: {tool_call.name}")

            # Add assistant's tool call to history
            try:
                args_dict = tool_call.arguments
                if tool_call.name == "get_separate_proposals":
                    locations = [p.get("location", "unknown") for p in args_dict.get("proposals", [])]
                    client = args_dict.get("client_name", "unknown")
                    assistant_summary = f"[Generated separate proposals for {client}: {', '.join(locations)}]"
                elif tool_call.name == "get_combined_proposal":
                    locations = [p.get("location", "unknown") for p in args_dict.get("proposals", [])]
                    client = args_dict.get("client_name", "unknown")
                    assistant_summary = f"[Generated combined proposal for {client}: {', '.join(locations)}]"
                elif tool_call.name == "generate_mockup":
                    location = args_dict.get("location", "unknown")
                    assistant_summary = f"[Generated mockup for {location}]"
                elif tool_call.name == "parse_booking_order":
                    assistant_summary = "[Parsed booking order]"
                else:
                    assistant_summary = f"[Called {tool_call.name}]"
            except (KeyError, TypeError, AttributeError):
                assistant_summary = f"[Called {tool_call.name}]"
            history.append({"role": "assistant", "content": assistant_summary, "timestamp": datetime.now().isoformat()})

            # Dispatch to tool router
            from handlers.tool_router import handle_tool_call
            await handle_tool_call(
                tool_call=tool_call,
                channel=channel,
                user_id=user_id,
                status_ts=status_ts,
                channel_event=channel_event,
                user_input=user_input,
                download_file_func=download_file,
                handle_booking_order_parse_func=_handle_booking_order_parse,
                generate_mockup_queued_func=_generate_mockup_queued,
                generate_ai_mockup_queued_func=_generate_ai_mockup_queued,
                user_companies=user_companies,
                workflow_ctx=workflow_ctx,
            )

        elif text_content:
            # Text response - finalize streaming
            # Add to history
            history.append({"role": "assistant", "content": text_content, "timestamp": datetime.now().isoformat()})

            # Format the reply
            formatted_reply = text_content
            formatted_reply = formatted_reply.replace('\n- ', '\n• ')
            formatted_reply = formatted_reply.replace('\n* ', '\n• ')
            formatted_reply = re.sub(r'^(For .+:)$', r'**\1**', formatted_reply, flags=re.MULTILINE)
            formatted_reply = re.sub(r'^([A-Z][A-Z\s]+:)$', r'**\1**', formatted_reply, flags=re.MULTILINE)

            # Signal stream complete with full content
            channel_adapter.push_stream_complete(user_id, message_id, formatted_reply)

        else:
            # No content and no tool calls
            await channel_adapter.send_message(
                channel_id=channel,
                content="I can help with proposals or add locations. Say 'add location'."
            )

    except Exception as e:
        logger.error(f"[LLM:STREAM] Streaming error: {e}", exc_info=True)
        await channel_adapter.send_message(channel_id=channel, content=f"❌ **Error:** {str(e)}")


async def main_llm_loop(
    channel: str,
    user_id: str,
    user_input: str,
    channel_event: dict[str, Any] = None,
    is_admin_override: bool = None,
    user_companies: list[str] | None = None,
):
    """
    Main LLM processing loop - channel-agnostic.

    Works with any channel adapter (Slack, Web, etc.) through the unified
    channel abstraction layer.

    Args:
        channel: Channel/conversation ID (Slack channel ID or web user ID)
        user_id: User identifier
        user_input: User's message text
        channel_event: Channel-specific event data containing:
            - files: List of file info dicts (optional)
            - thread_ts: Thread ID for Slack (optional)
            - subtype: Event subtype (optional)
        is_admin_override: Override admin check (for web UI where roles are passed separately)
        user_companies: List of company schemas user can access (for data filtering)
    """
    logger = config.logger

    # Debug logging
    logger.info(f"[MAIN_LLM] Starting for user {user_id}, pending_adds: {list(pending_location_additions.keys())}")
    if channel_event:
        logger.info(f"[MAIN_LLM] Channel event keys: {list(channel_event.keys())}")
        if "files" in channel_event:
            logger.info(f"[MAIN_LLM] Files found: {len(channel_event['files'])}")

    # Check if message is in a coordinator thread (before sending status message)
    thread_ts = channel_event.get("thread_ts") if channel_event else None
    if thread_ts:
        # Check if this thread is an active coordinator thread
        from workflows import bo_approval as bo_approval_workflow

        # Find workflow with matching coordinator thread
        logger.info(f"[BO APPROVAL] Checking {len(bo_approval_workflow.approval_workflows)} workflows for thread {thread_ts}")
        for workflow_id, workflow in bo_approval_workflow.approval_workflows.items():
            coordinator_thread = workflow.get("coordinator_thread_ts")
            logger.info(f"[BO APPROVAL] Workflow {workflow_id}: coordinator_thread={coordinator_thread}, status={workflow.get('status')}")

            # Check if message is in a coordinator thread (even if not active for editing yet)
            if coordinator_thread == thread_ts:
                # Check if thread is active for editing (after rejection)
                if bo_approval_workflow.is_coordinator_thread_active(workflow, thread_ts):
                    logger.info(f"[BO APPROVAL] Message in active coordinator thread for {workflow_id}")
                    try:
                        answer = await bo_approval_workflow.handle_coordinator_thread_message(
                            workflow_id=workflow_id,
                            user_id=user_id,
                            user_input=user_input,
                            channel=channel,
                            thread_ts=thread_ts
                        )
                        # Only send message if there's an answer (execute action returns None)
                        if answer is not None:
                            channel_adapter = config.get_channel_adapter()
                            await channel_adapter.send_message(
                                channel_id=channel,
                                content=answer,
                                thread_id=thread_ts
                            )
                    except Exception as e:
                        logger.error(f"[BO APPROVAL] Error in coordinator thread handler: {e}", exc_info=True)
                        channel_adapter = config.get_channel_adapter()
                        await channel_adapter.send_message(
                            channel_id=channel,
                            content=f"**Error:** {str(e)}",
                            thread_id=thread_ts
                        )
                    return  # Exit early, don't process as normal message
                else:
                    # Thread exists but not active yet (user hasn't rejected)
                    logger.info(f"[BO APPROVAL] Message in coordinator thread for {workflow_id} but thread not active - reminding user to use buttons")
                    channel_adapter = config.get_channel_adapter()
                    await channel_adapter.send_message(
                        channel_id=channel,
                        content=(
                            "**Please use the Approve or Reject buttons first**\n\n"
                            "To make edits to this booking order, click the **Reject** button above. "
                            "This will open the thread for editing.\n\n"
                            "If the BO looks good, click **Approve** to send it to the next stage."
                        ),
                        thread_id=thread_ts
                    )
                    return  # Exit early, don't process as normal message

    # Send initial status message (skip for web UI - it has its own thinking animation)
    channel_adapter = config.get_channel_adapter()
    status_ts = None
    if channel_adapter.channel_type != ChannelType.WEB:
        status_message = await channel_adapter.send_message(
            channel_id=channel,
            content="⏳ _Please wait..._"
        )
        status_ts = status_message.platform_message_id or status_message.id

    # OLD EDIT FLOW REMOVED - Now coordinators edit directly in threads

    # Check if user has a pending location addition or mockup request and uploaded a file
    # Also check for file_share events which Slack sometimes uses
    has_files = channel_event and ("files" in channel_event or (channel_event.get("subtype") == "file_share"))

    # Note: Mockup generation is now handled in one step within the tool handler
    # No need for pending state - users must upload image WITH request or provide AI prompt

    if user_id in pending_location_additions and has_files:
        pending_data = pending_location_additions[user_id]

        # Check if pending request is still valid (10 minute window)
        timestamp = pending_data.get("timestamp")
        if timestamp and (datetime.now() - timestamp) > timedelta(minutes=10):
            del pending_location_additions[user_id]
            logger.warning(f"[LOCATION_ADD] Pending location expired for user {user_id}")
            await channel_adapter.send_message(
                channel_id=channel,
                content="**Error:** Location upload session expired (10 minute limit). Please restart the location addition process."
            )
            return

        logger.info(f"[LOCATION_ADD] Found pending location for user {user_id}: {pending_data['location_key']}")
        logger.info(f"[LOCATION_ADD] Files in event: {len(channel_event.get('files', []))}")

        # Check if any of the files is a PDF (we'll convert it to PPTX)
        pptx_file = None
        files = channel_event.get("files", [])

        # If it's a file_share event, files might be structured differently
        if not files and channel_event.get("subtype") == "file_share" and "file" in channel_event:
            files = [channel_event["file"]]
            logger.info("[LOCATION_ADD] Using file from file_share event")

        for f in files:
            logger.info(f"[LOCATION_ADD] Checking file: name={f.get('name')}, filetype={f.get('filetype')}, mimetype={f.get('mimetype')}")

            # Accept PDF files (new) - will be converted to PPTX
            if f.get("filetype") == "pdf" or f.get("mimetype") == "application/pdf" or f.get("name", "").lower().endswith(".pdf"):
                try:
                    pdf_file = await download_file(f)
                except Exception as e:
                    logger.error(f"Failed to download PDF file: {e}")
                    await channel_adapter.send_message(
                        channel_id=channel,
                        content="**Error:** Failed to download the PDF file. Please try again."
                    )
                    return

                # Validate it's actually a PDF file
                if not _validate_pdf_file(pdf_file):
                    logger.error(f"Invalid PDF file: {f.get('name')}")
                    try:
                        os.unlink(pdf_file)
                    except OSError as cleanup_err:
                        logger.debug(f"[LOCATION_ADD] Failed to cleanup invalid PDF: {cleanup_err}")
                    await channel_adapter.send_message(
                        channel_id=channel,
                        content="**Error:** The uploaded file is not a valid PDF. Please upload a .pdf file."
                    )
                    return

                # Post status message about conversion
                conversion_status = await channel_adapter.send_message(
                    channel_id=channel,
                    content="🔄 _Converting PDF to PowerPoint with maximum quality (300 DPI)..._"
                )
                conversion_status_ts = conversion_status.platform_message_id or conversion_status.id

                # Convert PDF to PPTX
                logger.info("[LOCATION_ADD] Converting PDF to PPTX...")
                pptx_file = await _convert_pdf_to_pptx(pdf_file)

                # Clean up original PDF
                try:
                    os.unlink(pdf_file)
                except OSError as cleanup_err:
                    logger.debug(f"[LOCATION_ADD] Failed to cleanup original PDF: {cleanup_err}")

                # Delete conversion status message
                await channel_adapter.delete_message(channel_id=channel, message_id=conversion_status_ts)

                if not pptx_file:
                    await channel_adapter.send_message(
                        channel_id=channel,
                        content="**Error:** Failed to convert PDF to PowerPoint. Please try again or contact support."
                    )
                    return

                logger.info(f"[LOCATION_ADD] ✓ PDF converted to PPTX: {pptx_file}")
                break

        if pptx_file:
            # Build metadata.txt content matching exact format of existing files
            metadata_lines = []
            metadata_lines.append(f"Location Name: {pending_data['display_name']}")
            metadata_lines.append(f"Display Name: {pending_data['display_name']}")
            metadata_lines.append(f"Display Type: {pending_data['display_type']}")
            metadata_lines.append(f"Number of Faces: {pending_data['number_of_faces']}")

            # For digital locations, add digital-specific fields in the correct order
            if pending_data['display_type'] == 'Digital':
                metadata_lines.append(f"Spot Duration: {pending_data['spot_duration']}")
                metadata_lines.append(f"Loop Duration: {pending_data['loop_duration']}")
                metadata_lines.append(f"SOV: {pending_data['sov']}")
                if pending_data['upload_fee'] is not None:
                    metadata_lines.append(f"Upload Fee: {pending_data['upload_fee']}")

            # Series, Height, Width come after digital fields
            metadata_lines.append(f"Series: {pending_data['series']}")
            metadata_lines.append(f"Height: {pending_data['height']}")
            metadata_lines.append(f"Width: {pending_data['width']}")

            metadata_text = "\n".join(metadata_lines)

            try:
                # Save the location to the explicitly selected company
                target_company = pending_data['company']
                await _persist_location_upload(
                    pending_data['location_key'],
                    pptx_file,
                    metadata_text,
                    company=target_company,
                )

                # Clean up
                del pending_location_additions[user_id]

                # Refresh templates
                config.refresh_templates()

                # Delete status message
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)

                await channel_adapter.send_message(
                    channel_id=channel,
                    content=(
                        f"**Successfully added location `{pending_data['location_key']}` to `{target_company}`**\n\n"
                        f"The location is now available for use in proposals."
                    )
                )
                return
            except Exception as e:
                logger.error(f"Failed to save location: {e}")
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                await channel_adapter.send_message(
                    channel_id=channel,
                    content="**Error:** Failed to save the location. Please try again."
                )
                # Clean up the temporary file
                try:
                    os.unlink(pptx_file)
                except OSError as cleanup_err:
                    logger.debug(f"[LOCATION_ADD] Failed to cleanup temp PPTX: {cleanup_err}")
                return
        else:
            # No PPT file found, cancel the addition
            del pending_location_additions[user_id]
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(
                channel_id=channel,
                content=(
                    "**Location addition cancelled.**\n\n"
                    "No PowerPoint file was found in your message. Please start over with 'add location' if you want to try again."
                )
            )
            return

    # Check for location deletion confirmation
    if user_input.strip().lower().startswith("confirm delete ") and config.is_admin(user_id):
        location_key = user_input.strip().lower().replace("confirm delete ", "").strip()

        if location_key in config.LOCATION_METADATA:
            display_name = config.LOCATION_METADATA[location_key].get('display_name', location_key)

            try:
                from core.services.template_service import TemplateService
                from generators import mockup as mockup_generator
                from integrations.asset_management import asset_mgmt_client

                # Get user companies for deletion (must have companies to delete)
                if not user_companies:
                    raise ValueError("User companies required for location deletion")

                # Delete PowerPoint templates from Asset-Management storage
                template_service = TemplateService(companies=user_companies)
                template_deleted = False
                for company in user_companies:
                    try:
                        deleted = await template_service.delete(location_key, company)
                        if deleted:
                            template_deleted = True
                            logger.info(f"[LOCATION_DELETE] Deleted template for {location_key} from {company}")
                    except Exception as e:
                        logger.debug(f"[LOCATION_DELETE] Template not found in {company}: {e}")

                if template_deleted:
                    logger.info(f"[LOCATION_DELETE] Template deleted from Asset-Management storage")

                # Delete local mockup photos if they exist
                import shutil
                # New structure: mockups/{company}/{location_key}/...
                for company in user_companies:
                    mockup_dir = mockup_generator.MOCKUPS_DIR / company / location_key
                    if mockup_dir.exists():
                        shutil.rmtree(mockup_dir)
                        logger.info(f"[LOCATION_DELETE] Deleted local mockup directory: {mockup_dir}")
                # Legacy structure cleanup: mockups/{location_key}/...
                legacy_mockup_dir = mockup_generator.MOCKUPS_DIR / location_key
                if legacy_mockup_dir.exists():
                    shutil.rmtree(legacy_mockup_dir)
                    logger.info(f"[LOCATION_DELETE] Deleted legacy mockup directory: {legacy_mockup_dir}")

                # Delete all mockup frame data from Asset-Management for each company
                deleted_count = 0
                for company in user_companies:
                    try:
                        # Get all frames for this location in this company
                        frames = await asset_mgmt_client.get_mockup_frames(company, location_key)
                        for frame in frames:
                            success = await asset_mgmt_client.delete_mockup_frame(
                                company=company,
                                location_key=location_key,
                                photo_filename=frame.get("photo_filename", ""),
                                time_of_day=frame.get("time_of_day", "day"),
                                side=frame.get("side", "gold"),
                            )
                            if success:
                                deleted_count += 1
                    except Exception as e:
                        logger.debug(f"[LOCATION_DELETE] Error deleting frames from {company}: {e}")

                logger.info(f"[LOCATION_DELETE] Deleted {deleted_count} mockup frame entries from Asset-Management")

                # Refresh templates to remove from cache
                config.refresh_templates()

                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                await channel_adapter.send_message(
                    channel_id=channel,
                    content=(
                        f"✅ **Location `{location_key}` successfully deleted**\n\n"
                        f"📍 **Removed:** {display_name}\n"
                        f"🗑️ **Files deleted:** PowerPoint template, metadata, and {deleted_count} mockup frames\n"
                        f"🔄 **Templates refreshed:** Location no longer available for proposals"
                    )
                )
                return
            except Exception as e:
                logger.error(f"[LOCATION_DELETE] Failed to delete location {location_key}: {e}")
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                await channel_adapter.send_message(
                    channel_id=channel,
                    content=f"❌ **Error:** Failed to delete location `{location_key}`. Please try again or check server logs."
                )
                return
        else:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(
                channel_id=channel,
                content=f"❌ **Error:** Location `{location_key}` not found. Deletion cancelled."
            )
            return

    # Handle cancellation
    if user_input.strip().lower() == "cancel" and config.is_admin(user_id):
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content="✅ **Operation cancelled.**"
        )
        return

    # Clean up old pending additions (older than 10 minutes)
    cutoff = datetime.now() - timedelta(minutes=10)
    expired_users = [
        uid for uid, data in pending_location_additions.items()
        if data.get("timestamp", datetime.now()) < cutoff
    ]
    for uid in expired_users:
        del pending_location_additions[uid]

    available_names = ", ".join(config.available_location_names())

    # Get locations and packages for the prompt, grouped by company
    # This provides the LLM with a hierarchical view of available assets
    workflow_ctx = None
    locations_context = ""

    if user_companies:
        # Get locations from Asset-Management (single source of truth)
        from core.services.asset_service import get_asset_service
        from integrations.asset_management import asset_mgmt_client

        asset_service = get_asset_service()
        company_locations = await asset_service.get_locations_for_companies(user_companies)

        # Create workflow context with pre-loaded locations
        workflow_ctx = WorkflowContext.create(
            user_id=user_id,
            user_companies=user_companies,
            locations_list=company_locations,
        )
        logger.debug(f"[LLM] Created WorkflowContext with {len(company_locations)} locations")

        # Fetch packages for user's companies
        try:
            packages = await asset_mgmt_client.get_packages(
                companies=user_companies,
                active_only=True,
            )
            logger.info(f"[LLM] Retrieved {len(packages)} packages for user")
        except Exception as e:
            logger.warning(f"[LLM] Failed to fetch packages: {e}")
            packages = []

        # Group locations by company
        locations_by_company: dict[str, dict[str, list]] = {}
        for loc in company_locations:
            company = loc.get('company_schema') or loc.get('company') or 'unknown'
            if company not in locations_by_company:
                locations_by_company[company] = {'digital': [], 'static': []}

            key = loc.get('location_key', loc.get('key', ''))
            display_name = loc.get('display_name', key)
            display_type = loc.get('display_type', '').lower()

            if display_type == 'digital':
                locations_by_company[company]['digital'].append({
                    'key': key,
                    'name': display_name,
                })
            elif display_type == 'static':
                locations_by_company[company]['static'].append({
                    'key': key,
                    'name': display_name,
                })

        # Group packages by company
        packages_by_company: dict[str, list] = {}
        for pkg in packages:
            company = pkg.get('company_schema') or pkg.get('company') or 'unknown'
            if company not in packages_by_company:
                packages_by_company[company] = []

            pkg_key = pkg.get('package_key', '')
            pkg_name = pkg.get('name', pkg_key)
            items = pkg.get('items', [])

            # Build list of networks in package
            network_list = []
            for item in items:
                network_name = item.get('network_name') or item.get('network_key', 'Unknown')
                network_key = item.get('network_key', '')
                # Try to find display_type from locations
                network_type = 'digital'  # Default
                for loc in company_locations:
                    if loc.get('location_key') == network_key:
                        network_type = loc.get('display_type', 'digital').lower()
                        break
                network_list.append({
                    'key': network_key,
                    'name': network_name,
                    'type': network_type,
                })

            packages_by_company[company].append({
                'key': pkg_key,
                'name': pkg_name,
                'networks': network_list,
            })

        # Build hierarchical context string
        context_parts = []
        all_companies = set(locations_by_company.keys()) | set(packages_by_company.keys())

        for company in sorted(all_companies):
            company_section = [f"\n📍 {company.upper()}"]
            company_section.append("─" * 50)

            # Digital locations
            digital_locs = locations_by_company.get(company, {}).get('digital', [])
            if digital_locs:
                company_section.append("DIGITAL LOCATIONS:")
                for loc in digital_locs:
                    company_section.append(f"  • {loc['name']} ({loc['key']})")

            # Static locations
            static_locs = locations_by_company.get(company, {}).get('static', [])
            if static_locs:
                company_section.append("STATIC LOCATIONS:")
                for loc in static_locs:
                    company_section.append(f"  • {loc['name']} ({loc['key']})")

            # Packages
            company_packages = packages_by_company.get(company, [])
            if company_packages:
                company_section.append("PACKAGES (bundles of locations sold together):")
                for pkg in company_packages:
                    company_section.append(f"  📦 {pkg['name']} ({pkg['key']})")
                    if pkg['networks']:
                        for net in pkg['networks']:
                            company_section.append(f"     └ {net['name']} ({net['key']}) - {net['type']}")
                    else:
                        company_section.append("     └ (no locations configured)")

            context_parts.append("\n".join(company_section))

        locations_context = "\n".join(context_parts) if context_parts else "No locations available."

        logger.info(f"[LLM] User companies: {user_companies}")
        logger.info(f"[LLM] Built context with {len(company_locations)} locations, {len(packages)} packages")
    else:
        # Fallback to global cache (for Slack without company filtering)
        logger.info("[LLM] No user_companies provided, using global location cache")
        static_locations = []
        digital_locations = []
        for key, meta in config.LOCATION_METADATA.items():
            display_name = meta.get('display_name', key)
            if meta.get('display_type', '').lower() == 'static':
                static_locations.append(f"{display_name} ({key})")
            elif meta.get('display_type', '').lower() == 'digital':
                digital_locations.append(f"{display_name} ({key})")

        # Build simple context without company grouping
        context_parts = []
        if digital_locations:
            context_parts.append("DIGITAL LOCATIONS:\n  • " + "\n  • ".join(digital_locations))
        if static_locations:
            context_parts.append("STATIC LOCATIONS:\n  • " + "\n  • ".join(static_locations))
        locations_context = "\n\n".join(context_parts) if context_parts else "No locations available."

    # Check if user is admin for system prompt and tool filtering
    # Use override if provided (for web UI where roles are passed separately), otherwise check config
    is_admin = is_admin_override if is_admin_override is not None else config.is_admin(user_id)

    prompt = get_main_system_prompt(
        is_admin=is_admin,
        locations_context=locations_context,
        user_companies=user_companies,
    )

    # Check if user uploaded files and append to message
    user_message_content = user_input
    image_files = []  # Initialize outside conditional block
    document_files = []  # For PDFs, Excel, etc.

    if has_files and channel_event:
        from core.utils.constants import is_document_mimetype, is_image_mimetype

        files = channel_event.get("files", [])
        if not files and channel_event.get("subtype") == "file_share" and "file" in channel_event:
            files = [channel_event["file"]]

        # Check for image files and document files
        for f in files:
            filetype = f.get("filetype", "")
            mimetype = f.get("mimetype", "")
            filename = f.get("name", "").lower()

            # Image files (for mockups) - use exact MIME type matching for security
            if (filetype in ["jpg", "jpeg", "png", "gif", "bmp"] or
                is_image_mimetype(mimetype) or
                any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp"])):
                image_files.append(f.get("name", "image"))
            # Document files (for booking orders, proposals, etc.)
            elif (filetype in ["pdf", "xlsx", "xls", "csv", "docx", "doc"] or
                  is_document_mimetype(mimetype) or
                  any(filename.endswith(ext) for ext in [".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc"])):
                document_files.append(f.get("name", "document"))

        # PRE-ROUTING CLASSIFIER: Use centralized classifier for file routing
        from core.classification import ClassificationContext, RequestType, get_classifier

        classifier = get_classifier()
        classification_result = await classifier.classify(
            context=ClassificationContext(
                text=user_input,
                files=files,
                user_id=user_id,
                user_companies=user_companies,
                channel_type="slack" if channel else "web",
            ),
            download_file_func=download_file,
        )

        logger.info(f"[CLASSIFIER] Result: {classification_result.request_type.value} "
                    f"(confidence={classification_result.confidence.value}, "
                    f"deterministic={classification_result.is_deterministic})")

        # Route based on HIGH confidence classification
        if classification_result.is_high_confidence:
            if classification_result.request_type == RequestType.BO_PARSING:
                company = classification_result.company or "backlite"
                logger.info(f"[CLASSIFIER] HIGH CONFIDENCE BO ({company}) - routing directly")

                await _handle_booking_order_parse(
                    company=company,
                    channel_event=channel_event,
                    channel=channel,
                    status_ts=status_ts,
                    user_notes="",
                    user_id=user_id,
                    user_message=user_input
                )
                return  # Exit early - don't call LLM

            elif classification_result.request_type == RequestType.MOCKUP:
                logger.info("[CLASSIFIER] HIGH CONFIDENCE MOCKUP - letting LLM handle")
                # Clear document_files and set as image for LLM to handle as mockup
                document_files.clear()
                if not image_files:
                    for f in classification_result.files:
                        image_files.append(f.filename)
                # Fall through to LLM for mockup generation

            elif classification_result.request_type == RequestType.OTHER:
                logger.info(f"[CLASSIFIER] HIGH CONFIDENCE OTHER - informing LLM: {classification_result.reasoning}")
                # The file is neither a BO nor artwork - inform the main LLM
                # so it can respond appropriately to the user
                filenames = ", ".join(f.filename for f in classification_result.files) if classification_result.files else "uploaded file"
                user_message_content = (
                    f"{user_input}\n\n"
                    f"[SYSTEM: The uploaded file ({filenames}) was analyzed and determined to be "
                    f"neither a booking order nor artwork for mockup generation. "
                    f"Classification reasoning: {classification_result.reasoning}. "
                    f"Please respond to the user appropriately - they may have uploaded the wrong file "
                    f"or need help with something else.]"
                )
                # Clear file lists since we've already informed the LLM about the classification
                image_files.clear()
                document_files.clear()
                # Fall through to LLM

        # Low/medium confidence or unknown - fall through to LLM

        # Inform LLM about uploaded files (only if pre-router didn't handle it)
        if image_files:
            user_message_content = f"{user_input}\n\n[User uploaded {len(image_files)} image file(s): {', '.join(image_files)}]"
            logger.info(f"[LLM] Detected {len(image_files)} uploaded image(s), informing LLM")
        elif document_files:
            user_message_content = f"{user_input}\n\n[User uploaded {len(document_files)} document file(s): {', '.join(document_files)}]"
            logger.info(f"[LLM] Detected {len(document_files)} uploaded document(s), informing LLM")

    # Inject mockup history context ONLY if user did NOT upload ANY files (to avoid confusion)
    # Don't inject mockup history when user uploads documents (BO PDFs, Excel, etc.) or images
    if not image_files and not document_files:
        mockup_hist = get_mockup_history(user_id)
        if mockup_hist:
            metadata = mockup_hist.get("metadata", {})
            stored_location = metadata.get("location_name", "unknown")
            stored_frames = metadata.get("num_frames", 1)
            mode = metadata.get("mode", "unknown")

            # Calculate time remaining
            timestamp = mockup_hist.get("timestamp")
            if timestamp:
                time_remaining = 30 - int((datetime.now() - timestamp).total_seconds() / 60)
                time_remaining = max(0, time_remaining)

                user_message_content = (
                    f"{user_input}\n\n"
                    f"[SYSTEM: User has {stored_frames}-frame creative(s) in memory from '{stored_location}' ({mode}). "
                    f"Expires in {time_remaining} minutes. Can reuse for follow-up mockup requests on locations with {stored_frames} frame(s).]"
                )
                logger.info(f"[LLM] Injected mockup history context: {stored_frames} frames from {stored_location}, {time_remaining}min remaining")

    history = user_history.get(user_id, [])
    history.append({"role": "user", "content": user_message_content, "timestamp": datetime.now().isoformat()})
    history = history[-10:]

    # Build LLM messages from history
    from core.bo_messaging import get_user_real_name
    from integrations.llm import LLMClient, LLMMessage

    # Sanitize placeholders that might have leaked from frontend formatting
    def _sanitize_content(text: str) -> str:
        """Remove any leaked frontend placeholders from message content."""
        if not text:
            return text
        # Remove __INLINE_CODE_X__ and __CODE_BLOCK_X__ placeholders
        # These are used by frontend formatContent() and should never reach the LLM
        import re
        text = re.sub(r'__INLINE_CODE_\d+__', '', text)
        text = re.sub(r'__CODE_BLOCK_\d+__', '', text)
        return text

    llm_messages = [LLMMessage.system(prompt)]

    # Ensure history starts with a user message (skip leading assistant messages)
    # This fixes issues where error messages get persisted without corresponding user messages
    history_start = 0
    for i, msg in enumerate(history):
        if msg.get("role") == "user":
            history_start = i
            break

    for msg in history[history_start:]:
        role = msg.get("role", "user")
        content = _sanitize_content(msg.get("content", ""))
        if role == "user":
            llm_messages.append(LLMMessage.user(content))
        elif role == "assistant":
            llm_messages.append(LLMMessage.assistant(content))

    # Debug: Log message order for troubleshooting
    logger.debug(f"[LLM] Building messages: system prompt + {len(history)} history messages")
    for i, msg in enumerate(llm_messages[:5]):  # Log first 5 for debugging
        role = msg.role
        if role == "system":
            # Don't log system prompt content - too long
            preview = f"[{len(msg.content)} chars]" if isinstance(msg.content, str) else "[complex]"
        else:
            preview = (msg.content[:50] + "...") if isinstance(msg.content, str) and len(msg.content) > 50 else msg.content
        logger.debug(f"[LLM] Message {i}: role={role}, content={preview}")

    # Get tools from centralized tool definitions
    base_tools = get_base_tools()
    all_tools = list(base_tools)

    # Admin-only tools
    if is_admin:
        admin_tools = get_admin_tools()
        all_tools.extend(admin_tools)
        logger.info(f"[LLM] Admin user {user_id} - added {len(admin_tools)} admin-only tools")

    try:
        # Use LLMClient for abstracted LLM access
        llm_client = LLMClient.from_config()
        user_name = await get_user_real_name(user_id) if user_id else None

        # Determine workflow for cost tracking (will be updated based on tool call)
        workflow = "general_chat"

        # Check if we should use streaming (Web channel only)
        # TODO: Re-enable after fixing tool call detection in streaming mode
        use_streaming = False  # channel_adapter.channel_type == ChannelType.WEB

        if use_streaming:
            # Use streaming for Web UI - token-by-token display
            await _process_llm_streaming(
                llm_client=llm_client,
                llm_messages=llm_messages,
                all_tools=all_tools,
                channel=channel,
                user_id=user_id,
                user_name=user_name,
                status_ts=status_ts,
                channel_event=channel_event,
                user_input=user_input,
                has_files=has_files,
                history=history,
                channel_adapter=channel_adapter,
                user_companies=user_companies,
                workflow_ctx=workflow_ctx,
            )
        else:
            # Non-streaming for Slack and other channels
            response = await llm_client.complete(
                messages=llm_messages,
                tools=all_tools,
                tool_choice="auto",
                store=config.IS_DEVELOPMENT,  # Store in OpenAI only in dev mode
                # Prompt caching: system prompt is static, enable 24h extended cache
                cache_key="main-chat",
                cache_retention="24h",
                call_type="main_llm",
                workflow=workflow,
                user_id=user_name,
                context=f"Channel: {channel}",
                metadata={"has_files": has_files, "message_length": len(user_input)}
            )

            # Check if there are tool calls
            if response.tool_calls:
                tool_call = response.tool_calls[0]  # Get first tool call
                logger.info(f"[LLM] Tool call: {tool_call.name}")

                # Add assistant's tool call to history so model knows what it did
                try:
                    args_dict = tool_call.arguments
                    if tool_call.name == "get_separate_proposals":
                        locations = [p.get("location", "unknown") for p in args_dict.get("proposals", [])]
                        client = args_dict.get("client_name", "unknown")
                        assistant_summary = f"[Generated separate proposals for {client}: {', '.join(locations)}]"
                    elif tool_call.name == "get_combined_proposal":
                        locations = [p.get("location", "unknown") for p in args_dict.get("proposals", [])]
                        client = args_dict.get("client_name", "unknown")
                        assistant_summary = f"[Generated combined proposal for {client}: {', '.join(locations)}]"
                    elif tool_call.name == "generate_mockup":
                        location = args_dict.get("location", "unknown")
                        assistant_summary = f"[Generated mockup for {location}]"
                    elif tool_call.name == "parse_booking_order":
                        assistant_summary = "[Parsed booking order]"
                    else:
                        assistant_summary = f"[Called {tool_call.name}]"
                except (KeyError, TypeError, AttributeError):
                    assistant_summary = f"[Called {tool_call.name}]"
                history.append({"role": "assistant", "content": assistant_summary, "timestamp": datetime.now().isoformat()})

                # Dispatch to tool router
                from handlers.tool_router import handle_tool_call
                handled = await handle_tool_call(
                    tool_call=tool_call,
                    channel=channel,
                    user_id=user_id,
                    status_ts=status_ts,
                    channel_event=channel_event,
                    user_input=user_input,
                    download_file_func=download_file,
                    handle_booking_order_parse_func=_handle_booking_order_parse,
                    generate_mockup_queued_func=_generate_mockup_queued,
                    generate_ai_mockup_queued_func=_generate_ai_mockup_queued,
                    user_companies=user_companies,
                    workflow_ctx=workflow_ctx,
                )
                if handled:
                    user_history[user_id] = history[-10:]
                    return
            elif response.content:
                # Text response (no tool call)
                reply = response.content
                # Add assistant's text reply to history
                history.append({"role": "assistant", "content": reply, "timestamp": datetime.now().isoformat()})
                # Format any markdown-style text from the LLM
                formatted_reply = reply
                # Ensure bullet points are properly formatted
                formatted_reply = formatted_reply.replace('\n- ', '\n• ')
                formatted_reply = formatted_reply.replace('\n* ', '\n• ')
                # Ensure headers are bolded
                import re
                formatted_reply = re.sub(r'^(For .+:)$', r'**\1**', formatted_reply, flags=re.MULTILINE)
                formatted_reply = re.sub(r'^([A-Z][A-Z\s]+:)$', r'**\1**', formatted_reply, flags=re.MULTILINE)
                # Delete status message before sending reply
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                await channel_adapter.send_message(channel_id=channel, content=formatted_reply)
            else:
                # No content and no tool calls
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                await channel_adapter.send_message(channel_id=channel, content="I can help with proposals or add locations. Say 'add location'.")
                return

        user_history[user_id] = history[-10:]

    except Exception as e:
        config.logger.error(f"LLM loop error: {e}", exc_info=True)
        # Try to delete status message if it exists
        try:
            if 'status_ts' in locals() and status_ts and channel_adapter:
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        except Exception as cleanup_err:
            logger.debug(f"[LLM] Failed to delete status message during error cleanup: {cleanup_err}")
        channel_adapter = config.get_channel_adapter()
        if channel_adapter:
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** Something went wrong. Please try again.")
