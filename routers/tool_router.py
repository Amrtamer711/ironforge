"""
Tool Router - Handles dispatching LLM function calls to appropriate handlers.
"""

import os
from datetime import datetime
from typing import List, Optional, Tuple

import config
from db.database import db
from core.proposals import process_proposals
from workflows.bo_parser import BookingOrderParser, sanitize_filename
from db.cache import pending_location_additions
from integrations.llm import ToolCall
from routers.mockup_handler import handle_mockup_generation

logger = config.logger


def _validate_company_access(user_companies: Optional[List[str]]) -> Tuple[bool, str]:
    """
    Validate that user has company access for data operations.

    Security: Users without company assignments cannot access any company-specific data.
    No backwards compatibility - this prevents accidental data leaks.

    Args:
        user_companies: List of company schemas user can access

    Returns:
        Tuple of (is_valid, error_message)
    """
    if user_companies is None or len(user_companies) == 0:
        return False, (
            "❌ **Access Denied**\n\n"
            "You don't have access to any company data. "
            "Please contact your administrator to be assigned to a company."
        )
    return True, ""


def _validate_location_access(
    location_key: str,
    user_companies: List[str],
) -> Tuple[bool, str, Optional[str]]:
    """
    Validate that a specific location belongs to user's accessible companies.

    Security: Prevents users from accessing locations outside their assigned companies,
    even if they know the location key.

    Args:
        location_key: The location key to validate
        user_companies: List of company schemas user can access

    Returns:
        Tuple of (is_valid, error_message, company_schema)
        company_schema is the schema where the location was found (if valid)
    """
    location = db.get_location_by_key(location_key, user_companies)
    if location is None:
        return False, (
            f"❌ **Location Not Found**\n\n"
            f"Location `{location_key}` was not found in your accessible companies. "
            f"Use 'list locations' to see available locations."
        ), None
    return True, "", location.get("company_schema")


async def handle_tool_call(
    tool_call: ToolCall,
    channel: str,
    user_id: str,
    status_ts: str,
    channel_event: dict = None,
    user_input: str = "",
    download_file_func=None,
    handle_booking_order_parse_func=None,
    generate_mockup_queued_func=None,
    generate_ai_mockup_queued_func=None,
    user_companies: list = None,
):
    """
    Main tool router - dispatches function calls to appropriate handlers.

    Channel-agnostic: Works with any channel adapter (Slack, Web, etc.)

    Args:
        tool_call: The ToolCall object from LLMClient response
        channel: Channel/conversation ID (Slack channel or web user ID)
        user_id: User identifier
        status_ts: ID of status message to update/delete
        channel_event: Original channel event dict (for file access)
        user_input: Original user message
        download_file_func: Function to download files (channel-agnostic)
        handle_booking_order_parse_func: Function to handle BO parsing
        generate_mockup_queued_func: Function for queued mockup generation
        generate_ai_mockup_queued_func: Function for queued AI mockup generation
        user_companies: List of company schemas user can access (for data filtering)

    Returns:
        True if handled as function call, False otherwise
    """
    # Extract tool call info - arguments is already a dict from ToolCall
    tool_name = tool_call.name
    args = tool_call.arguments

    channel_adapter = config.get_channel_adapter()

    if tool_name == "get_separate_proposals":
        # Company access validation (security - no backwards compatibility)
        has_access, error_msg = _validate_company_access(user_companies)
        if not has_access:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content=error_msg)
            return True

        args = args
        proposals_data = args.get("proposals", [])
        client_name = args.get("client_name") or "Unknown Client"
        payment_terms = args.get("payment_terms", "100% upfront")
        currency = args.get("currency")  # Optional currency (e.g., 'USD', 'EUR')

        logger.info(f"[SEPARATE] Raw args: {args}")
        logger.info(f"[SEPARATE] Proposals data: {proposals_data}")
        logger.info(f"[SEPARATE] Client: {client_name}, User: {user_id}")
        logger.info(f"[SEPARATE] Payment terms: {payment_terms}")
        logger.info(f"[SEPARATE] Currency: {currency or 'AED'}")
        logger.info(f"[SEPARATE] User companies: {user_companies}")

        if not proposals_data:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** No proposals data provided")
            return True

        # Validate all requested locations belong to user's companies
        for proposal in proposals_data:
            location_key = proposal.get("location", "").strip().lower().replace(" ", "_")
            if location_key:
                is_valid, loc_error, _ = _validate_location_access(location_key, user_companies)
                if not is_valid:
                    await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                    await channel_adapter.send_message(channel_id=channel, content=loc_error)
                    return True

        # Update status to Building Proposal
        await channel_adapter.update_message(
            channel_id=channel,
            message_id=status_ts,
            content="⏳ _Building Proposal..._"
        )

        result = await process_proposals(proposals_data, "separate", None, user_id, client_name, payment_terms, currency)
    elif tool_name == "get_combined_proposal":
        # Company access validation (security - no backwards compatibility)
        has_access, error_msg = _validate_company_access(user_companies)
        if not has_access:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content=error_msg)
            return True

        args = args
        proposals_data = args.get("proposals", [])
        combined_net_rate = args.get("combined_net_rate", None)
        client_name = args.get("client_name") or "Unknown Client"
        payment_terms = args.get("payment_terms", "100% upfront")
        currency = args.get("currency")  # Optional currency (e.g., 'USD', 'EUR')

        logger.info(f"[COMBINED] Raw args: {args}")
        logger.info(f"[COMBINED] Proposals data: {proposals_data}")
        logger.info(f"[COMBINED] Combined rate: {combined_net_rate}")
        logger.info(f"[COMBINED] Client: {client_name}, User: {user_id}")
        logger.info(f"[COMBINED] Payment terms: {payment_terms}")
        logger.info(f"[COMBINED] Currency: {currency or 'AED'}")
        logger.info(f"[COMBINED] User companies: {user_companies}")

        if not proposals_data:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** No proposals data provided")
            return True
        elif not combined_net_rate:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** Combined package requires a combined net rate")
            return True
        elif len(proposals_data) < 2:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** Combined package requires at least 2 locations")
            return True

        # Validate all requested locations belong to user's companies
        for proposal in proposals_data:
            location_key = proposal.get("location", "").strip().lower().replace(" ", "_")
            if location_key:
                is_valid, loc_error, _ = _validate_location_access(location_key, user_companies)
                if not is_valid:
                    await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                    await channel_adapter.send_message(channel_id=channel, content=loc_error)
                    return True

        # Update status to Building Proposal
        await channel_adapter.update_message(
            channel_id=channel,
            message_id=status_ts,
            content="⏳ _Building Proposal..._"
        )

        # Transform proposals data for combined package (add durations as list with single item)
        for proposal in proposals_data:
            if "duration" in proposal:
                proposal["durations"] = [proposal.pop("duration")]
                logger.info(f"[COMBINED] Transformed proposal: {proposal}")

        result = await process_proposals(proposals_data, "combined", combined_net_rate, user_id, client_name, payment_terms, currency)
    
    # Handle result for both get_separate_proposals and get_combined_proposal
    if tool_name in ["get_separate_proposals", "get_combined_proposal"] and 'result' in locals():
        logger.info(f"[RESULT] Processing result: {result}")
        if result["success"]:
            # Update status to uploading
            await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="📤 Uploading proposals...")

            if result.get("is_combined"):
                logger.info(f"[RESULT] Combined package - PDF: {result.get('pdf_filename')}")
                await channel_adapter.upload_file(channel_id=channel, file_path=result["pdf_path"], title=result["pdf_filename"], comment=f"📦 **Combined Package Proposal**\n📍 Locations: {result['locations']}")
                try: os.unlink(result["pdf_path"])  # type: ignore
                except OSError as cleanup_err: logger.debug(f"[RESULT] Failed to cleanup combined PDF: {cleanup_err}")
            elif result.get("is_single"):
                logger.info(f"[RESULT] Single proposal - Location: {result.get('location')}")
                await channel_adapter.upload_file(channel_id=channel, file_path=result["pptx_path"], title=result["pptx_filename"], comment=f"📊 **PowerPoint Proposal**\n📍 Location: {result['location']}")
                await channel_adapter.upload_file(channel_id=channel, file_path=result["pdf_path"], title=result["pdf_filename"], comment=f"📄 **PDF Proposal**\n📍 Location: {result['location']}")
                try:
                    os.unlink(result["pptx_path"])  # type: ignore
                    os.unlink(result["pdf_path"])  # type: ignore
                except OSError as cleanup_err:
                    logger.debug(f"[RESULT] Failed to cleanup single proposal files: {cleanup_err}")
            else:
                logger.info(f"[RESULT] Multiple separate proposals - Count: {len(result.get('individual_files', []))}")
                for f in result["individual_files"]:
                    await channel_adapter.upload_file(channel_id=channel, file_path=f["path"], title=f["filename"], comment=f"📊 **PowerPoint Proposal**\n📍 Location: {f['location']}")
                await channel_adapter.upload_file(channel_id=channel, file_path=result["merged_pdf_path"], title=result["merged_pdf_filename"], comment=f"📄 **Combined PDF**\n📍 All Locations: {result['locations']}")
                try:
                    for f in result["individual_files"]: os.unlink(f["path"])  # type: ignore
                    os.unlink(result["merged_pdf_path"])  # type: ignore
                except OSError as cleanup_err:
                    logger.debug(f"[RESULT] Failed to cleanup merged proposal files: {cleanup_err}")
            # Delete status message after uploads complete
            try:
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            except Exception as e:
                logger.debug(f"[RESULT] Failed to delete status message: {e}")
        else:
            logger.error(f"[RESULT] Error: {result.get('error')}")
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content=f"❌ **Error:** {result['error']}")

    elif tool_name == "refresh_templates":
        config.refresh_templates()
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(channel_id=channel, content="✅ Templates refreshed successfully.")

    elif tool_name == "add_location":
        # Admin permission gate
        if not config.is_admin(user_id):
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** You need admin privileges to add locations.")
            return True

        args = args
        location_key = args.get("location_key", "").strip().lower().replace(" ", "_")

        if not location_key:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** Location key is required.")
            return True

        # Check if location already exists (filesystem + cache check for security)
        # SECURITY FIX: Previous vulnerability allowed duplicate locations when cache was stale
        # Now we check both filesystem (authoritative) and cache (fallback) to prevent bypass
        location_dir = config.TEMPLATES_DIR / location_key
        mapping = config.get_location_mapping()

        # Dual check: filesystem (primary) + cache (secondary) to prevent bypass
        if location_dir.exists() or location_key in mapping:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            if location_dir.exists():
                logger.warning(f"[SECURITY] Duplicate location attempt blocked - filesystem check: {location_key}")
            await channel_adapter.send_message(channel_id=channel, content=f"⚠️ Location `{location_key}` already exists. Please use a different key.")
            return True

        # All metadata must be provided upfront
        display_name = args.get("display_name")
        display_type = args.get("display_type")
        height = args.get("height")
        width = args.get("width")
        number_of_faces = args.get("number_of_faces", 1)
        sov = args.get("sov")
        series = args.get("series")
        spot_duration = args.get("spot_duration")
        loop_duration = args.get("loop_duration")
        upload_fee = args.get("upload_fee")

        # Clean duration values - remove any non-numeric suffixes
        if spot_duration is not None:
            # Convert to string first to handle the cleaning
            spot_str = str(spot_duration).strip()
            # Remove common suffixes like 's', 'sec', 'seconds', '"'
            spot_str = spot_str.rstrip('s"').rstrip('sec').rstrip('seconds').strip()
            try:
                spot_duration = int(spot_str)
                if spot_duration <= 0:
                    await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                    await channel_adapter.send_message(channel_id=channel, content=f"❌ **Error:** Spot duration must be greater than 0 seconds. Got: {spot_duration}")
                    return True
            except ValueError:
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                await channel_adapter.send_message(channel_id=channel, content=f"❌ **Error:** Invalid spot duration '{spot_duration}'. Please provide a number in seconds (e.g., 10, 12, 16).")
                return True

        if loop_duration is not None:
            # Convert to string first to handle the cleaning
            loop_str = str(loop_duration).strip()
            # Remove common suffixes like 's', 'sec', 'seconds', '"'
            loop_str = loop_str.rstrip('s"').rstrip('sec').rstrip('seconds').strip()
            try:
                loop_duration = int(loop_str)
                if loop_duration <= 0:
                    await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                    await channel_adapter.send_message(channel_id=channel, content=f"❌ **Error:** Loop duration must be greater than 0 seconds. Got: {loop_duration}")
                    return True
            except ValueError:
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                await channel_adapter.send_message(channel_id=channel, content=f"❌ **Error:** Invalid loop duration '{loop_duration}'. Please provide a number in seconds (e.g., 96, 100).")
                return True
        
        # Validate required fields
        missing = []
        if not display_name:
            missing.append("display_name")
        if not display_type:
            missing.append("display_type")
        if not height:
            missing.append("height")
        if not width:
            missing.append("width")
        if not series:
            missing.append("series")
        
        # For digital locations only, these fields are required
        if display_type == "Digital":
            if not sov:
                missing.append("sov")
            if not spot_duration:
                missing.append("spot_duration")
            if not loop_duration:
                missing.append("loop_duration")
            if upload_fee is None:
                missing.append("upload_fee")
        
        if missing:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(
                channel_id=channel,
                content=f"❌ **Error:** Missing required fields: {', '.join(missing)}"
            )
            return True

        # Store the pending location data
        pending_location_additions[user_id] = {
            "location_key": location_key,
            "display_name": display_name,
            "display_type": display_type,
            "height": height,
            "width": width,
            "number_of_faces": number_of_faces,
            "sov": sov,
            "series": series,
            "spot_duration": spot_duration,
            "loop_duration": loop_duration,
            "upload_fee": upload_fee,
            "timestamp": datetime.now()
        }

        logger.info(f"[LOCATION_ADD] Stored pending location for user {user_id}: {location_key}")
        logger.info(f"[LOCATION_ADD] Current pending additions: {list(pending_location_additions.keys())}")

        # Ask for PPT file
        summary_text = (
            f"✅ **Location metadata validated for `{location_key}`**\n\n"
            f"📋 **Summary:**\n"
            f"• Display Name: {display_name}\n"
            f"• Display Type: {display_type}\n"
            f"• Dimensions: {width} x {height}\n"
            f"• Faces: {number_of_faces}\n"
            f"• Series: {series}\n"
        )

        # Add digital-specific fields only for digital locations
        if display_type == "Digital":
            summary_text += (
                f"• SOV: {sov}\n"
                f"• Spot Duration: {spot_duration}s\n"
                f"• Loop Duration: {loop_duration}s\n"
                f"• Upload Fee: AED {upload_fee}\n"
            )

        summary_text += "\n📎 **Please upload the PDF template file now.** (Will be converted to PowerPoint at maximum quality)\n\n⏱️ _You have 10 minutes to upload the file._"

        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content=summary_text
        )
        return True

    elif tool_name == "list_locations":
        # Company access validation (security - no backwards compatibility)
        has_access, error_msg = _validate_company_access(user_companies)
        if not has_access:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content=error_msg)
            return True

        # Query locations from user's accessible company schemas
        locations = db.get_locations_for_companies(user_companies)
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)

        if not locations:
            await channel_adapter.send_message(channel_id=channel, content="📍 No locations available for your companies.")
        else:
            # Group locations by company for clearer display
            by_company = {}
            for loc in locations:
                company = loc.get("company_schema", "Unknown")
                if company not in by_company:
                    by_company[company] = []
                display_name = loc.get("display_name", loc.get("location_key", "Unknown"))
                by_company[company].append(display_name)

            # Format the listing
            listing_parts = []
            for company, names in sorted(by_company.items()):
                company_display = company.replace("_", " ").title()
                listing_parts.append(f"\n**{company_display}:**")
                for name in sorted(names):
                    listing_parts.append(f"• {name}")

            listing = "\n".join(listing_parts)
            await channel_adapter.send_message(channel_id=channel, content=f"📍 **Available locations:**{listing}")

    elif tool_name == "delete_location":
        # Admin permission gate
        if not config.is_admin(user_id):
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** You need admin privileges to delete locations.")
            return True

        args = args
        location_input = args.get("location_key", "").strip()

        if not location_input:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** Please specify which location to delete.")
            return True

        # Find the actual location key - check if it's a display name or direct key
        location_key = None
        display_name = None

        # First try direct key match
        if location_input.lower().replace(" ", "_") in config.LOCATION_METADATA:
            location_key = location_input.lower().replace(" ", "_")
            display_name = config.LOCATION_METADATA[location_key].get('display_name', location_key)
        else:
            # Try to match by display name
            for key, meta in config.LOCATION_METADATA.items():
                if meta.get('display_name', '').lower() == location_input.lower():
                    location_key = key
                    display_name = meta.get('display_name', key)
                    break

        if not location_key:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            available = ", ".join(config.available_location_names())
            await channel_adapter.send_message(
                channel_id=channel,
                content=f"❌ **Error:** Location '{location_input}' not found.\n\n**Available locations:** {available}"
            )
            return True

        # Double confirmation - show location details and ask for confirmation
        location_dir = config.TEMPLATES_DIR / location_key
        meta = config.LOCATION_METADATA[location_key]

        confirmation_text = (
            f"⚠️ **CONFIRM LOCATION DELETION**\n\n"
            f"📍 **Location:** {display_name} (`{location_key}`)\n"
            f"📊 **Type:** {meta.get('display_type', 'Unknown')}\n"
            f"📐 **Size:** {meta.get('width')} x {meta.get('height')}\n"
            f"🎯 **Series:** {meta.get('series', 'Unknown')}\n\n"
            f"🚨 **WARNING:** This will permanently delete:\n"
            f"• PowerPoint template file\n"
            f"• Location metadata\n"
            f"• Remove location from all future proposals\n\n"
            f"❓ **To confirm deletion, reply with:** `confirm delete {location_key}`\n"
            f"❓ **To cancel, reply with:** `cancel` or ignore this message"
        )

        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content=confirmation_text
        )
        return True

    elif tool_name == "export_proposals_to_excel":
        # Admin permission gate
        logger.info(f"[EXCEL_EXPORT] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[EXCEL_EXPORT] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** You need admin privileges to export the database.")
            return True

        logger.info("[EXCEL_EXPORT] User requested Excel export")
        try:
            excel_path = db.export_to_excel()
            logger.info(f"[EXCEL_EXPORT] Created Excel file at {excel_path}")

            # Get file size for display
            file_size = os.path.getsize(excel_path)
            size_mb = file_size / (1024 * 1024)

            # Update status to uploading
            await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="📤 Uploading export...")

            await channel_adapter.upload_file(
                channel_id=channel,
                file_path=excel_path,
                title=f"proposals_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                comment=(
                    f"📊 **Proposals Database Export**\n"
                    f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📁 Size: {size_mb:.2f} MB"
                )
            )

            # Delete status message after upload completes
            try:
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            except Exception as e:
                logger.debug(f"[EXCEL_EXPORT] Failed to delete status message: {e}")

            # Clean up temp file
            try:
                os.unlink(excel_path)
            except OSError as cleanup_err:
                logger.debug(f"[EXCEL_EXPORT] Failed to cleanup temp file: {cleanup_err}")

        except Exception as e:
            logger.error(f"[EXCEL_EXPORT] Error: {e}", exc_info=True)
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(
                channel_id=channel,
                content="❌ **Error:** Failed to export database to Excel. Please try again."
            )

    elif tool_name == "export_booking_orders_to_excel":
        # Admin permission gate
        logger.info(f"[BO_EXPORT] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[BO_EXPORT] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** You need admin privileges to export booking orders.")
            return True

        logger.info("[BO_EXPORT] User requested booking orders Excel export")
        try:
            excel_path = db.export_booking_orders_to_excel()
            logger.info(f"[BO_EXPORT] Created Excel file at {excel_path}")

            # Get file size for display
            file_size = os.path.getsize(excel_path)
            size_mb = file_size / (1024 * 1024)

            # Update status to uploading
            await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="📤 Uploading export...")

            await channel_adapter.upload_file(
                channel_id=channel,
                file_path=excel_path,
                title=f"booking_orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                comment=(
                    f"📋 **Booking Orders Database Export**\n"
                    f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📁 Size: {size_mb:.2f} MB"
                )
            )

            # Delete status message after upload completes
            try:
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            except Exception as e:
                logger.debug(f"[BO_EXPORT] Failed to delete status message: {e}")

            # Clean up temp file
            try:
                os.unlink(excel_path)
            except OSError as cleanup_err:
                logger.debug(f"[BO_EXPORT] Failed to cleanup temp file: {cleanup_err}")

        except Exception as e:
            logger.error(f"[BO_EXPORT] Error: {e}", exc_info=True)
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(
                channel_id=channel,
                content="❌ **Error:** Failed to export booking orders to Excel. Please try again."
            )

    elif tool_name == "fetch_booking_order":
        # Admin permission gate
        logger.info(f"[BO_FETCH] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[BO_FETCH] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** You need admin privileges to fetch booking orders.")
            return True

        args = args
        bo_number = args.get("bo_number")
        logger.info(f"[BO_FETCH] User requested BO by number: '{bo_number}' (type: {type(bo_number)}, len: {len(bo_number) if bo_number else 0})")

        try:
            # Fetch BO from database by bo_number (user-facing identifier)
            # Query is case-insensitive and trims whitespace
            bo_data = db.get_booking_order_by_number(bo_number)
            logger.info(f"[BO_FETCH] Database query result: {'Found' if bo_data else 'Not found'}")

            if not bo_data:
                # Try to list similar BOs for debugging
                conn = db._connect()
                sample_bos = conn.execute("SELECT bo_number FROM booking_orders LIMIT 10").fetchall()
                conn.close()
                logger.info(f"[BO_FETCH] Sample BOs in database: {[bo[0] for bo in sample_bos if bo[0]]}")

                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                await channel_adapter.send_message(
                    channel_id=channel,
                    content=f"❌ **Booking Order Not Found**\n\nBO Number: `{bo_number}` does not exist in the database."
                )
                return True

            # Extract backend bo_ref for internal use and sanitize bo_number for filename
            bo_ref = bo_data.get("bo_ref")
            safe_bo_number = sanitize_filename(bo_number)

            # Check if schema/syntax is outdated and regenerate if needed
            # For now, we'll just fetch and send - regeneration logic can be added later

            # Get the combined PDF path
            combined_pdf_path = bo_data.get("original_file_path") or bo_data.get("parsed_excel_path")

            if combined_pdf_path and os.path.exists(combined_pdf_path):
                # Update status to uploading
                await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="📤 Uploading BO...")

                # Send BO details with file (show user-facing bo_number)
                details = f"📋 **Booking Order Found**\n\n"
                details += f"**BO Number:** {bo_number}\n"
                details += f"**Client:** {bo_data.get('client', 'N/A')}\n"
                details += f"**Campaign:** {bo_data.get('brand_campaign', 'N/A')}\n"
                details += f"**Gross Total:** AED {bo_data.get('gross_amount', 0):,.2f}\n"
                details += f"**Created:** {bo_data.get('created_at', 'N/A')}\n"

                await channel_adapter.upload_file(
                    channel_id=channel,
                    file_path=combined_pdf_path,
                    title=f"{safe_bo_number}.pdf",
                    comment=details
                )
                # Delete status message after upload completes
                try:
                    await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                except Exception as e:
                    logger.debug(f"[BO_FETCH] Failed to delete status message: {e}")
            else:
                # File not found, regenerate from data
                await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="📤 Regenerating and uploading BO...")

                parser = BookingOrderParser(company=bo_data.get("company", "backlite"))

                # Generate Excel from stored data (use bo_ref for internal reference)
                excel_path = await parser.generate_excel(bo_data, bo_ref)

                details = f"📋 **Booking Order Found (Regenerated)**\n\n"
                details += f"**BO Number:** {bo_number}\n"
                details += f"**Client:** {bo_data.get('client', 'N/A')}\n"
                details += f"**Campaign:** {bo_data.get('brand_campaign', 'N/A')}\n"
                details += f"**Gross Total:** AED {bo_data.get('gross_amount', 0):,.2f}\n"
                details += f"**Created:** {bo_data.get('created_at', 'N/A')}\n"
                details += f"\n⚠️ _Original file not found - regenerated from database_"

                await channel_adapter.upload_file(
                    channel_id=channel,
                    file_path=str(excel_path),
                    title=f"{safe_bo_number}.xlsx",
                    comment=details
                )
                # Delete status message after upload completes
                try:
                    await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                except Exception as e:
                    logger.debug(f"[BO_FETCH] Failed to delete status message: {e}")

                # Clean up temp file
                try:
                    excel_path.unlink()
                except OSError as cleanup_err:
                    logger.debug(f"[BO_FETCH] Failed to cleanup temp file: {cleanup_err}")

        except Exception as e:
            logger.error(f"[BO_FETCH] Error: {e}", exc_info=True)
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(
                channel_id=channel,
                content=f"❌ **Error:** Failed to fetch booking order `{bo_ref}`. Error: {str(e)}"
            )

    elif tool_name == "revise_booking_order":
        # Admin permission gate
        logger.info(f"[BO_REVISE] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[BO_REVISE] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content="❌ **Error:** You need admin privileges to revise booking orders.")
            return True

        args = args
        bo_number = args.get("bo_number")
        logger.info(f"[BO_REVISE] Admin requested revision for BO: '{bo_number}'")

        try:
            from workflows import bo_approval as bo_approval_workflow

            # Fetch existing BO from database
            bo_data = db.get_booking_order_by_number(bo_number)
            logger.info(f"[BO_REVISE] Database query result: {'Found' if bo_data else 'Not found'}")

            if not bo_data:
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                await channel_adapter.send_message(
                    channel_id=channel,
                    content=f"❌ **Booking Order Not Found**\n\nBO Number: `{bo_number}` does not exist in the database."
                )
                return True

            # Start revision workflow (sends to coordinator with new thread)
            await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="⏳ _Starting revision workflow..._")

            result = await bo_approval_workflow.start_revision_workflow(
                bo_data=bo_data,
                requester_user_id=user_id,
                requester_channel=channel
            )

            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(
                channel_id=channel,
                content=f"✅ **Revision workflow started for BO {bo_number}**\n\nThe booking order has been sent to the Sales Coordinator for edits."
            )

        except Exception as e:
            logger.error(f"[BO_REVISE] Error: {e}", exc_info=True)
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(
                channel_id=channel,
                content=f"❌ **Error:** Failed to start revision workflow. Error: {str(e)}"
            )

    elif tool_name == "get_proposals_stats":
        logger.info("[STATS] User requested proposals statistics")
        try:
            stats = db.get_proposals_summary()

            # Format the statistics message
            message = "📊 **Proposals Database Summary**\n\n"
            message += f"**Total Proposals:** {stats['total_proposals']}\n\n"

            if stats['by_package_type']:
                message += "**By Package Type:**\n"
                for pkg_type, count in stats['by_package_type'].items():
                    message += f"• {pkg_type.title()}: {count}\n"
                message += "\n"

            if stats['recent_proposals']:
                message += "**Recent Proposals:**\n"
                for proposal in stats['recent_proposals']:
                    date_str = datetime.fromisoformat(proposal['date']).strftime('%Y-%m-%d %H:%M')
                    message += f"• {proposal['client']} - {proposal['locations']} ({date_str})\n"
            else:
                message += "_No proposals generated yet._"

            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(
                channel_id=channel,
                content=message
            )

        except Exception as e:
            logger.error(f"[STATS] Error: {e}", exc_info=True)

    elif tool_name == "parse_booking_order":
        # Available to all users (admin check removed per new workflow)
        args = args
        company = args.get("company")
        user_notes = args.get("user_notes", "")
        await channel_adapter.update_message(channel_id=channel, message_id=status_ts, content="⏳ _Parsing booking order..._")
        await handle_booking_order_parse_func(
            company=company,
            channel_event=channel_event,
            channel=channel,
            status_ts=status_ts,
            user_notes=user_notes,
            user_id=user_id,
            user_message=user_input
        )
        return True

    elif tool_name == "generate_mockup":
        # Company access validation (security - no backwards compatibility)
        has_access, error_msg = _validate_company_access(user_companies)
        if not has_access:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
            await channel_adapter.send_message(channel_id=channel, content=error_msg)
            return True

        # Validate the requested location belongs to user's companies
        location_name = args.get("location", "").strip()
        if location_name:
            location_key = location_name.lower().replace(" ", "_")
            is_valid, loc_error, _ = _validate_location_access(location_key, user_companies)
            if not is_valid:
                await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
                await channel_adapter.send_message(channel_id=channel, content=loc_error)
                return True

        # Delegate to extracted mockup handler
        await handle_mockup_generation(
            location_name=location_name,
            time_of_day=args.get("time_of_day", "").strip().lower() or "all",
            finish=args.get("finish", "").strip().lower() or "all",
            ai_prompts=args.get("ai_prompts", []) or [],
            user_id=user_id,
            channel=channel,
            status_ts=status_ts,
            channel_event=channel_event,
            download_file_func=download_file_func,
            generate_mockup_queued_func=generate_mockup_queued_func,
            generate_ai_mockup_queued_func=generate_ai_mockup_queued_func,
        )

    return True
