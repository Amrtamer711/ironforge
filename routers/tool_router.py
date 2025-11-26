"""
Tool Router - Handles dispatching LLM function calls to appropriate handlers.
"""

import json
import os
import gc
from datetime import datetime
from pathlib import Path

import config
from data.database import db
from core.proposals import process_proposals
from workflows.bo_parser import BookingOrderParser, sanitize_filename
from data.cache import (
    pending_location_additions,
    mockup_history,
    get_mockup_history,
    get_location_frame_count,
    store_mockup_history,
)

logger = config.logger


async def handle_tool_call(
    msg,
    channel: str,
    user_id: str,
    status_ts: str,
    slack_event: dict = None,
    user_input: str = "",
    download_slack_file_func=None,
    handle_booking_order_parse_func=None,
    generate_mockup_queued_func=None,
    generate_ai_mockup_queued_func=None,
):
    """
    Main tool router - dispatches function calls to appropriate handlers.

    Args:
        msg: The function call message from OpenAI
        channel: Slack channel ID
        user_id: Slack user ID
        status_ts: Timestamp of status message to update/delete
        slack_event: Original Slack event (for file access)
        user_input: Original user message
        download_slack_file_func: Function to download Slack files
        handle_booking_order_parse_func: Function to handle BO parsing
        generate_mockup_queued_func: Function for queued mockup generation
        generate_ai_mockup_queued_func: Function for queued AI mockup generation

    Returns:
        True if handled as function call, False otherwise
    """
    if msg.type != "function_call":
        return False

    if msg.name == "get_separate_proposals":
        # Update status to Building Proposal
        await config.slack_client.chat_update(
            channel=channel,
            ts=status_ts,
            text="⏳ _Building Proposal..._"
        )
        
        args = json.loads(msg.arguments)
        proposals_data = args.get("proposals", [])
        client_name = args.get("client_name") or "Unknown Client"
        payment_terms = args.get("payment_terms", "100% upfront")

        logger.info(f"[SEPARATE] Raw args: {args}")
        logger.info(f"[SEPARATE] Proposals data: {proposals_data}")
        logger.info(f"[SEPARATE] Client: {client_name}, User: {user_id}")
        logger.info(f"[SEPARATE] Payment terms: {payment_terms}")

        if not proposals_data:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** No proposals data provided"))
            return True

        result = await process_proposals(proposals_data, "separate", None, user_id, client_name, payment_terms)
    elif msg.name == "get_combined_proposal":
        # Update status to Building Proposal
        await config.slack_client.chat_update(
            channel=channel,
            ts=status_ts,
            text="⏳ _Building Proposal..._"
        )
        
        args = json.loads(msg.arguments)
        proposals_data = args.get("proposals", [])
        combined_net_rate = args.get("combined_net_rate", None)
        client_name = args.get("client_name") or "Unknown Client"
        payment_terms = args.get("payment_terms", "100% upfront")

        logger.info(f"[COMBINED] Raw args: {args}")
        logger.info(f"[COMBINED] Proposals data: {proposals_data}")
        logger.info(f"[COMBINED] Combined rate: {combined_net_rate}")
        logger.info(f"[COMBINED] Client: {client_name}, User: {user_id}")
        logger.info(f"[COMBINED] Payment terms: {payment_terms}")

        if not proposals_data:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** No proposals data provided"))
            return True
        elif not combined_net_rate:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** Combined package requires a combined net rate"))
            return True
        elif len(proposals_data) < 2:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** Combined package requires at least 2 locations"))
            return True
        
        # Transform proposals data for combined package (add durations as list with single item)
        for proposal in proposals_data:
            if "duration" in proposal:
                proposal["durations"] = [proposal.pop("duration")]
                logger.info(f"[COMBINED] Transformed proposal: {proposal}")
                
        result = await process_proposals(proposals_data, "combined", combined_net_rate, user_id, client_name, payment_terms)
    
    # Handle result for both get_separate_proposals and get_combined_proposal
    if msg.name in ["get_separate_proposals", "get_combined_proposal"] and 'result' in locals():
        logger.info(f"[RESULT] Processing result: {result}")
        if result["success"]:
            # Delete status message before uploading files
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            
            if result.get("is_combined"):
                logger.info(f"[RESULT] Combined package - PDF: {result.get('pdf_filename')}")
                await config.slack_client.files_upload_v2(channel=channel, file=result["pdf_path"], filename=result["pdf_filename"], initial_comment=config.markdown_to_slack(f"📦 **Combined Package Proposal**\n📍 Locations: {result['locations']}"))
                try: os.unlink(result["pdf_path"])  # type: ignore
                except: pass
            elif result.get("is_single"):
                logger.info(f"[RESULT] Single proposal - Location: {result.get('location')}")
                await config.slack_client.files_upload_v2(channel=channel, file=result["pptx_path"], filename=result["pptx_filename"], initial_comment=config.markdown_to_slack(f"📊 **PowerPoint Proposal**\n📍 Location: {result['location']}"))
                await config.slack_client.files_upload_v2(channel=channel, file=result["pdf_path"], filename=result["pdf_filename"], initial_comment=config.markdown_to_slack(f"📄 **PDF Proposal**\n📍 Location: {result['location']}"))
                try:
                    os.unlink(result["pptx_path"])  # type: ignore
                    os.unlink(result["pdf_path"])  # type: ignore
                except: pass
            else:
                logger.info(f"[RESULT] Multiple separate proposals - Count: {len(result.get('individual_files', []))}")
                for f in result["individual_files"]:
                    await config.slack_client.files_upload_v2(channel=channel, file=f["path"], filename=f["filename"], initial_comment=config.markdown_to_slack(f"📊 **PowerPoint Proposal**\n📍 Location: {f['location']}"))
                await config.slack_client.files_upload_v2(channel=channel, file=result["merged_pdf_path"], filename=result["merged_pdf_filename"], initial_comment=config.markdown_to_slack(f"📄 **Combined PDF**\n📍 All Locations: {result['locations']}"))
                try:
                    for f in result["individual_files"]: os.unlink(f["path"])  # type: ignore
                    os.unlink(result["merged_pdf_path"])  # type: ignore
                except: pass
        else:
            logger.error(f"[RESULT] Error: {result.get('error')}")
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack(f"❌ **Error:** {result['error']}"))

    elif msg.name == "refresh_templates":
        config.refresh_templates()
        await config.slack_client.chat_delete(channel=channel, ts=status_ts)
        await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("✅ Templates refreshed successfully."))

    elif msg.name == "add_location":
        # Admin permission gate
        if not config.is_admin(user_id):
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** You need admin privileges to add locations."))
            return True

        args = json.loads(msg.arguments)
        location_key = args.get("location_key", "").strip().lower().replace(" ", "_")
        
        if not location_key:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** Location key is required."))
            return True

        # Check if location already exists (filesystem + cache check for security)
        # SECURITY FIX: Previous vulnerability allowed duplicate locations when cache was stale
        # Now we check both filesystem (authoritative) and cache (fallback) to prevent bypass
        location_dir = config.TEMPLATES_DIR / location_key
        mapping = config.get_location_mapping()

        # Dual check: filesystem (primary) + cache (secondary) to prevent bypass
        if location_dir.exists() or location_key in mapping:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            if location_dir.exists():
                logger.warning(f"[SECURITY] Duplicate location attempt blocked - filesystem check: {location_key}")
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack(f"⚠️ Location `{location_key}` already exists. Please use a different key."))
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
                    await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                    await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack(f"❌ **Error:** Spot duration must be greater than 0 seconds. Got: {spot_duration}"))
                    return True
            except ValueError:
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack(f"❌ **Error:** Invalid spot duration '{spot_duration}'. Please provide a number in seconds (e.g., 10, 12, 16)."))
                return True
        
        if loop_duration is not None:
            # Convert to string first to handle the cleaning
            loop_str = str(loop_duration).strip()
            # Remove common suffixes like 's', 'sec', 'seconds', '"'
            loop_str = loop_str.rstrip('s"').rstrip('sec').rstrip('seconds').strip()
            try:
                loop_duration = int(loop_str)
                if loop_duration <= 0:
                    await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                    await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack(f"❌ **Error:** Loop duration must be greater than 0 seconds. Got: {loop_duration}"))
                    return True
            except ValueError:
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack(f"❌ **Error:** Invalid loop duration '{loop_duration}'. Please provide a number in seconds (e.g., 96, 100)."))
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
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(f"❌ **Error:** Missing required fields: {', '.join(missing)}")
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
        
        await config.slack_client.chat_delete(channel=channel, ts=status_ts)
        await config.slack_client.chat_postMessage(
            channel=channel,
            text=config.markdown_to_slack(summary_text)
        )
        return True

    elif msg.name == "list_locations":
        names = config.available_location_names()
        await config.slack_client.chat_delete(channel=channel, ts=status_ts)
        if not names:
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("📍 No locations available. Use **'add location'** to add one."))
        else:
            listing = "\n".join(f"• {n}" for n in names)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack(f"📍 **Current locations:**\n{listing}"))

    elif msg.name == "delete_location":
        # Admin permission gate
        if not config.is_admin(user_id):
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** You need admin privileges to delete locations."))
            return True

        args = json.loads(msg.arguments)
        location_input = args.get("location_key", "").strip()

        if not location_input:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** Please specify which location to delete."))
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
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            available = ", ".join(config.available_location_names())
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(f"❌ **Error:** Location '{location_input}' not found.\n\n**Available locations:** {available}")
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

        await config.slack_client.chat_delete(channel=channel, ts=status_ts)
        await config.slack_client.chat_postMessage(
            channel=channel,
            text=config.markdown_to_slack(confirmation_text)
        )
        return True
    
    elif msg.name == "export_proposals_to_excel":
        # Admin permission gate
        logger.info(f"[EXCEL_EXPORT] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[EXCEL_EXPORT] User {user_id} admin status: {is_admin_user}")
        
        if not is_admin_user:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** You need admin privileges to export the database."))
            return True
            
        logger.info("[EXCEL_EXPORT] User requested Excel export")
        try:
            excel_path = db.export_to_excel()
            logger.info(f"[EXCEL_EXPORT] Created Excel file at {excel_path}")
            
            # Get file size for display
            file_size = os.path.getsize(excel_path)
            size_mb = file_size / (1024 * 1024)
            
            # Delete status message before uploading file
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            
            await config.slack_client.files_upload_v2(
                channel=channel,
                file=excel_path,
                filename=f"proposals_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                initial_comment=config.markdown_to_slack(
                    f"📊 **Proposals Database Export**\n"
                    f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📁 Size: {size_mb:.2f} MB"
                )
            )
            
            # Clean up temp file
            try:
                os.unlink(excel_path)
            except:
                pass
                
        except Exception as e:
            logger.error(f"[EXCEL_EXPORT] Error: {e}", exc_info=True)
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack("❌ **Error:** Failed to export database to Excel. Please try again.")
            )
    
    elif msg.name == "export_booking_orders_to_excel":
        # Admin permission gate
        logger.info(f"[BO_EXPORT] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[BO_EXPORT] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** You need admin privileges to export booking orders."))
            return True

        logger.info("[BO_EXPORT] User requested booking orders Excel export")
        try:
            import db
            excel_path = db.export_booking_orders_to_excel()
            logger.info(f"[BO_EXPORT] Created Excel file at {excel_path}")

            # Get file size for display
            file_size = os.path.getsize(excel_path)
            size_mb = file_size / (1024 * 1024)

            # Delete status message before uploading file
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)

            await config.slack_client.files_upload_v2(
                channel=channel,
                file=excel_path,
                filename=f"booking_orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                initial_comment=config.markdown_to_slack(
                    f"📋 **Booking Orders Database Export**\n"
                    f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📁 Size: {size_mb:.2f} MB"
                )
            )

            # Clean up temp file
            try:
                os.unlink(excel_path)
            except:
                pass

        except Exception as e:
            logger.error(f"[BO_EXPORT] Error: {e}", exc_info=True)
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack("❌ **Error:** Failed to export booking orders to Excel. Please try again.")
            )

    elif msg.name == "fetch_booking_order":
        # Admin permission gate
        logger.info(f"[BO_FETCH] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[BO_FETCH] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** You need admin privileges to fetch booking orders."))
            return True

        args = json.loads(msg.arguments)
        bo_number = args.get("bo_number")
        logger.info(f"[BO_FETCH] User requested BO by number: '{bo_number}' (type: {type(bo_number)}, len: {len(bo_number) if bo_number else 0})")

        try:
            import db
            from booking_parser import BookingOrderParser, sanitize_filename

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

                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(f"❌ **Booking Order Not Found**\n\nBO Number: `{bo_number}` does not exist in the database.")
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
                # Delete status message before uploading file
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)

                # Send BO details with file (show user-facing bo_number)
                details = f"📋 **Booking Order Found**\n\n"
                details += f"**BO Number:** {bo_number}\n"
                details += f"**Client:** {bo_data.get('client', 'N/A')}\n"
                details += f"**Campaign:** {bo_data.get('brand_campaign', 'N/A')}\n"
                details += f"**Gross Total:** AED {bo_data.get('gross_amount', 0):,.2f}\n"
                details += f"**Created:** {bo_data.get('created_at', 'N/A')}\n"

                await config.slack_client.files_upload_v2(
                    channel=channel,
                    file=combined_pdf_path,
                    filename=f"{safe_bo_number}.pdf",
                    initial_comment=config.markdown_to_slack(details)
                )
            else:
                # File not found, regenerate from data
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)

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

                await config.slack_client.files_upload_v2(
                    channel=channel,
                    file=str(excel_path),
                    filename=f"{safe_bo_number}.xlsx",
                    initial_comment=config.markdown_to_slack(details)
                )

                # Clean up temp file
                try:
                    excel_path.unlink()
                except:
                    pass

        except Exception as e:
            logger.error(f"[BO_FETCH] Error: {e}", exc_info=True)
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(f"❌ **Error:** Failed to fetch booking order `{bo_ref}`. Error: {str(e)}")
            )

    elif msg.name == "revise_booking_order":
        # Admin permission gate
        logger.info(f"[BO_REVISE] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[BO_REVISE] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(channel=channel, text=config.markdown_to_slack("❌ **Error:** You need admin privileges to revise booking orders."))
            return True

        args = json.loads(msg.arguments)
        bo_number = args.get("bo_number")
        logger.info(f"[BO_REVISE] Admin requested revision for BO: '{bo_number}'")

        try:
            import db
            import bo_approval_workflow

            # Fetch existing BO from database
            bo_data = db.get_booking_order_by_number(bo_number)
            logger.info(f"[BO_REVISE] Database query result: {'Found' if bo_data else 'Not found'}")

            if not bo_data:
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(f"❌ **Booking Order Not Found**\n\nBO Number: `{bo_number}` does not exist in the database.")
                )
                return True

            # Start revision workflow (sends to coordinator with new thread)
            await config.slack_client.chat_update(channel=channel, ts=status_ts, text="⏳ _Starting revision workflow..._")

            result = await bo_approval_workflow.start_revision_workflow(
                bo_data=bo_data,
                requester_user_id=user_id,
                requester_channel=channel
            )

            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(f"✅ **Revision workflow started for BO {bo_number}**\n\nThe booking order has been sent to the Sales Coordinator for edits.")
            )

        except Exception as e:
            logger.error(f"[BO_REVISE] Error: {e}", exc_info=True)
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(f"❌ **Error:** Failed to start revision workflow. Error: {str(e)}")
            )

    elif msg.name == "get_proposals_stats":
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

            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(message)
            )

        except Exception as e:
            logger.error(f"[STATS] Error: {e}", exc_info=True)

    elif msg.name == "parse_booking_order":
        # Available to all users (admin check removed per new workflow)
        args = json.loads(msg.arguments)
        company = args.get("company")
        user_notes = args.get("user_notes", "")
        await config.slack_client.chat_update(channel=channel, ts=status_ts, text="⏳ _Parsing booking order..._")
        await handle_booking_order_parse_func(
            company=company,
            slack_event=slack_event,
            channel=channel,
            status_ts=status_ts,
            user_notes=user_notes,
            user_id=user_id,
            user_message=user_input
        )
        return True

    elif msg.name == "generate_mockup":
        # Handle mockup generation with AI or user upload
        logger.info("[MOCKUP] User requested mockup generation")

        # Parse the location from arguments
        args = json.loads(msg.arguments)
        location_name = args.get("location", "").strip()
        time_of_day = args.get("time_of_day", "").strip().lower() or "all"
        finish = args.get("finish", "").strip().lower() or "all"
        ai_prompts = args.get("ai_prompts", []) or []
        
        # Convert to list if needed and validate
        if not isinstance(ai_prompts, list):
            ai_prompts = [ai_prompts] if ai_prompts else []
        
        # Clean and validate prompts
        ai_prompts = [str(p).strip() for p in ai_prompts if p]
        
        if not ai_prompts:
            # No AI prompts provided - this is fine, user might be uploading images
            num_ai_frames = 0
            logger.info(f"[MOCKUP] No AI prompts provided")
        else:
            num_ai_frames = len(ai_prompts)
            logger.info(f"[MOCKUP] LLM extracted {num_ai_frames} AI prompt(s) from function call")

        # Convert display name to location key
        location_key = config.get_location_key_from_display_name(location_name)
        if not location_key:
            location_key = location_name.lower().replace(" ", "_")

        # Validate location exists
        if location_key not in config.LOCATION_METADATA:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(f"❌ **Error:** Location '{location_name}' not found. Please choose from available locations.")
            )
            return True

        # Handle time_of_day and finish selection
        import mockup_generator
        import db

        variation_note = ""

        # Check if location has any mockup photos configured
        variations = db.list_mockup_variations(location_key)
        if not variations:
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            mockup_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:3000") + "/mockup"
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(
                    f"❌ **Error:** No billboard photos configured for *{location_name}* (location key: `{location_key}`).\n\n"
                    f"Ask an admin to set up mockup frames at {mockup_url}"
                )
            )
            return True

        # Get frame count for this location (needed for validation and storage)
        new_location_frame_count = get_location_frame_count(location_key, time_of_day, finish)

        # Get user's mockup history if exists (will validate later after checking for uploads)
        mockup_user_hist = get_mockup_history(user_id)

        # Check if user uploaded image(s) with the request
        has_images = False
        uploaded_creatives = []

        if slack_event and ("files" in slack_event or slack_event.get("subtype") == "file_share"):
            files = slack_event.get("files", [])
            if not files and slack_event.get("subtype") == "file_share" and "file" in slack_event:
                files = [slack_event["file"]]

            # Look for image files
            for f in files:
                filetype = f.get("filetype", "")
                mimetype = f.get("mimetype", "")
                filename = f.get("name", "").lower()

                if (filetype in ["jpg", "jpeg", "png", "gif", "bmp"] or
                    mimetype.startswith("image/") or
                    any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp"])):
                    try:
                        creative_file = await download_slack_file_func(f)
                        uploaded_creatives.append(creative_file)
                        has_images = True
                        logger.info(f"[MOCKUP] Found uploaded image: {f.get('name')}")
                    except Exception as e:
                        logger.error(f"[MOCKUP] Failed to download image: {e}")

        # Determine mode based on what user provided
        # Priority: 1) New upload 2) AI prompt 3) History reuse 4) Error

        # NO EARLY FRAME VALIDATION - Allow 1 creative to be tiled across multiple frames
        # Validation happens later at line ~1916 where we check creative count, not stored frame count

        # FOLLOW-UP MODE: Check if this is a follow-up request (no upload, no AI, has history)
        if not has_images and not ai_prompts and mockup_user_hist:
            # This is a follow-up request to apply previous creatives to a different location
            stored_frames = mockup_user_hist.get("metadata", {}).get("num_frames", 1)
            stored_creative_paths = mockup_user_hist.get("creative_paths", [])
            stored_location = mockup_user_hist.get("metadata", {}).get("location_name", "unknown")

            # Verify all creative files still exist on disk
            missing_files = []
            for creative_path in stored_creative_paths:
                if not creative_path.exists():
                    missing_files.append(str(creative_path))

            if missing_files:
                logger.error(f"[MOCKUP] Creative files missing from history: {missing_files}")
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(
                        f"❌ **Error:** Your previous creative files are no longer available.\n\n"
                        f"Please upload new images or use AI generation."
                    )
                )
                # Clean up corrupted history
                del mockup_history[user_id]
                return True

            # Validate creative count: Allow if 1 creative (tile across frames) OR matches frame count
            num_stored_creatives = len(stored_creative_paths)
            is_valid_count = (num_stored_creatives == 1) or (num_stored_creatives == new_location_frame_count)

            if is_valid_count:
                logger.info(f"[MOCKUP] Follow-up request detected - reusing {len(stored_creative_paths)} creative(s) from history")

                await config.slack_client.chat_update(
                    channel=channel,
                    ts=status_ts,
                    text=f"⏳ _Applying your previous creative(s) to {location_name}..._"
                )

                try:
                    # Generate mockup using stored creatives (queued)
                    result_path, _ = await generate_mockup_queued_func(
                        location_key,
                        stored_creative_paths,
                        time_of_day=time_of_day,
                        finish=finish
                    )

                    if not result_path:
                        raise Exception("Failed to generate mockup")

                    # Upload mockup
                    await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                    variation_info = ""
                    if time_of_day != "all" or finish != "all":
                        variation_info = f" ({time_of_day}/{finish})"

                    frames_info = f" ({stored_frames} frame(s))" if stored_frames > 1 else ""

                    await config.slack_client.files_upload_v2(
                        channel=channel,
                        file=str(result_path),
                        filename=f"mockup_{location_key}_{time_of_day}_{finish}.jpg",
                        initial_comment=config.markdown_to_slack(
                            f"🎨 **Billboard Mockup Generated** (Follow-up)\n\n"
                            f"📍 New Location: {location_name}{variation_info}\n"
                            f"🔄 Using creative(s) from: {stored_location}{frames_info}\n"
                            f"✨ Your creative has been applied to this location."
                        )
                    )

                    # Update history with new location (but keep same creatives)
                    mockup_user_hist["metadata"]["location_key"] = location_key
                    mockup_user_hist["metadata"]["location_name"] = location_name
                    mockup_user_hist["metadata"]["time_of_day"] = time_of_day
                    mockup_user_hist["metadata"]["finish"] = finish

                    logger.info(f"[MOCKUP] Follow-up mockup generated successfully for user {user_id}")

                    # Cleanup final mockup
                    try:
                        os.unlink(result_path)
                    except:
                        pass

                    # Force garbage collection to free memory from numpy arrays
                    import gc
                    gc.collect()
                    logger.debug(f"[MOCKUP] Follow-up mode: Forced garbage collection")

                    return  # Done with follow-up

                except Exception as e:
                    logger.error(f"[MOCKUP] Error generating follow-up mockup: {e}", exc_info=True)
                    await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                    await config.slack_client.chat_postMessage(
                        channel=channel,
                        text=config.markdown_to_slack(f"❌ **Error:** Failed to generate follow-up mockup. {str(e)}")
                    )

                    # Cleanup result file if it was created before error
                    try:
                        if 'result_path' in locals() and result_path and result_path.exists():
                            os.unlink(result_path)
                            logger.info(f"[MOCKUP] Cleaned up partial result file after error")
                    except Exception as cleanup_error:
                        logger.error(f"[MOCKUP] Failed to cleanup result file: {cleanup_error}")

                    # Force garbage collection
                    import gc
                    gc.collect()

                    return True
            else:
                # Invalid creative count (e.g., 2 creatives for 3 frames)
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(
                        f"⚠️ **Creative Count Mismatch**\n\n"
                        f"I have **{num_stored_creatives} creative(s)** from your previous mockup (**{stored_location}**), "
                        f"but **{location_name}** requires **{new_location_frame_count} frame(s)**.\n\n"
                        f"**Valid options:**\n"
                        f"• Upload **1 image** (will be tiled across all frames)\n"
                        f"• Upload **{new_location_frame_count} images** (one per frame)\n"
                        f"• Use AI generation with a creative description"
                    )
                )
                return True

        # Now proceed with normal modes (Priority: Upload > AI > Error)
        if has_images:
            # UPLOAD MODE: User uploaded image(s) - this takes priority over AI
            logger.info(f"[MOCKUP] Processing {len(uploaded_creatives)} uploaded image(s)")

            # Validate creative count: Allow 1 (tile) OR match frame count
            num_uploaded = len(uploaded_creatives)
            is_valid_upload_count = (num_uploaded == 1) or (num_uploaded == new_location_frame_count)

            if not is_valid_upload_count:
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(
                        f"⚠️ **Creative Count Mismatch**\n\n"
                        f"You uploaded **{num_uploaded} image(s)**, but **{location_name}** requires **{new_location_frame_count} frame(s)**.\n\n"
                        f"**Valid options:**\n"
                        f"• Upload **1 image** (will be tiled across all frames)\n"
                        f"• Upload **{new_location_frame_count} images** (one per frame)"
                    )
                )
                return True

            await config.slack_client.chat_update(
                channel=channel,
                ts=status_ts,
                text="⏳ _Generating mockup from uploaded image(s)..._"
            )

            try:
                # Generate mockup using uploaded creatives (queued)
                result_path, _ = await generate_mockup_queued_func(
                    location_key,
                    uploaded_creatives,
                    time_of_day=time_of_day,
                    finish=finish
                )

                if not result_path:
                    raise Exception("Failed to generate mockup")

                # Delete status and upload mockup
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                variation_info = ""
                if time_of_day != "all" or finish != "all":
                    variation_info = f" ({time_of_day}/{finish})"
                await config.slack_client.files_upload_v2(
                    channel=channel,
                    file=str(result_path),
                    filename=f"mockup_{location_key}_{time_of_day}_{finish}.jpg",
                    initial_comment=config.markdown_to_slack(
                        f"🎨 **Billboard Mockup Generated**\n\n"
                        f"📍 Location: {location_name}{variation_info}\n"
                        f"🖼️ Creative(s): {len(uploaded_creatives)} image(s)\n"
                        f"✨ Your creative has been applied to a billboard photo.{variation_note}"
                    )
                )

                # Get frame count for validation in follow-ups
                location_frame_count = get_location_frame_count(location_key, time_of_day, finish)

                # Store creative files in 30-minute history for follow-ups on other locations
                store_mockup_history(user_id, uploaded_creatives, {
                    "location_key": location_key,
                    "location_name": location_name,
                    "time_of_day": time_of_day,
                    "finish": finish,
                    "mode": "uploaded",
                    "num_frames": location_frame_count or 1
                })
                logger.info(f"[MOCKUP] Stored {len(uploaded_creatives)} uploaded creative(s) in history for user {user_id} ({location_frame_count} frames)")

                # Cleanup final mockup (we keep creatives in history, not the result)
                try:
                    os.unlink(result_path)
                except:
                    pass

                # Force garbage collection to free memory from numpy arrays
                import gc
                gc.collect()
                logger.debug(f"[MOCKUP] Upload mode: Forced garbage collection")

            except Exception as e:
                logger.error(f"[MOCKUP] Error generating mockup from upload: {e}", exc_info=True)
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(f"❌ **Error:** Failed to generate mockup. {str(e)}")
                )

                # Cleanup uploaded creative files on error
                try:
                    for creative_file in uploaded_creatives:
                        os.unlink(creative_file)
                except:
                    pass

                # Force garbage collection
                import gc
                gc.collect()

        elif ai_prompts:
            # AI MODE: User provided AI prompt(s) for generation

            # Validate frame count: Allow 1 (tile across all) OR exact match to template frame count
            is_valid_count = (num_ai_frames == 1) or (num_ai_frames == new_location_frame_count)

            if not is_valid_count:
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(
                        f"⚠️ **Frame Count Mismatch**\n\n"
                        f"You provided **{num_ai_frames} AI prompt(s)**, but **{location_name}** has **{new_location_frame_count} frame(s)**.\n\n"
                        f"**Valid options:**\n"
                        f"• Provide **1 prompt** (will be tiled across all frames)\n"
                        f"• Provide **{new_location_frame_count} prompts** (one per frame)"
                    )
                )
                return True

            await config.slack_client.chat_update(
                channel=channel,
                ts=status_ts,
                text="⏳ _Generating AI creative and mockup..._"
            )

            try:
                # Detect orientation for this location
                import mockup_generator
                is_portrait = mockup_generator.is_portrait_location(location_key)

                if is_portrait:
                    orientation_text = """📐 FORMAT & DIMENSIONS:
- Aspect ratio: Tall portrait (roughly 2:3 ratio)
- Orientation: Vertical/portrait ONLY
- Canvas: Perfectly flat, rectangular, no warping or perspective
- Fill entire frame edge-to-edge with design
- No white borders, frames, or margins around the design"""
                else:
                    orientation_text = """📐 FORMAT & DIMENSIONS:
- Aspect ratio: Wide landscape (roughly 3:2 ratio)
- Orientation: Horizontal/landscape ONLY
- Canvas: Perfectly flat, rectangular, no warping or perspective
- Fill entire frame edge-to-edge with design
- No white borders, frames, or margins around the design"""

                # Extensive system prompt for billboard artwork generation
                enhanced_prompt = f"""Create a professional flat 2D artwork/creative design for outdoor advertising.

⚠️ CRITICAL RULES - READ FIRST:
1. Generate CLEAN, FLAT graphics with SOLID elements
2. FILL THE ENTIRE CANVAS - create a COMPLETE, full advertisement design
3. NO blank/empty backgrounds unless explicitly requested
4. Use modern, contemporary design aesthetic (2024+ style)
5. ABSOLUTELY NO glowing effects, light flares, halos, sparkles, or radiating effects around ANY elements, especially text and logos
6. This should look like a PROFESSIONAL AD from a creative agency

═══════════════════════════════════════════════════════════
🚨 CRITICAL: WHAT YOU ARE CREATING
═══════════════════════════════════════════════════════════

YOU ARE CREATING: **ARTWORK/CREATIVE CONTENT ONLY**
- This is the flat graphic design file (like a Photoshop/Illustrator artwork)
- This artwork will later be placed on a billboard template by our system
- Generate ONLY the creative content, NOT a billboard mockup or photo

✅ CORRECT OUTPUT (what we want):
- A flat, rectangular advertisement design filling the entire canvas
- The actual graphic artwork (like a poster, magazine ad, or digital banner)
- Perfectly flat with no perspective, no 3D elements, no depth
- Edge-to-edge design with no borders, frames, or margins
- Think: the content you'd see on a computer screen when designing an ad
- Like a print-ready advertisement file before it's mounted anywhere

❌ INCORRECT OUTPUT (what we DON'T want):
- ❌ DO NOT create a photo of a physical billboard
- ❌ DO NOT show billboard frames, poles, or support structures
- ❌ DO NOT include perspective, angles, or 3D rendering
- ❌ DO NOT show street scenes, buildings, sky, roads, or environment
- ❌ DO NOT create a mockup showing how the billboard looks when installed
- ❌ DO NOT add vanishing points or dimensional representation

**REMEMBER:** You are creating the ARTWORK that will go ON the billboard,
not a picture OF a billboard. We have a separate template system for that.

═══════════════════════════════════════════════════════════
DETAILED DESIGN REQUIREMENTS:
═══════════════════════════════════════════════════════════

{orientation_text}

🎨 VISUAL DESIGN PRINCIPLES:
- MODERN 2024+ AESTHETIC: Contemporary, sleek, professional design style
- FILL THE CANVAS: Edge-to-edge design with rich visual content - NO blank/empty spaces
- High-impact composition that catches attention immediately
- Large hero image or visual focal point (50-70% of design)
- Strong colors appropriate for outdoor advertising
- Background should be FULLY designed - use colors, images, patterns, or textures (NOT blank white/empty)
- Clear separation between design elements for readability
- Simple but COMPLETE layout (viewer has 5-7 seconds max)
- Professional photo quality or clean vector graphics
- FLAT graphics only - no special effects, glows, or embellishments around elements

✍️ TYPOGRAPHY (if text is needed):
- LARGE, highly readable fonts with clean edges
- Sans-serif typefaces work best for outdoor viewing
- Maximum 7-10 words total (fewer is better)
- Strong text-to-background distinction for readability
- Text size: headlines should occupy 15-25% of vertical height
- Clear hierarchy: one main message, optional supporting text
- Avoid script fonts, thin fonts, or decorative typefaces
- Letter spacing optimized for distance reading
- Text should be solid and clean - NO glows, halos, shadows, or effects around letters

🎯 COMPOSITION STRATEGY:
- FULL CANVAS UTILIZATION: Every part of the design should be intentional and filled
- Rule of thirds or strong visual hierarchy
- One clear focal point (don't scatter attention)
- Strategic use of space - but NO large blank/empty areas
- Visual flow guides eye to key message/CTA
- Brand logo prominent but not dominating (10-15% of space)
- Clean, professional layout with purposeful design elements throughout
- Modern advertising style: bold, complete, visually rich compositions

💡 COLOR THEORY FOR OUTDOOR:
- CRITICAL: Use EXACTLY the colors specified in the creative brief - DO NOT substitute or change colors
- If user requests red background, use RED background - not blue or any other color
- If user requests specific brand colors, use those EXACT colors without modification
- NO BLANK WHITE BACKGROUNDS unless explicitly requested - use rich, designed backgrounds
- Strong colors appropriate to brand (avoid pastels or muted tones)
- Clear distinction between foreground and background elements
- Colors that work well in outdoor conditions
- Background should be fully designed with color, imagery, or patterns - NOT empty/blank
- Avoid repetitive color schemes - vary your palette based on the creative brief
- Solid, flat color application - NO gradients radiating from text or logos

🔍 QUALITY STANDARDS:
- Sharp, crisp graphics (no blur, pixelation, or artifacts)
- Professional commercial photography or illustration
- Even, balanced exposure across all design elements
- No watermarks, stock photo markers, or placeholder text
- Print-ready quality at large scale
- Polished, agency-level execution
- COMPLETE DESIGN: No unfinished areas, blank spaces, or missing elements
- Modern, contemporary look that matches current 2024+ advertising trends

═══════════════════════════════════════════════════════════
⚠️ CRITICAL - FINAL REMINDER - READ CAREFULLY:
═══════════════════════════════════════════════════════════

🚫 ABSOLUTELY DO NOT INCLUDE:
- NO billboards, signs, or advertising structures
- NO street scenes, highways, or roads
- NO people holding/viewing the ad
- NO frames, borders, or physical contexts
- NO 3D perspective or mockup views
- NO environmental surroundings whatsoever
- NO glowing effects, light flares, or dramatic lighting around text/logos
- NO lens flares, sparkles, or artificial light sources
- NO halos, glows, or radiating effects from any elements
- NO blank/empty white backgrounds (unless specifically requested)
- NO unfinished or incomplete designs
- NO dated or old-fashioned design styles - keep it modern

✅ YOU MUST CREATE:
- The FLAT ARTWORK FILE ONLY - the pure advertisement design
- A COMPLETE, FILLED, PROFESSIONAL advertisement (edge-to-edge)
- MODERN 2024+ design style - contemporary, sleek, polished
- A rectangular graphic that will be PLACED onto a billboard LATER
- Think: top-tier creative agency advertisement design
- The final output is a COMPLETE CREATIVE with NO blank areas

📐 DELIVERABLE:
Imagine you're delivering a print file to a billboard company.
They will take YOUR flat design and apply it to their billboard.
Your job: create a COMPLETE, PROFESSIONAL, MODERN advertisement.
Their job: put it on the billboard.

Example: If asked for a "Nike shoe ad," create a COMPLETE advertisement graphic with:
- Full background design (colored, textured, or image-based - NOT blank)
- Product imagery (shoe)
- Brand elements (swoosh logo)
- Text/slogan if needed
- Modern, contemporary design style
- FILLED canvas with intentional design throughout

DELIVER A COMPLETE, MODERN, PROFESSIONAL ADVERTISEMENT - FULLY DESIGNED, NO BLANK AREAS.

═══════════════════════════════════════════════════════════
🎯 YOUR CREATIVE BRIEF (FOLLOW THIS EXACTLY):
═══════════════════════════════════════════════════════════

{{USER_PROMPT}}"""

                # Update status to show we're generating
                frames_text = f"{num_ai_frames} artworks and mockup" if num_ai_frames > 1 else "AI artwork and mockup"
                await config.slack_client.chat_update(
                    channel=channel,
                    ts=status_ts,
                    text=f"⏳ _Generating {frames_text}..._"
                )

                # Generate AI creative(s) + mockup through queue (prevents memory spikes)
                result_path, ai_creative_paths = await generate_ai_mockup_queued_func(
                    ai_prompts=ai_prompts,
                    enhanced_prompt_template=enhanced_prompt,
                    location_key=location_key,
                    time_of_day=time_of_day,
                    finish=finish,
                    user_id=user_id
                )

                if not result_path:
                    raise Exception("Failed to generate mockup")

                # Delete status and upload mockup
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                variation_info = ""
                if time_of_day != "all" or finish != "all":
                    variation_info = f" ({time_of_day}/{finish})"

                frames_info = f" ({num_ai_frames} frames)" if num_ai_frames > 1 else ""

                await config.slack_client.files_upload_v2(
                    channel=channel,
                    file=str(result_path),
                    filename=f"ai_mockup_{location_key}_{time_of_day}_{finish}.jpg",
                    initial_comment=config.markdown_to_slack(
                        f"🎨 **AI-Generated Billboard Mockup**\n\n"
                        f"📍 Location: {location_name}{variation_info}{frames_info}\n"
                    )
                )

                # Store creative files in 30-minute history for follow-ups on other locations
                store_mockup_history(user_id, ai_creative_paths, {
                    "location_key": location_key,
                    "location_name": location_name,
                    "time_of_day": time_of_day,
                    "finish": finish,
                    "mode": "ai_generated",
                    "num_frames": num_ai_frames
                })
                logger.info(f"[MOCKUP] Stored {len(ai_creative_paths)} AI creative(s) in history for user {user_id}")

                # Cleanup final mockup (we keep creatives in history, not the result)
                try:
                    os.unlink(result_path)
                except:
                    pass

                # Force garbage collection to free memory from numpy arrays
                import gc
                gc.collect()
                logger.debug(f"[MOCKUP] AI mode: Forced garbage collection")

            except Exception as e:
                logger.error(f"[MOCKUP] Error generating AI mockup: {e}", exc_info=True)
                await config.slack_client.chat_delete(channel=channel, ts=status_ts)
                await config.slack_client.chat_postMessage(
                    channel=channel,
                    text=config.markdown_to_slack(f"❌ **Error:** Failed to generate AI mockup. {str(e)}")
                )

                # Cleanup any AI creative files that were generated before the error
                try:
                    for creative_path in ai_creative_paths:
                        if creative_path and creative_path.exists():
                            os.unlink(creative_path)
                    logger.info(f"[MOCKUP] Cleaned up {len(ai_creative_paths)} AI creative file(s) after error")
                except Exception as cleanup_error:
                    logger.error(f"[MOCKUP] Failed to cleanup AI creatives: {cleanup_error}")

                # Force garbage collection
                import gc
                gc.collect()

        else:
            # NO AI PROMPT, NO IMAGE UPLOADED, NO HISTORY: Error - user needs to provide creative
            await config.slack_client.chat_delete(channel=channel, ts=status_ts)
            await config.slack_client.chat_postMessage(
                channel=channel,
                text=config.markdown_to_slack(
                    f"❌ **Sorry!** You need to provide a creative for the mockup.\n\n"
                    f"**Three ways to generate mockups:**\n\n"
                    f"1️⃣ **Upload Your Image:** Attach your creative when you send the request\n"
                    f"   Example: [Upload creative.jpg] + \"mockup for {location_name}\"\n\n"
                    f"2️⃣ **AI Generation (No upload needed):** Describe what you want\n"
                    f"   Example: \"mockup for {location_name} with luxury watch ad, gold and elegant typography\"\n"
                    f"   The AI will generate the creative for you!\n\n"
                    f"3️⃣ **Follow-up Request:** If you recently generated a mockup (within 30 min), just ask!\n"
                    f"   Example: \"show me this on {location_name}\" or \"apply to {location_name}\"\n"
                    f"   I'll reuse your previous creative(s) automatically.\n\n"
                    f"Please try again with an image attachment, creative description, or generate a mockup first!"
                )
            )

    return True
