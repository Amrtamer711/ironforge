import json
import asyncio
from typing import Dict, Any, Optional, List
import os
from pathlib import Path
import aiohttp
from datetime import datetime, timedelta
from pptx import Presentation
import shutil

import config
from db.database import db
from core.proposals import process_proposals
from integrations.slack.formatting import SlackResponses
from workflows.bo_parser import BookingOrderParser, COMBINED_BOS_DIR
from utils.task_queue import mockup_queue
from integrations.slack import bo_messaging as bo_slack_messaging
from integrations.slack.file_utils import _download_slack_file, _validate_pdf_file
from integrations.llm.prompts.bo_editing import get_bo_edit_prompt
from db.cache import (
    user_history,
    pending_location_additions,
    mockup_history,
    pending_booking_orders,
    cleanup_expired_mockups,
    store_mockup_history,
    get_mockup_history,
    get_location_frame_count,
)


async def _generate_mockup_queued(
    location_key: str,
    creative_paths: list,
    time_of_day: str,
    finish: str,
    specific_photo: str = None,
    config_override: dict = None
):
    """
    Wrapper function for mockup generation that runs through the task queue.
    This limits concurrent mockup generation to prevent memory exhaustion.

    Args:
        location_key: Location identifier
        creative_paths: List of creative file paths
        time_of_day: Time of day variation
        finish: Finish type
        specific_photo: Optional specific photo to use
        config_override: Optional config override

    Returns:
        Tuple of (result_path, metadata)
    """
    from generators import mockup as mockup_generator
    import gc

    logger = config.logger
    logger.info(f"[QUEUE] Mockup generation requested for {location_key}")

    # This function will be queued and executed when a slot is available
    async def _generate():
        try:
            logger.info(f"[QUEUE] Starting mockup generation for {location_key}")
            result_path, metadata = mockup_generator.generate_mockup(
                location_key,
                creative_paths,
                time_of_day=time_of_day,
                finish=finish,
                specific_photo=specific_photo,
                config_override=config_override
            )
            logger.info(f"[QUEUE] Mockup generation completed for {location_key}")
            gc.collect()
            return result_path, metadata
        except Exception as e:
            logger.error(f"[QUEUE] Mockup generation failed for {location_key}: {e}")
            raise

    # Submit to queue and wait for result
    return await mockup_queue.submit(_generate)


async def _generate_ai_mockup_queued(
    ai_prompts: List[str],
    enhanced_prompt_template: str,
    location_key: str,
    time_of_day: str,
    finish: str,
    user_id: Optional[str] = None
):
    """
    Wrapper for AI mockup generation (AI creative generation + mockup) through the queue.
    This ensures the entire AI workflow (fetch from OpenAI + image processing + mockup)
    is treated as ONE queued task to prevent memory spikes.

    Args:
        ai_prompts: List of AI prompts (1 for tiled, N for multi-frame)
        enhanced_prompt_template: Full enhanced system prompt template with placeholder
        location_key: Location identifier
        time_of_day: Time of day variation
        finish: Finish type
        user_id: Optional Slack user ID for cost tracking

    Returns:
        Tuple of (result_path, ai_creative_paths)
    """
    from generators import mockup as mockup_generator
    import gc

    logger = config.logger
    num_prompts = len(ai_prompts)
    logger.info(f"[QUEUE] AI mockup requested for {location_key} ({num_prompts} prompt(s))")

    async def _generate():
        try:
            logger.info(f"[QUEUE] Generating {num_prompts} AI creative(s) for {location_key} in parallel")

            # Build all prompts first
            full_prompts = []
            for i, user_prompt in enumerate(ai_prompts, 1):
                # Inject user's prompt into the enhanced template
                # Note: template uses {USER_PROMPT} (single braces) because f-string converts {{ to {
                full_prompt = enhanced_prompt_template.replace("{USER_PROMPT}", user_prompt)
                full_prompts.append(full_prompt)

            # Generate all creatives in parallel (asyncio.gather preserves order)
            logger.info(f"[AI QUEUE] Executing {num_prompts} image generation(s) in parallel...")
            creative_tasks = [
                mockup_generator.generate_ai_creative(
                    prompt=prompt,
                    location_key=location_key,
                    user_id=user_id
                )
                for prompt in full_prompts
            ]
            ai_creative_paths = await asyncio.gather(*creative_tasks)

            # Check if any failed
            for i, creative_path in enumerate(ai_creative_paths, 1):
                if not creative_path:
                    raise Exception(f"Failed to generate AI creative {i}/{num_prompts}")

            logger.info(f"[QUEUE] All AI creatives ready, generating mockup for {location_key}")

            # Generate mockup with AI creatives
            result_path, metadata = mockup_generator.generate_mockup(
                location_key,
                ai_creative_paths,
                time_of_day=time_of_day,
                finish=finish
            )

            if not result_path:
                raise Exception("Failed to generate mockup")

            logger.info(f"[QUEUE] AI mockup completed for {location_key}")
            gc.collect()
            return result_path, ai_creative_paths

        except Exception as e:
            logger.error(f"[QUEUE] AI mockup failed for {location_key}: {e}")
            raise

    # Submit entire AI workflow to queue as ONE task
    return await mockup_queue.submit(_generate)


async def _persist_location_upload(location_key: str, pptx_path: Path, metadata_text: str) -> None:
    location_dir = config.TEMPLATES_DIR / location_key
    location_dir.mkdir(parents=True, exist_ok=True)
    target_pptx = location_dir / f"{location_key}.pptx"
    target_meta = location_dir / "metadata.txt"
    # Move/copy files
    import shutil
    shutil.move(str(pptx_path), str(target_pptx))
    target_meta.write_text(metadata_text, encoding="utf-8")


async def _handle_booking_order_parse(
    company: str,
    slack_event: Dict[str, Any],
    channel: str,
    status_ts: str,
    user_notes: str,
    user_id: str,
    user_message: str = ""
):
    """Handle booking order parsing workflow"""
    logger = config.logger

    # Extract files from slack event
    files = slack_event.get("files", [])
    if not files and slack_event.get("subtype") == "file_share" and "file" in slack_event:
        files = [slack_event["file"]]

    if not files:
        await config.slack_client.chat_update(
            channel=channel,
            ts=status_ts,
            text=config.markdown_to_slack("❌ No file detected. Please upload a booking order document (Excel, PDF, or image).")
        )
        return

    file_info = files[0]
    logger.info(f"[BOOKING] Processing file: {file_info.get('name')}")

    # Download file
    try:
        tmp_file = await _download_slack_file(file_info)
    except Exception as e:
        logger.error(f"[BOOKING] Download failed: {e}")
        await config.slack_client.chat_update(
            channel=channel,
            ts=status_ts,
            text=config.markdown_to_slack(f"❌ Failed to download file: {e}")
        )
        return

    # Initialize parser
    parser = BookingOrderParser(company=company)
    file_type = parser.detect_file_type(tmp_file)

    # Classify document
    try:
        await config.slack_client.chat_update(channel=channel, ts=status_ts, text="⏳ _Classifying document..._")
    except Exception as e:
        logger.error(f"[SLACK] Failed to update status message while classifying: {e}", exc_info=True)
        # Continue processing - status update failure shouldn't stop the workflow

    # Convert user_id to user_name for cost tracking
    from integrations.slack.bo_messaging import get_user_real_name
    user_name = await get_user_real_name(user_id) if user_id else None

    classification = await parser.classify_document(tmp_file, user_message=user_message, user_id=user_name)
    logger.info(f"[BOOKING] Classification: {classification}")

    # Check if it's actually a booking order
    if classification.get("classification") != "BOOKING_ORDER" or classification.get("confidence") in {"low", None}:
        try:
            await config.slack_client.chat_update(
                channel=channel,
                ts=status_ts,
                text=config.markdown_to_slack(
                    f"⚠️ This doesn't look like a booking order (confidence: {classification.get('confidence', 'unknown')}).\n\n"
                    f"Reasoning: {classification.get('reasoning', 'N/A')}\n\n"
                    f"If this is artwork for a mockup, please request a mockup instead."
                )
            )
        except Exception as e:
            logger.error(f"[SLACK] Failed to send classification result to user: {e}", exc_info=True)
        tmp_file.unlink(missing_ok=True)
        return

    # Parse the booking order
    # TODO: Re-enable timeout protection once we optimize parsing speed
    # Current issue: High reasoning effort can take 10-15+ minutes on complex BOs
    try:
        await config.slack_client.chat_update(channel=channel, ts=status_ts, text="⏳ _Extracting booking order data..._")
    except Exception as e:
        logger.error(f"[SLACK] Failed to update status message while parsing: {e}", exc_info=True)
    try:
        # Timeout temporarily disabled to allow high reasoning effort to complete
        # result = await asyncio.wait_for(
        #     parser.parse_file(tmp_file, file_type, user_message=user_message, user_id=user_name),
        #     timeout=900.0
        # )
        result = await parser.parse_file(tmp_file, file_type, user_message=user_message, user_id=user_name)
    # except asyncio.TimeoutError:
    #     logger.error(f"[BOOKING] Parsing timed out after 15 minutes", exc_info=True)
    #     try:
    #         await config.slack_client.chat_update(
    #             channel=channel,
    #             ts=status_ts,
    #             text=config.markdown_to_slack(
    #                 f"❌ **Error:** Sorry, OpenAI took too long and seems to be hanging.\n\n"
    #                 f"Please try uploading the booking order again. If this persists, contact the AI team."
    #             )
    #         )
    #     except Exception as slack_error:
    #         logger.error(f"[SLACK] Failed to send timeout error to user: {slack_error}", exc_info=True)
    #     tmp_file.unlink(missing_ok=True)
    #     return
    except Exception as e:
        logger.error(f"[BOOKING] Parsing failed: {e}", exc_info=True)
        try:
            await config.slack_client.chat_update(
                channel=channel,
                ts=status_ts,
                text=config.markdown_to_slack(
                    f"❌ **Error:** Failed to extract data from the booking order.\n\n"
                    f"If you believe this is a bug, please contact the AI team with the timestamp: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}`"
                )
            )
        except Exception as slack_error:
            logger.error(f"[SLACK] Failed to send parsing error to user: {slack_error}", exc_info=True)
        tmp_file.unlink(missing_ok=True)
        return

    # NEW FLOW: Generate Excel immediately and send with Approve/Reject buttons
    try:
        await config.slack_client.chat_update(channel=channel, ts=status_ts, text="⏳ _Generating Excel file..._")
    except Exception as e:
        logger.error(f"[SLACK] Failed to update status message while generating Excel: {e}", exc_info=True)

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
                await config.slack_client.chat_update(
                    channel=channel,
                    ts=status_ts,
                    text=config.markdown_to_slack(f"❌ **Error:** Sales Coordinator for {company} not configured. Please contact the AI team to set this up.")
                )
            except Exception as e:
                logger.error(f"[SLACK] Failed to send config error to user: {e}", exc_info=True)
            return

        # Send Excel + summary + Approve/Reject buttons to coordinator
        submitter_name = await bo_slack_messaging.get_user_real_name(user_id)
        preview_text = f"📋 **New Booking Order - Ready for Approval**\n\n"
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
            await config.slack_client.chat_update(channel=channel, ts=status_ts, text="⏳ _Sending to coordinator..._")
        except Exception as e:
            logger.error(f"[SLACK] Failed to update status message: {e}", exc_info=True)

        logger.info(f"[BO APPROVAL] Posting notification to coordinator channel: {coordinator_channel}")

        # Get submitter's real name
        submitter_name = await bo_slack_messaging.get_user_real_name(user_id)

        # Step 1: Post notification message in main channel
        notification_text = (
            f"📋 **New Booking Order Submitted**\n\n"
            f"**Client:** {result.data.get('client', 'N/A')}\n"
            f"**Campaign:** {result.data.get('brand_campaign', 'N/A')}\n"
            f"**Gross Total:** AED {result.data.get('gross_calc', 0):,.2f}\n\n"
            f"**Submitted by:** {submitter_name}\n\n"
            f"_Please review the details in the thread below..._"
        )

        notification_msg = await config.slack_client.chat_postMessage(
            channel=coordinator_channel,
            text=config.markdown_to_slack(notification_text)
        )
        notification_ts = notification_msg["ts"]
        logger.info(f"[BO APPROVAL] Posted notification with ts: {notification_ts}")

        # Step 2: Upload combined PDF file as threaded reply
        logger.info(f"[BO APPROVAL] Uploading combined PDF in thread...")
        try:
            file_upload = await config.slack_client.files_upload_v2(
                channel=coordinator_channel,
                file=str(combined_pdf_path),
                title=f"BO Draft - {result.data.get('client', 'Unknown')}",
                initial_comment=config.markdown_to_slack(preview_text),
                thread_ts=notification_ts  # Post in thread
            )
            logger.info(f"[BO APPROVAL] Combined PDF uploaded in thread successfully")
        except Exception as upload_error:
            logger.error(f"[BO APPROVAL] Failed to upload combined PDF: {upload_error}", exc_info=True)
            raise Exception(f"Failed to send combined PDF to coordinator. Channel/User ID: {coordinator_channel}")

        # Wait for file to fully appear in Slack before posting buttons
        logger.info(f"[BO APPROVAL] Waiting 10 seconds for file to render in Slack...")
        await asyncio.sleep(10)

        # Step 3: Post buttons in the same thread
        logger.info(f"[BO APPROVAL] Posting approval buttons in thread...")
        button_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "📎 *Please review the PDF above (Excel + Original BO), then:*"
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
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🚫 Cancel"},
                        "value": workflow_id,
                        "action_id": "cancel_bo_coordinator"
                    }
                ]
            }
        ]

        button_msg = await config.slack_client.chat_postMessage(
            channel=coordinator_channel,
            thread_ts=notification_ts,  # Post in same thread
            text="Please review and approve or reject:",
            blocks=button_blocks
        )
        coordinator_msg_ts = button_msg["ts"]
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
            await config.slack_client.chat_update(
                channel=channel,
                ts=status_ts,
                text=config.markdown_to_slack(
                    f"✅ **Booking Order Submitted**\n\n"
                    f"**Client:** {result.data.get('client', 'N/A')}\n"
                    f"**Campaign:** {result.data.get('brand_campaign', 'N/A')}\n"
                    f"**Gross Total:** AED {result.data.get('gross_calc', 0):,.2f}\n\n"
                    f"Your booking order has been sent to the Sales Coordinator with a combined PDF (parsed data + original BO) for immediate review. "
                    f"You'll be notified once the approval process is complete."
                )
            )
        except Exception as e:
            logger.error(f"[SLACK] Failed to send success message to user: {e}", exc_info=True)

        logger.info(f"[BO APPROVAL] Sent {workflow_id} to coordinator with combined PDF and approval buttons")

    except Exception as e:
        logger.error(f"[BO APPROVAL] Error creating workflow: {e}", exc_info=True)
        try:
            await config.slack_client.chat_update(
                channel=channel,
                ts=status_ts,
                text=config.markdown_to_slack(
                    f"❌ **Error:** Failed to start the approval workflow.\n\n"
                    f"If you believe this is a bug, please contact the AI team with the timestamp: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}`"
                )
            )
        except Exception as slack_error:
            logger.error(f"[SLACK] Failed to send workflow error to user: {slack_error}", exc_info=True)


async def handle_booking_order_edit_flow(channel: str, user_id: str, user_input: str) -> str:
    """Handle booking order edit flow with structured LLM response"""
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

        res = await config.openai_client.responses.create(
            model=config.OPENAI_MODEL,
            input=[{"role": "system", "content": system_prompt}],
            text={
                'format': {
                    'type': 'json_schema',
                    'name': 'booking_order_edit_response',
                    'strict': False,
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'action': {'type': 'string', 'enum': ['approve', 'cancel', 'edit', 'view']},
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
                                'additionalProperties': True  # Allow locations and other fields
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

        decision = json.loads(res.output_text)
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
                result = await bo_slack_messaging.send_to_coordinator(
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


async def main_llm_loop(channel: str, user_id: str, user_input: str, slack_event: Dict[str, Any] = None):
    logger = config.logger
    
    # Debug logging
    logger.info(f"[MAIN_LLM] Starting for user {user_id}, pending_adds: {list(pending_location_additions.keys())}")
    if slack_event:
        logger.info(f"[MAIN_LLM] Slack event keys: {list(slack_event.keys())}")
        if "files" in slack_event:
            logger.info(f"[MAIN_LLM] Files found: {len(slack_event['files'])}")
    
    # Check if message is in a coordinator thread (before sending status message)
    thread_ts = slack_event.get("thread_ts") if slack_event else None
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
                            await config.slack_client.chat_postMessage(
                                channel=channel,
                                thread_ts=thread_ts,
                                text=config.markdown_to_slack(answer)
                            )
                    except Exception as e:
                        logger.error(f"[BO APPROVAL] Error in coordinator thread handler: {e}", exc_info=True)
                        await config.slack_client.chat_postMessage(
                            channel=channel,
                            thread_ts=thread_ts,
                            text=config.markdown_to_slack(f"❌ **Error:** {str(e)}")
                        )
                    return  # Exit early, don't process as normal message
                else:
                    # Thread exists but not active yet (user hasn't rejected)
                    logger.info(f"[BO APPROVAL] Message in coordinator thread for {workflow_id} but thread not active - reminding user to use buttons")
                    await config.slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        text=config.markdown_to_slack(
                            "⚠️ **Please use the Approve or Reject buttons first**\n\n"
                            "To make edits to this booking order, click the **❌ Reject** button above. "
                            "This will open the thread for editing.\n\n"
                            "If the BO looks good, click **✅ Approve** to send it to the next stage."
                        )
                    )
                    return  # Exit early, don't process as normal message

    # Send initial status message
    status_message = await config.slack_client.chat_postMessage(
        channel=channel,
        text="⏳ _Please wait..._"
    )
    status_ts = status_message.get("ts")

    # OLD EDIT FLOW REMOVED - Now coordinators edit directly in threads

    # Check if user has a pending location addition or mockup request and uploaded a file
    # Also check for file_share events which Slack sometimes uses
    has_files = slack_event and ("files" in slack_event or (slack_event.get("subtype") == "file_share"))

    # Note: Mockup generation is now handled in one step within the tool handler
    # No need for pending state - users must upload image WITH request or provide AI prompt

    if user_id in pending_location_additions and has_files:
        pending_data = pending_location_additions[user_id]

        # Check if pending request is still valid (10 minute window)
        timestamp = pending_data.get("timestamp")
        if timestamp and (datetime.now() - timestamp) > timedelta(minutes=10):
            del pending_location_additions[user_id]
            logger.warning(f"[LOCATION_ADD] Pending location expired for user {user_id}")
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack("❌ **Error:** Location upload session expired (10 minute limit). Please restart the location addition process.")
            )
            return

        logger.info(f"[LOCATION_ADD] Found pending location for user {user_id}: {pending_data['location_key']}")
        logger.info(f"[LOCATION_ADD] Files in event: {len(slack_event.get('files', []))}")
        
        # Check if any of the files is a PDF (we'll convert it to PPTX)
        pptx_file = None
        files = slack_event.get("files", [])

        # If it's a file_share event, files might be structured differently
        if not files and slack_event.get("subtype") == "file_share" and "file" in slack_event:
            files = [slack_event["file"]]
            logger.info(f"[LOCATION_ADD] Using file from file_share event")

        for f in files:
            logger.info(f"[LOCATION_ADD] Checking file: name={f.get('name')}, filetype={f.get('filetype')}, mimetype={f.get('mimetype')}")

            # Accept PDF files (new) - will be converted to PPTX
            if f.get("filetype") == "pdf" or f.get("mimetype") == "application/pdf" or f.get("name", "").lower().endswith(".pdf"):
                try:
                    pdf_file = await _download_slack_file(f)
                except Exception as e:
                    logger.error(f"Failed to download PDF file: {e}")
                    await config.slack_client.chat_postMessage(
                        channel=channel,
                        text=config.markdown_to_slack("❌ **Error:** Failed to download the PDF file. Please try again.")
                    )
                    return

                # Validate it's actually a PDF file
                if not _validate_pdf_file(pdf_file):
                    logger.error(f"Invalid PDF file: {f.get('name')}")
                    try:
                        os.unlink(pdf_file)
                    except:
                        pass
                    await config.slack_client.chat_postMessage(
                        channel=channel,
                        text=config.markdown_to_slack("❌ **Error:** The uploaded file is not a valid PDF. Please upload a .pdf file.")
                    )
                    return

                # Post status message about conversion
                conversion_status = await config.slack_client.chat_postMessage(
                    channel=channel,
                    text="⏳ _Converting PDF to PowerPoint with maximum quality (300 DPI)..._"
                )

                # Convert PDF to PPTX
                logger.info(f"[LOCATION_ADD] Converting PDF to PPTX...")
                pptx_file = await _convert_pdf_to_pptx(pdf_file)

                # Clean up original PDF
                try:
                    os.unlink(pdf_file)
                except:
                    pass

                # Delete conversion status message
                await config.slack_client.chat_delete(channel=channel, ts=conversion_status["ts"])

                if not pptx_file:
                    await config.slack_client.chat_postMessage(
                        channel=channel,
                        text=config.markdown_to_slack("❌ **Error:** Failed to convert PDF to PowerPoint. Please try again or contact support.")
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
                # Save the location
                await _persist_location_upload(pending_data['location_key'], pptx_file, metadata_text)
                
                # Clean up
                del pending_location_additions[user_id]
                
                # Refresh templates
                config.refresh_templates()
                
                # Delete status message
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(
                        f"✅ **Successfully added location `{pending_data['location_key']}`**\n\n"
                        f"The location is now available for use in proposals."
                    )
                )
                return
            except Exception as e:
                logger.error(f"Failed to save location: {e}")
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack("❌ **Error:** Failed to save the location. Please try again.")
                )
                # Clean up the temporary file
                try:
                    os.unlink(pptx_file)
                except:
                    pass
                return
        else:
            # No PPT file found, cancel the addition
            del pending_location_additions[user_id]
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(
                    "❌ **Location addition cancelled.**\n\n"
                    "No PowerPoint file was found in your message. Please start over with 'add location' if you want to try again."
                )
            )
            return

    # Check for location deletion confirmation
    if user_input.strip().lower().startswith("confirm delete ") and config.is_admin(user_id):
        location_key = user_input.strip().lower().replace("confirm delete ", "").strip()

        if location_key in config.LOCATION_METADATA:
            location_dir = config.TEMPLATES_DIR / location_key
            display_name = config.LOCATION_METADATA[location_key].get('display_name', location_key)

            try:
                # Delete the location directory and all its contents
                import shutil
                from generators import mockup as mockup_generator

                # Delete PowerPoint templates
                if location_dir.exists():
                    shutil.rmtree(location_dir)
                    logger.info(f"[LOCATION_DELETE] Deleted location directory: {location_dir}")

                # Delete all mockup photos and database entries for this location
                mockup_dir = mockup_generator.MOCKUPS_DIR / location_key
                if mockup_dir.exists():
                    shutil.rmtree(mockup_dir)
                    logger.info(f"[LOCATION_DELETE] Deleted mockup directory: {mockup_dir}")

                # Delete all mockup frame data from database
                import db
                conn = db._connect()
                try:
                    result = conn.execute("DELETE FROM mockup_frames WHERE location_key = ?", (location_key,))
                    deleted_count = result.rowcount
                    conn.commit()
                    logger.info(f"[LOCATION_DELETE] Deleted {deleted_count} mockup frame entries from database")
                finally:
                    conn.close()

                # Refresh templates to remove from cache
                config.refresh_templates()

                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(
                        f"✅ **Location `{location_key}` successfully deleted**\n\n"
                        f"📍 **Removed:** {display_name}\n"
                        f"🗑️ **Files deleted:** PowerPoint template, metadata, and {deleted_count} mockup frames\n"
                        f"🔄 **Templates refreshed:** Location no longer available for proposals"
                    )
                )
                return
            except Exception as e:
                logger.error(f"[LOCATION_DELETE] Failed to delete location {location_key}: {e}")
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(f"❌ **Error:** Failed to delete location `{location_key}`. Please try again or check server logs.")
                )
                return
        else:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(f"❌ **Error:** Location `{location_key}` not found. Deletion cancelled.")
            )
            return

    # Handle cancellation
    if user_input.strip().lower() == "cancel" and config.is_admin(user_id):
        await config.slack_client.chat_delete(channel=channel, ts=status_ts)
        await config.slack_client.chat_postMessage(
            channel=channel,
            text=config.markdown_to_slack("✅ **Operation cancelled.**")
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
    
    # Get static and digital locations for the prompt
    static_locations = []
    digital_locations = []
    for key, meta in config.LOCATION_METADATA.items():
        display_name = meta.get('display_name', key)
        if meta.get('display_type', '').lower() == 'static':
            static_locations.append(f"{display_name} ({key})")
        elif meta.get('display_type', '').lower() == 'digital':
            digital_locations.append(f"{display_name} ({key})")

    static_list = ", ".join(static_locations) if static_locations else "None"
    digital_list = ", ".join(digital_locations) if digital_locations else "None"

    # Check if user is admin for system prompt and tool filtering
    is_admin = config.is_admin(user_id)

    prompt = (
        f"You are an AI sales assistant for BackLite Media. You provide comprehensive sales support tools including:\n"
        f"• Financial proposal generation for advertising locations\n"
        f"• Billboard mockup visualization (upload-based or AI-generated)\n"
        f"• Booking order parsing and management\n"
        f"• Location database management\n"
        f"• Sales analytics and reporting\n"
        f"• Code interpreter for calculations and data analysis\n\n"
        f"CRITICAL INSTRUCTION:\n"
        f"You are an INTERFACE to tools, NOT the executor. When users request actions:\n"
        f"- DO NOT say 'Generating now...', 'Creating proposal...', or 'Building mockup...'\n"
        f"- DO call the appropriate tool/function immediately\n"
        f"- Let the TOOL handle the actual execution\n"
        f"- Only respond with text AFTER the tool completes or if asking clarifying questions\n\n"
        f"⚠️ CONTEXT SWITCHING - CRITICAL:\n"
        f"Users frequently switch between different task types. ALWAYS analyze the CURRENT message to determine what they want NOW:\n\n"
        f"🔴 IMMEDIATE CONTEXT RESET RULES:\n"
        f"1. If user mentions NEW location names → FORGET previous proposal, generate NEW proposal with NEW locations\n"
        f"   Example: Just made 'gateway' proposal, now user says 'jawhara' → Generate JAWHARA proposal (not gateway again)\n"
        f"2. If user mentions NEW client name → FORGET previous client, use NEW client name\n"
        f"3. If user mentions NEW dates/rates → FORGET previous values, use NEW values\n"
        f"4. If user uploads a PDF after proposal request → They want BOOKING ORDER parsing, NOT proposal\n"
        f"5. If user uploads image after any request → They want MOCKUP generation, NOT previous task\n"
        f"6. Each message is a FRESH request - extract ALL parameters from CURRENT message only\n\n"
        f"🟢 HOW TO DETECT NEW REQUESTS:\n"
        f"- Look for location names in CURRENT message (gateway, jawhara, landmark, etc.)\n"
        f"- Look for proposal keywords (make, create, generate, proposal)\n"
        f"- Look for dates, rates, durations in CURRENT message\n"
        f"- If CURRENT message has complete info → Call tool immediately with NEW data\n"
        f"- If CURRENT message missing info → Ask for missing info ONLY (don't repeat previous request)\n\n"
        f"🔴 NEVER DO THIS:\n"
        f"- Don't say 'generating the same proposal as before'\n"
        f"- Don't ask 'did you mean the previous location?'\n"
        f"- Don't use location names from previous messages if CURRENT message has different locations\n"
        f"- Don't require user to explicitly say 'new proposal' or 'different location'\n\n"
        f"✅ ALWAYS DO THIS:\n"
        f"- Parse CURRENT message for ALL parameters (locations, dates, rates, client)\n"
        f"- If CURRENT message has different locations than last → Use CURRENT locations\n"
        f"- Trust CURRENT message over conversation history\n"
        f"- Call tool with parameters from CURRENT message ONLY\n\n"
        f"Today's date is: {datetime.now().strftime('%B %d, %Y')} ({datetime.now().strftime('%A')})\n"
        f"Use this date to understand relative dates like 'tomorrow', 'next week', 'next month', etc.\n\n"
        f"═══════════════════════════════════════════════════════════════════\n"
        f"📊 PROPOSAL GENERATION\n"
        f"═══════════════════════════════════════════════════════════════════\n\n"
        f"You can handle SINGLE or MULTIPLE location proposals in one request.\n\n"
        f"PACKAGE TYPES:\n"
        f"1. SEPARATE PACKAGE (default): Each location gets its own proposal slide, multiple durations/rates allowed per location\n"
        f"2. COMBINED PACKAGE: All locations in ONE proposal slide, single duration per location, one combined net rate\n\n"
        
        f"LOCATION TYPES - CRITICAL TO UNDERSTAND:\n\n"
        f"🔴 DIGITAL LOCATIONS (LED screens with rotating ads):\n"
        f"   Features: Multiple advertisers share screen time, ads rotate in loops\n"
        f"   Fee Structure: NET RATE + PRE-CONFIGURED UPLOAD FEE (automatically added)\n"
        f"   Examples: {digital_list}\n"
        f"   Upload Fee: System automatically adds the correct upload fee for each digital location\n\n"

        f"🔵 STATIC LOCATIONS (Traditional billboards, prints, physical displays):\n"
        f"   Features: Single advertiser has exclusive display, no rotation\n"
        f"   Fee Structure: NET RATE + PRODUCTION FEE (must be collected from user)\n"
        f"   Examples: {static_list}\n"
        f"   Production Fee: REQUIRED - ask user for production fee amount (e.g., 'AED 5,000')\n"
        f"   Multiple Productions: If client changes artwork during campaign (e.g., 2 productions at AED 20k each), sum them together (total: AED 40,000)\n"
        f"   ⚠️ IMPORTANT STATIC LOCATION RULES (SOFT VALIDATION - confirm with user if violated):\n"
        f"      • Start Date: Static locations are typically sold starting on the 1st of each month\n"
        f"      • Duration: Static campaigns typically run in 4-week increments (4 weeks, 8 weeks, 12 weeks, etc.)\n"
        f"      • If user requests non-standard timing (e.g., mid-month start or 3-week duration), YOU MUST:\n"
        f"        1. Inform them: 'Static locations are usually sold from the 1st of the month in 4-week increments'\n"
        f"        2. Ask for explicit confirmation: 'Please confirm these dates/duration are absolutely correct'\n"
        f"        3. Only proceed after user confirms - do NOT reject, just validate\n\n"

        f"CRITICAL RULES:\n"
        f"- DIGITAL = Upload fee (automatic) | STATIC = Production fee (ask user)\n"
        f"- NEVER ask for production fee on digital locations\n"
        f"- NEVER skip production fee on static locations\n"
        f"- If user mentions 'upload fee' for static locations, correct them to 'production fee'\n"
        f"- If multiple production fees mentioned for one location (artwork changes), sum them together\n\n"
        
        f"REQUIRED INFORMATION:\n"
        f"For SEPARATE PACKAGE (each location):\n"
        f"1. Location (must match from lists above - intelligently infer if user says 'gateway'→'dubai_gateway', 'jawhara'→'dubai_jawhara', 'the landmark'→'landmark', etc.)\n"
        f"2. Start Date\n"
        f"3. Duration Options (multiple allowed)\n"
        f"4. Net Rates for EACH duration\n"
        f"5. Fees - CHECK LOCATION TYPE:\n"
        f"   • DIGITAL locations: NO FEE NEEDED (upload fee auto-added)\n"
        f"   • STATIC locations: ASK for production fee (e.g., 'AED 5,000')\n"
        f"6. Client Name (required)\n"
        f"7. Submitted By (optional - defaults to current user)\n\n"
        f"For COMBINED PACKAGE:\n"
        f"1. All Locations (mix of digital/static allowed - intelligently infer names from available list)\n"
        f"2. Start Date for EACH location\n"
        f"3. ONE Duration per location\n"
        f"4. ONE Combined Net Rate for entire package\n"
        f"5. Fees - CHECK EACH LOCATION TYPE:\n"
        f"   • DIGITAL locations: NO FEE NEEDED (upload fees auto-added)\n"
        f"   • STATIC locations: ASK for production fee for EACH static location\n"
        f"6. Client Name (required)\n"
        f"7. Submitted By (optional - defaults to current user)\n\n"
        
        f"MULTIPLE PROPOSALS RULES:\n"
        f"- User can request proposals for multiple locations at once\n"
        f"- EACH location must have its own complete set of information\n"
        f"- EACH location must have matching number of durations and net rates\n"
        f"- Different locations can have different durations/rates\n"
        f"- Multiple proposals will be combined into a single PDF document\n\n"
        
        f"VALIDATION RULES:\n"
        f"- For EACH location, durations count MUST equal net rates count\n"
        f"- If a location has 3 duration options, it MUST have exactly 3 net rates\n"
        f"- DO NOT proceed until ALL locations have complete information\n"
        f"- Ask follow-up questions for any missing information\n"
        f"- ALWAYS ask for client name if not provided\n\n"
        
        f"PARSING EXAMPLES:\n"
        f"User: 'jawhara, oryx and triple crown special combined deal 2 mil, 2, 4 and 6 weeks respectively, 1st jan 2026, 2nd jan 2026 and 3rd'\n"
        f"Parse as: Combined package with Jawhara (2 weeks, Jan 1), Oryx (4 weeks, Jan 2), Triple Crown (6 weeks, Jan 3), total 2 million AED\n\n"
        
        f"SINGLE LOCATION EXAMPLE:\n"
        f"User: 'Proposal for landmark, Jan 1st, 2 weeks at 1.5M'\n"
        f"Bot confirms and generates one proposal\n\n"
        
        f"MULTIPLE LOCATIONS EXAMPLE:\n"
        f"User: 'I need proposals for landmark and gateway'\n"
        f"Bot: 'I'll help you create proposals for The Landmark and The Gateway. Let me get the details for each:\n\n"
        f"For THE LANDMARK:\n"
        f"- What's the campaign start date?\n"
        f"- What duration options do you want?\n"
        f"- What are the net rates for each duration?\n\n"
        f"For THE GATEWAY:\n"
        f"- What's the campaign start date?\n"
        f"- What duration options do you want?\n"
        f"- What are the net rates for each duration?'\n\n"
        
        f"COMBINED PACKAGE EXAMPLE:\n"
        f"User: 'I need a combined package for landmark, gateway, and oryx at 5 million total'\n"
        f"Bot: 'I'll create a combined package proposal. Let me confirm the details:\n\n"
        f"COMBINED PACKAGE:\n"
        f"- Locations: The Landmark, The Gateway, The Oryx\n"
        f"- Package Net Rate: AED 5,000,000\n\n"
        f"For each location, I need:\n"
        f"- Start date\n"
        f"- Duration (one per location for combined packages)\n\n"
        f"Please provide these details.'\n\n"

        f"═══════════════════════════════════════════════════════════════════\n"
        f"🎨 MOCKUP GENERATION\n"
        f"═══════════════════════════════════════════════════════════════════\n\n"
        f"MOCKUP SETUP WEBSITE: {os.getenv('RENDER_EXTERNAL_URL', 'http://localhost:3000')}/mockup\n"
        f"(Share this URL when users ask about setting up mockup frames or uploading billboard photos)\n\n"
        f"You can GENERATE MOCKUPS: Create billboard mockups with uploaded or AI-generated creatives:\n"
        f"  TWO MODES (everything must be in ONE message):\n"
        f"  A) USER UPLOAD MODE (requires image attachment):\n"
        f"     1. User UPLOADS image(s) WITH mockup request in same message\n"
        f"     2. System detects images and generates mockup immediately\n"
        f"     3. INTELLIGENT TEMPLATE SELECTION:\n"
        f"        • 1 image uploaded → Selects ANY template (image duplicated across all frames)\n"
        f"        • N images uploaded → ONLY selects templates with EXACTLY N frames\n"
        f"        • Example: Upload 3 images → system finds template with 3 frames only\n"
        f"     CRITICAL: If you see '[User uploaded X image file(s): ...]' in the message, call generate_mockup IMMEDIATELY\n"
        f"     DO NOT ask for clarification - the images are already uploaded!\n"
        f"  B) AI GENERATION MODE (NO upload needed):\n"
        f"     1. User provides location AND creative description in request\n"
        f"     2. System generates creative using gpt-image-1 model (NO upload needed)\n"
        f"     3. MULTI-FRAME AI SUPPORT:\n"
        f"        • CRITICAL: ALWAYS default to 1 prompt UNLESS user EXPLICITLY requests multiple frames\n"
        f"        • Single prompt (default): ai_prompts=['full detailed description'] → generates 1 artwork, tiled across all frames\n"
        f"        • Multi-frame (explicit only): User says '3-frame mockup' or 'show evolution' → ai_prompts=['detailed prompt 1', 'detailed prompt 2', 'detailed prompt 3']\n"
        f"        • Example DEFAULT: 'Nike ad on triple crown' → ai_prompts=['Nike athletic shoe advertisement with swoosh logo, bold \"Just Do It\" slogan, dynamic sports imagery, modern minimalist design with black and white color scheme']\n"
        f"        • Example MULTI-FRAME: 'triple crown with 3 different nike ads showing product evolution' → ai_prompts=['Nike Air Max shoe components laid out artistically - leather pieces, rubber sole, mesh fabric against dark industrial background with Nike swoosh logo prominent', 'Nike Air Max in assembly process with hands stitching components together, workshop setting with professional lighting highlighting craftsmanship and Nike branding', 'Finished Nike Air Max shoe in hero shot on gradient background, dramatic lighting, 3/4 angle showing sleek design, large Nike swoosh and \"Just Do It\" text in bold typography']\n"
        f"     4. System applies AI creative(s) to billboard and returns mockup\n"
        f"     IMPORTANT: If description provided = AI mode, ignore any uploaded images\n"
        f"  Decision Logic:\n"
        f"  - Has creative description? → Use AI mode (ignore uploads)\n"
        f"  - No description but has upload? → Use upload mode (DO NOT ASK FOR CLARIFICATION)\n"
        f"  - No description and no upload? → ERROR\n"
        f"  Examples:\n"
        f"  - [uploads creative.jpg] + 'mockup for Dubai Gateway' → uses uploaded image (IMMEDIATE)\n"
        f"  - [uploads 3 images] + 'triple crown mockup' → matches to 3-frame template (IMMEDIATE)\n"
        f"  - 'put this on triple crown' + [User uploaded 1 image file(s): test.jpg] → IMMEDIATE mockup\n"
        f"  - 'mockup for Oryx with luxury watch ad, gold and elegant' → AI generates 1 creative\n"
        f"  - 'triple crown with 3 different nike shoe ads' → AI generates 3 variations (num_ai_frames=3)\n"
        f"  - 'mockup for Gateway' (no upload, no description) → ERROR: missing creative\n"
        f"  Keywords: 'mockup', 'mock up', 'billboard preview', 'show my ad on', 'put this on', 'dual frame', 'triple frame'\n\n"

        f"═══════════════════════════════════════════════════════════════════\n"
        f"🗄️ DATABASE & LOCATION MANAGEMENT\n"
        f"═══════════════════════════════════════════════════════════════════\n\n"
        f"- ADD NEW LOCATIONS (admin only):\n"
        f"  • Admin provides ALL metadata: location_key, display_name, display_type, height, width, number_of_faces, sov, series, spot_duration, loop_duration, upload_fee (for digital)\n"
        f"  • Once validated, admin uploads the PPT template file\n"
        f"  • Location becomes immediately available for proposals\n\n"
        f"- DELETE LOCATIONS (admin only): Requires double confirmation to prevent accidents\n"
        f"- REFRESH TEMPLATES: Reload available locations from disk\n"
        f"- LIST LOCATIONS: Show all available advertising locations\n\n"

        f"═══════════════════════════════════════════════════════════════════\n"
        f"📈 ANALYTICS & REPORTING\n"
        f"═══════════════════════════════════════════════════════════════════\n\n"
        f"- EXPORT DATABASE: Export all proposals to Excel (admin only - triggered by 'excel backend' or similar)\n"
        f"- GET STATISTICS: View proposal generation summary and recent activity\n"
        f"- EDIT TASKS: Modify task management workflows\n\n"

        f"═══════════════════════════════════════════════════════════════════\n"
        f"👤 USER PERMISSIONS\n"
        f"═══════════════════════════════════════════════════════════════════\n\n"
        f"Current User: {'ADMIN' if is_admin else 'STANDARD USER'}\n\n"
        f"{'✅ ADMIN TOOLS AVAILABLE:' if is_admin else '❌ ADMIN TOOLS NOT AVAILABLE:'}\n"
        f"- Location Management (add_location, delete_location)\n"
        f"- Database Export (export_proposals_to_excel, export_booking_orders_to_excel)\n"
        f"- Fetch Booking Orders (fetch_booking_order)\n\n"
        f"✅ AVAILABLE TO ALL USERS:\n"
        f"- Booking Order Upload & Parsing (parse_booking_order)\n"
        f"- Any sales person can upload booking orders for approval\n\n"
        f"{'You have access to all admin-only tools listed above.' if is_admin else 'You do NOT have access to admin-only tools like location management or database export, but you CAN upload and parse booking orders.'}\n\n"

        f"═══════════════════════════════════════════════════════════════════\n"
        f"⚙️ SYSTEM GUIDELINES\n"
        f"═══════════════════════════════════════════════════════════════════\n\n"
        f"IMPORTANT:\n"
        f"- Use get_separate_proposals for individual location proposals with multiple duration/rate options\n"
        f"- Use get_combined_proposal for special package deals with one total price\n"
        f"- For SEPARATE packages: each location gets its own proposal slide\n"
        f"- For COMBINED packages: all locations in ONE proposal slide with ONE net rate\n"
        f"- Single location always uses get_separate_proposals\n"
        f"- When user mentions 'combined deal' or 'special package' with total price, use get_combined_proposal\n"
        f"- Format all rates as 'AED X,XXX,XXX'\n"
        f"- Parse 'mil' or 'million' as 000,000 (e.g., '2 mil' = 'AED 2,000,000')\n"
        f"- Number of spots defaults to 1 if not specified\n"
        f"CURRENCY CONVERSION:\n"
        f"- Default currency is AED - all internal calculations use AED\n"
        f"- If user requests amounts in USD, EUR, GBP, SAR, or other currencies, use the 'currency' parameter\n"
        f"- Examples: 'show in dollars', 'make it in USD', 'I need this in euros'\n"
        f"- The proposal will display all amounts in the requested currency with a note about conversion\n"
        f"FEE COLLECTION RULES (CRITICAL):\n"
        f"- DIGITAL locations: NEVER ask for fees - upload fees are automatic\n"
        f"- STATIC locations: ALWAYS ask for production fee - it's mandatory\n"
        f"- Mixed packages: Ask production fees only for static locations\n"
        f"- If confused about location type, check the lists above\n"
        f"- ALWAYS collect client name - it's required for tracking\n\n"

        f"═══════════════════════════════════════════════════════════════════\n"
        f"🎨 BILLBOARD MOCKUP GENERATION\n"
        f"═══════════════════════════════════════════════════════════════════\n\n"

        f"MOCKUP MEMORY SYSTEM (30-Minute Creative Storage):\n"
        f"When a user generates a mockup, the system stores their creative files (NOT the final mockup) for 30 minutes.\n"
        f"This enables FOLLOW-UP REQUESTS where users can apply the same creatives to different locations.\n\n"

        f"FOLLOW-UP REQUEST DETECTION:\n"
        f"If a user recently generated a mockup (within 30 min) and asks to see it on another location WITHOUT uploading new images or providing AI prompt:\n"
        f"- Examples: 'show me this on Dubai Gateway', 'apply to The Landmark', 'how would it look at Oryx'\n"
        f"- Just call generate_mockup with the new location name - the system automatically reuses stored creatives\n"
        f"- DO NOT ask them to re-upload images or provide AI prompt again\n"
        f"- The system validates frame count compatibility (3-frame creatives can't be used on 1-frame locations)\n\n"

        f"FRAME COUNT VALIDATION:\n"
        f"- Multi-frame locations (2, 3, or more frames) require matching number of creatives\n"
        f"- If user has 3-frame creatives in memory but requests 1-frame location → system shows error automatically\n"
        f"- If frame mismatch error occurs, explain user needs to upload correct number of images OR use AI generation\n\n"

        f"MOCKUP GENERATION MODES:\n"
        f"1. UPLOAD MODE: User uploads image file(s) → Call generate_mockup IMMEDIATELY, no questions\n"
        f"   - Takes priority over everything else\n"
        f"   - Replaces any stored creatives with new upload\n"
        f"   - DO NOT ask for clarification if user uploads images with location mention\n\n"

        f"2. AI MODE: User provides creative description (no upload) → Call generate_mockup with ai_prompts array\n"
        f"   - Example: 'mockup for Dubai Gateway with luxury watch ad, gold and elegant' → ai_prompts=['luxury watch ad with gold and elegant styling']\n"
        f"   - Default to single prompt unless user explicitly requests multiple frames\n"
        f"   - System generates flat artwork designs (NOT photos of billboards)\n\n"

        f"3. FOLLOW-UP MODE: User requests different location (no upload, no AI, within 30 min)\n"
        f"   - Example: 'show me this on The Landmark'\n"
        f"   - Just call generate_mockup with new location - system handles rest\n"
        f"   - User doesn't need to specify they want to reuse creatives\n\n"

        f"CRITICAL MOCKUP RULES:\n"
        f"- If user uploads images AND mentions location → Call generate_mockup IMMEDIATELY\n"
        f"- Don't ask 'which mockup' or 'which creative' for follow-ups - system knows\n"
        f"- Frame count errors are handled automatically - just relay system message\n"
        f"- After 30 minutes, stored creatives expire - user must upload/generate again"
    )

    # Check if user uploaded files and append to message
    user_message_content = user_input
    image_files = []  # Initialize outside conditional block
    document_files = []  # For PDFs, Excel, etc.

    if has_files and slack_event:
        files = slack_event.get("files", [])
        if not files and slack_event.get("subtype") == "file_share" and "file" in slack_event:
            files = [slack_event["file"]]

        # Check for image files and document files
        for f in files:
            filetype = f.get("filetype", "")
            mimetype = f.get("mimetype", "")
            filename = f.get("name", "").lower()

            # Image files (for mockups)
            if (filetype in ["jpg", "jpeg", "png", "gif", "bmp"] or
                mimetype.startswith("image/") or
                any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp"])):
                image_files.append(f.get("name", "image"))
            # Document files (for booking orders, proposals, etc.)
            elif (filetype in ["pdf", "xlsx", "xls", "csv", "docx", "doc"] or
                  mimetype in ["application/pdf", "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"] or
                  any(filename.endswith(ext) for ext in [".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc"])):
                document_files.append(f.get("name", "document"))

        # PRE-ROUTING CLASSIFIER: Classify and route files before LLM
        if len(files) == 1:
            logger.info(f"[PRE-ROUTER] Single file upload detected, running classification...")

            try:
                file_info = files[0]

                # Download file
                tmp_file = await _download_slack_file(file_info)
                logger.info(f"[PRE-ROUTER] Downloaded: {tmp_file}")

                # Classify using existing classifier (converts to PDF, sends to OpenAI, returns classification)
                from workflows.bo_parser import BookingOrderParser
                from integrations.slack.bo_messaging import get_user_real_name
                user_name = await get_user_real_name(user_id) if user_id else None
                parser = BookingOrderParser(company="backlite")  # Company will be determined by classifier
                classification = await parser.classify_document(tmp_file, user_message=user_input, user_id=user_name)

                logger.info(f"[PRE-ROUTER] Classification: {classification}")

                # Route based on HIGH confidence only
                if classification.get("classification") == "BOOKING_ORDER" and classification.get("confidence") == "high":
                    company = classification.get("company", "backlite")  # Get company from classifier
                    logger.info(f"[PRE-ROUTER] HIGH CONFIDENCE BOOKING ORDER ({company}) - routing directly")

                    # Route to booking order parser
                    await _handle_booking_order_parse(
                        company=company,
                        slack_event=slack_event,
                        channel=channel,
                        status_ts=status_ts,
                        user_notes="",
                        user_id=user_id,
                        user_message=user_input
                    )
                    return  # Exit early - don't call LLM

                elif classification.get("classification") == "ARTWORK" and classification.get("confidence") == "high":
                    logger.info(f"[PRE-ROUTER] HIGH CONFIDENCE ARTWORK - letting LLM handle mockup")
                    tmp_file.unlink(missing_ok=True)
                    # Clear document_files and set as image for LLM to handle as mockup
                    document_files.clear()
                    if not image_files:  # If not already marked as image
                        image_files.append(file_info.get("name", "artwork"))
                    # Fall through to LLM for mockup generation

                else:
                    logger.info(f"[PRE-ROUTER] Low/medium confidence - letting LLM decide")
                    tmp_file.unlink(missing_ok=True)
                    # Fall through to LLM

            except Exception as e:
                logger.error(f"[PRE-ROUTER] Classification/routing failed: {e}", exc_info=True)
                # Fall through to LLM on error

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
    # Remove timestamp from messages sent to OpenAI
    messages_for_openai = [{"role": msg["role"], "content": msg["content"]} for msg in history if "role" in msg and "content" in msg]
    messages = [{"role": "developer", "content": prompt}] + messages_for_openai

    # Base tools available to all users
    tools = [
        {
            "type": "function",
            "name": "get_separate_proposals",
            "description": "Generate SEPARATE proposals - each location gets its own proposal slide with multiple duration/rate options. Use this when user asks to 'make', 'create', or 'generate' proposals for specific locations. Returns individual PPTs and combined PDF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string", "description": "The location name - intelligently match to available locations. If user says 'gateway' or 'the gateway', match to 'dubai_gateway'. If user says 'jawhara', match to 'dubai_jawhara'. Use your best judgment to infer the correct location from the available list even if the name is abbreviated or has 'the' prefix."},
                                "start_date": {"type": "string", "description": "Start date for the campaign (e.g., 1st December 2025)"},
                                "end_date": {"type": "string", "description": "End date for the campaign. Either extract from user message if provided, or calculate from start_date + duration (e.g., start: 1st Dec + 4 weeks = end: 29th Dec). Use the first/shortest duration if multiple durations provided."},
                                "durations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of duration options (e.g., ['2 Weeks', '4 Weeks', '6 Weeks'])"
                                },
                                "net_rates": {
                                    "type": "array", 
                                    "items": {"type": "string"},
                                    "description": "List of net rates corresponding to each duration (e.g., ['AED 1,250,000', 'AED 2,300,000', 'AED 3,300,000'])"
                                },
                                "spots": {"type": "integer", "description": "Number of spots (default: 1)", "default": 1},
                                "production_fee": {"type": "string", "description": "Production fee for static locations (e.g., 'AED 5,000'). If multiple production fees are mentioned (client changing artwork during campaign), sum them together (e.g., two productions at AED 20,000 each = 'AED 40,000'). Required for static locations."}
                            },
                            "required": ["location", "start_date", "end_date", "durations", "net_rates"]
                        },
                        "description": "Array of proposal objects. Each location can have multiple duration/rate options."
                    },
                    "client_name": {
                        "type": "string",
                        "description": "Name of the client (required)"
                    },
                    "payment_terms": {
                        "type": "string",
                        "description": "Payment terms for the proposal (default: '100% upfront'). ALWAYS validate with user even if not explicitly mentioned. Examples: '100% upfront', '50% upfront, 50% on delivery', '30 days net'",
                        "default": "100% upfront"
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency for displaying amounts (default: 'AED'). Use if user requests amounts in a different currency like 'USD', 'EUR', 'GBP', 'SAR', etc. The proposal will show all amounts converted to this currency with a note about the conversion.",
                        "default": "AED"
                    }
                },
                "required": ["proposals", "client_name", "payment_terms"]
            }
        },
        {
            "type": "function",
            "name": "get_combined_proposal",
            "description": "Generate COMBINED package proposal - all locations in ONE slide with single net rate. Use this when user asks for a 'package', 'bundle', or 'combined' deal with multiple locations sharing one total rate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string", "description": "The location name - intelligently match to available locations. If user says 'gateway' or 'the gateway', match to 'dubai_gateway'. If user says 'jawhara', match to 'dubai_jawhara'. Use your best judgment to infer the correct location from the available list even if the name is abbreviated or has 'the' prefix."},
                                "start_date": {"type": "string", "description": "Start date for this location (e.g., 1st January 2026)"},
                                "end_date": {"type": "string", "description": "End date for this location. Either extract from user message if provided, or calculate from start_date + duration (e.g., start: 1st Jan + 2 weeks = end: 15th Jan)."},
                                "duration": {"type": "string", "description": "Duration for this location (e.g., '2 Weeks')"},
                                "spots": {"type": "integer", "description": "Number of spots (default: 1)", "default": 1},
                                "production_fee": {"type": "string", "description": "Production fee for static locations (e.g., 'AED 5,000'). If multiple production fees are mentioned (client changing artwork during campaign), sum them together (e.g., two productions at AED 20,000 each = 'AED 40,000'). Required for static locations."}
                            },
                            "required": ["location", "start_date", "end_date", "duration"]
                        },
                        "description": "Array of locations with their individual durations and start dates"
                    },
                    "combined_net_rate": {
                        "type": "string",
                        "description": "The total net rate for the entire package (e.g., 'AED 2,000,000')"
                    },
                    "client_name": {
                        "type": "string",
                        "description": "Name of the client (required)"
                    },
                    "payment_terms": {
                        "type": "string",
                        "description": "Payment terms for the proposal (default: '100% upfront'). ALWAYS validate with user even if not explicitly mentioned. Examples: '100% upfront', '50% upfront, 50% on delivery', '30 days net'",
                        "default": "100% upfront"
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency for displaying amounts (default: 'AED'). Use if user requests amounts in a different currency like 'USD', 'EUR', 'GBP', 'SAR', etc. The proposal will show all amounts converted to this currency with a note about the conversion.",
                        "default": "AED"
                    }
                },
                "required": ["proposals", "combined_net_rate", "client_name", "payment_terms"]
            }
        },
        {"type": "function", "name": "refresh_templates", "parameters": {"type": "object", "properties": {}}},
        {"type": "function", "name": "edit_task_flow", "parameters": {"type": "object", "properties": {"task_number": {"type": "integer"}, "task_data": {"type": "object"}}, "required": ["task_number", "task_data"]}},
        {
            "type": "function",
            "name": "add_location",
            "description": "Add a new location. Admin must provide ALL required metadata upfront. Digital locations require: sov, spot_duration, loop_duration, upload_fee. Static locations don't need these fields. ADMIN ONLY.", 
            "parameters": {
                "type": "object", 
                "properties": {
                    "location_key": {"type": "string", "description": "Folder/key name (lowercase, underscores for spaces, e.g., 'dubai_gateway')"},
                    "display_name": {"type": "string", "description": "Display name shown to users (e.g., 'The Dubai Gateway')"},
                    "display_type": {"type": "string", "enum": ["Digital", "Static"], "description": "Display type - determines which fields are required"},
                    "height": {"type": "string", "description": "Height with unit (e.g., '6m', '14m')"},
                    "width": {"type": "string", "description": "Width with unit (e.g., '12m', '7m')"},
                    "number_of_faces": {"type": "integer", "description": "Number of display faces (e.g., 1, 2, 4, 6)", "default": 1},
                    "series": {"type": "string", "description": "Series name (e.g., 'The Landmark Series', 'Digital Icons')"},
                    "sov": {"type": "string", "description": "Share of voice percentage - REQUIRED for Digital only (e.g., '16.6%', '12.5%')"},
                    "spot_duration": {"type": "integer", "description": "Duration of each spot in seconds - REQUIRED for Digital only (e.g., 10, 12, 16)"},
                    "loop_duration": {"type": "integer", "description": "Total loop duration in seconds - REQUIRED for Digital only (e.g., 96, 100)"},
                    "upload_fee": {"type": "integer", "description": "Upload fee in AED - REQUIRED for Digital only (e.g., 1000, 1500, 2000, 3000)"}
                }, 
                "required": ["location_key", "display_name", "display_type", "height", "width", "series"]
            }
        },
        {"type": "function", "name": "list_locations", "description": "ONLY call this when user explicitly asks to SEE or LIST available locations (e.g., 'what locations do you have?', 'show me locations', 'list all locations'). DO NOT call this when user mentions specific location names in a proposal request.", "parameters": {"type": "object", "properties": {}}},
        {
            "type": "function",
            "name": "delete_location",
            "description": "Delete an existing location (admin only, requires confirmation). ADMIN ONLY.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_key": {"type": "string", "description": "The location key or display name to delete"}
                },
                "required": ["location_key"]
            }
        },
        {"type": "function", "name": "export_proposals_to_excel", "description": "Export all proposals from the backend database to Excel and send to user. ADMIN ONLY.", "parameters": {"type": "object", "properties": {}}},
        {"type": "function", "name": "get_proposals_stats", "description": "Get summary statistics of proposals from the database", "parameters": {"type": "object", "properties": {}}},
        {"type": "function", "name": "export_booking_orders_to_excel", "description": "Export all booking orders from the backend database to Excel and send to user. Shows BO ref, client, campaign, gross total, status, dates, etc. ADMIN ONLY.", "parameters": {"type": "object", "properties": {}}},
        {
            "type": "function",
            "name": "fetch_booking_order",
            "description": "Fetch a booking order by its BO number from the original document (e.g., BL-001, VL-042, ABC123, etc). This is the BO number that appears in the client's booking order document. Returns the BO data and combined PDF file. If the BO exists but was created with outdated schema/syntax, it will be automatically regenerated with the latest format. ADMIN ONLY.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bo_number": {"type": "string", "description": "The booking order number from the original document (e.g., 'BL-001', 'VL-042', 'ABC123')"}
                },
                "required": ["bo_number"]
            }
        },
        {
            "type": "function",
            "name": "revise_booking_order",
            "description": "Start a revision workflow for an existing booking order. Sends the BO to Sales Coordinator for edits, then through the full approval flow (Coordinator → HoS → Finance). Use this when admin wants to revise/update an already submitted BO. ADMIN ONLY.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bo_number": {"type": "string", "description": "The booking order number to revise (e.g., 'DPD-112652', 'VLA-001')"}
                },
                "required": ["bo_number"]
            }
        },
        {
            "type": "function",
            "name": "generate_mockup",
            "description": "Generate a billboard mockup. IMPORTANT: If user uploads image file(s) and mentions a location for mockup, call this function IMMEDIATELY - do not ask for clarification. User can upload image(s) OR provide AI prompt(s) for generation OR reuse creatives from recent mockup (within 30 min) by just specifying new location. System stores creative files for 30 minutes enabling follow-up requests on different locations. For AI generation: ALWAYS use 1 prompt (single array entry) unless user EXPLICITLY requests multiple frames (e.g., '3-frame mockup', 'show evolution'). 1 creative = tiled across all frames, N creatives = matched 1:1 to N frames. System validates frame count compatibility automatically. Billboard variations can be specified with time_of_day (day/night/all) and finish (gold/silver/all). Use 'all' or omit to randomly select from all available variations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The location name - intelligently match to available locations. If user says 'gateway' or 'the gateway', match to 'dubai_gateway'. If user says 'jawhara', match to 'dubai_jawhara'. Use your best judgment to infer the correct location from the available list."},
                    "time_of_day": {"type": "string", "description": "Optional time of day: 'day', 'night', or 'all' (default). Use 'all' for random selection from all time variations.", "enum": ["day", "night", "all"]},
                    "finish": {"type": "string", "description": "Optional billboard finish: 'gold', 'silver', or 'all' (default). Use 'all' for random selection from all finish variations.", "enum": ["gold", "silver", "all"]},
                    "ai_prompts": {"type": "array", "items": {"type": "string"}, "description": "Optional array of DETAILED AI prompts to generate billboard-ready ARTWORK. Each prompt generates one creative image. CRITICAL PROMPT QUALITY RULES: Each prompt MUST be comprehensive and detailed (minimum 2-3 sentences), including: specific product/brand name, visual elements, colors, mood/atmosphere, composition details, text/slogans, and any specific details user mentioned. DO NOT use vague 1-2 word descriptions. ALWAYS default to 1 prompt unless user EXPLICITLY requests multiple frames (e.g., '3-frame mockup', 'show evolution'). If 1 prompt: tiled across all frames. If N prompts: matched 1:1 to N frames. GOOD examples: ['Luxury Rolex watch advertisement featuring gold Submariner model on black velvet surface, dramatic spotlight creating reflections, \"Timeless Elegance\" text in elegant serif font, Rolex crown logo prominent'] (single frame - tiled), or ['Mercedes-Benz S-Class sedan front 3/4 view on wet asphalt with city lights bokeh background, sleek silver paint, dramatic evening lighting, \"The Best or Nothing\" slogan', 'Mercedes interior shot showing leather seats and dashboard technology, ambient lighting, sophisticated luxury atmosphere', 'Mercedes driving on mountain road at sunset, dynamic motion blur, aspirational lifestyle imagery'] (3-frame evolution). BAD examples: ['watch ad'], ['car', 'interior', 'driving']. [] means user uploads images."}
                },
                "required": ["location"]
            }
        },
        {
            "type": "code_interpreter",
            "container": {"type": "auto"}
        }
    ]

    # Booking order parsing - Available to all users
    tools.append({
        "type": "function",
        "name": "parse_booking_order",
        "description": "Parse a booking order document (Excel, PDF, or image) for Backlite or Viola. Available to ALL users. Extracts client, campaign, locations, pricing, dates, and financial data. Infer the company from document content (e.g., letterhead, branding, or 'BackLite'/'Viola' text) - default to 'backlite' if unclear. Biased toward classifying uploads as ARTWORK unless clearly a booking order.",
        "parameters": {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "enum": ["backlite", "viola"],
                    "description": "Company name - either 'backlite' or 'viola'. Infer from document branding/letterhead. Default to 'backlite' if unclear."
                },
                "user_notes": {
                    "type": "string",
                    "description": "Optional notes or instructions from user about the booking order"
                }
            },
            "required": ["company"]
        }
    })

    # Admin-only tools
    if is_admin:
        admin_tools = []
        tools.extend(admin_tools)
        logger.info(f"[LLM] Admin user {user_id} - added {len(admin_tools)} admin-only tools")

    try:
        res = await config.openai_client.responses.create(model=config.OPENAI_MODEL, input=messages, tools=tools, tool_choice="auto")

        # Determine workflow based on function being called
        workflow = "general_chat"  # Default
        if res.output and len(res.output) > 0:
            function_call = next((item for item in res.output if item.type == "function_call"), None)
            if function_call and hasattr(function_call, 'name'):
                func_name = function_call.name
                if func_name == "generate_mockup":
                    # Determine if AI or upload based on parameters
                    workflow = "mockup_upload"  # Default, may be updated to mockup_ai later
                elif func_name in ["get_separate_proposals", "get_combined_proposal"]:
                    workflow = "proposal_generation"
                elif func_name == "add_location":
                    workflow = "location_management"

        # Track cost
        from integrations.openai import cost_tracker as cost_tracking
        from integrations.slack.bo_messaging import get_user_real_name
        user_name = await get_user_real_name(user_id) if user_id else None
        cost_tracking.track_openai_call(
            response=res,
            call_type="main_llm",
            user_id=user_name,
            workflow=workflow,
            context=f"Channel: {channel}",
            metadata={"has_files": has_files, "message_length": len(user_input)}
        )

        if not res.output or len(res.output) == 0:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("I can help with proposals or add locations. Say 'add location'."))
            return

        logger.info(f"[LLM] Output items: {len(res.output)}, Types: {[item.type for item in res.output]}")

        # Get function_call item (skip reasoning items)
        msg = next((item for item in res.output if item.type == "function_call"), None)

        # If no function call, get first non-reasoning item for text response
        if msg is None:
            msg = next((item for item in res.output if item.type != "reasoning"), res.output[0])

        logger.info(f"[LLM] Selected item type: {msg.type}")
        if hasattr(msg, 'name'):
            logger.info(f"[LLM] Function name: {msg.name}")
        if msg.type == "function_call":
            # Add assistant's tool call to history so model knows what it did
            try:
                args_dict = json.loads(msg.arguments)
                if msg.name == "get_separate_proposals":
                    locations = [p.get("location", "unknown") for p in args_dict.get("proposals", [])]
                    client = args_dict.get("client_name", "unknown")
                    assistant_summary = f"[Generated separate proposals for {client}: {', '.join(locations)}]"
                elif msg.name == "get_combined_proposal":
                    locations = [p.get("location", "unknown") for p in args_dict.get("proposals", [])]
                    client = args_dict.get("client_name", "unknown")
                    assistant_summary = f"[Generated combined proposal for {client}: {', '.join(locations)}]"
                elif msg.name == "generate_mockup":
                    location = args_dict.get("location", "unknown")
                    assistant_summary = f"[Generated mockup for {location}]"
                elif msg.name == "parse_booking_order":
                    assistant_summary = "[Parsed booking order]"
                else:
                    assistant_summary = f"[Called {msg.name}]"
            except:
                assistant_summary = f"[Called {msg.name}]"
            history.append({"role": "assistant", "content": assistant_summary, "timestamp": datetime.now().isoformat()})

            # Dispatch to tool router
            from routers.tool_router import handle_tool_call
            handled = await handle_tool_call(
                msg=msg,
                channel=channel,
                user_id=user_id,
                status_ts=status_ts,
                slack_event=slack_event,
                user_input=user_input,
                download_slack_file_func=_download_slack_file,
                handle_booking_order_parse_func=_handle_booking_order_parse,
                generate_mockup_queued_func=_generate_mockup_queued,
                generate_ai_mockup_queued_func=_generate_ai_mockup_queued,
            )
            if handled:
                user_history[user_id] = history[-10:]
                return
        else:
            reply = msg.content[-1].text if hasattr(msg, 'content') and msg.content else "How can I help you today?"
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
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack(formatted_reply))

        user_history[user_id] = history[-10:]

    except Exception as e:
        config.logger.error(f"LLM loop error: {e}", exc_info=True)
        # Try to delete status message if it exists
        try:
            if 'status_ts' in locals() and status_ts:
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
        except:
            pass
        await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** Something went wrong. Please try again.")) 