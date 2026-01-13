"""
Tool Router - Handles dispatching LLM function calls to appropriate handlers.

Class-based architecture following video-critique pattern for platform alignment.
Each tool has its own private handler method for clarity and testability.
"""

import os
from datetime import datetime
from typing import Any

import config
from core.proposals import process_proposals
from core.services.asset_service import get_asset_service
from core.workflow_context import WorkflowContext
from db.cache import pending_location_additions
from db.database import db
from integrations.llm import ToolCall
from core.utils import sanitize_filename
from workflows.bo_parser import BookingOrderParser
from core.mockups import handle_mockup_generation

logger = config.logger

# TODO: Re-enable PPTX uploads once we implement background uploads for large files.
# PPTX files can be 50-100MB which causes Supabase upload timeouts.
# For now, only send PDFs (much smaller) to avoid blocking users.
ENABLE_PPTX_UPLOADS = False


class ToolRouter:
    """
    Routes LLM tool calls to appropriate handler methods.

    Class-based architecture for:
    - Clear separation of concerns (each tool = one method)
    - Easier testing and mocking
    - Consistent pattern with video-critique module
    - Dependency injection via constructor
    """

    def __init__(
        self,
        channel_adapter: Any = None,
    ):
        """
        Initialize the tool router.

        Args:
            channel_adapter: Channel adapter for messaging (optional, uses config default)
        """
        self._channel = channel_adapter or config.get_channel_adapter()

    async def _send_tool_message(
        self,
        channel_id: str,
        content: str,
        permanent: bool = False,
        **kwargs
    ) -> Any:
        """
        Send a message from a tool response.

        Args:
            channel_id: Channel to send to
            content: Message content
            permanent: If True, message is shown in permanent chat (default: False).
                       Use permanent=True for informational responses like listings,
                       confirmations, and results the user might want to reference.
                       Use permanent=False (default) for transient status/error messages.
            **kwargs: Additional args passed to send_message
        """
        return await self._channel.send_message(
            channel_id=channel_id,
            content=content,
            is_tool_response=not permanent,  # permanent=True means show in chat
            **kwargs
        )

    # =========================================================================
    # VALIDATION HELPERS
    # =========================================================================

    @staticmethod
    def validate_company_access(user_companies: list[str] | None) -> tuple[bool, str]:
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

    @staticmethod
    def validate_location_access(
        location_key: str,
        user_companies: list[str],
        workflow_ctx: WorkflowContext | None = None,
    ) -> tuple[bool, str, str | None]:
        """
        Validate that a specific location belongs to user's accessible companies.

        Security: Prevents users from accessing locations outside their assigned companies,
        even if they know the location key.

        Performance: If workflow_ctx is provided, uses O(1) in-memory lookup.
        Falls back to database query if context not available.

        Args:
            location_key: The location key to validate
            user_companies: List of company schemas user can access
            workflow_ctx: Optional pre-loaded context for O(1) lookups

        Returns:
            Tuple of (is_valid, error_message, company_schema)
            company_schema is the schema where the location was found (if valid)
        """
        location = None

        # Try O(1) lookup from workflow context first (if available)
        if workflow_ctx is not None:
            location = workflow_ctx.get_location(location_key)
            if location:
                logger.debug(f"[TOOL_ROUTER] Location '{location_key}' found in workflow context (O(1))")

        # Fallback to database query if not in context
        if location is None:
            location = db.get_location_by_key(location_key, user_companies)
            if location:
                logger.debug(f"[TOOL_ROUTER] Location '{location_key}' found via DB query (fallback)")

        if location is None:
            return False, (
                f"❌ **Location Not Found**\n\n"
                f"Location `{location_key}` was not found in your accessible companies. "
                f"Use 'list locations' to see available locations."
            ), None

        # Handle both field names: Asset-Management returns 'company', internal code uses 'company_schema'
        company_schema = location.get("company_schema") or location.get("company")
        return True, "", company_schema

    @staticmethod
    async def validate_locations_batch(
        location_keys: list[str],
        user_companies: list[str],
        workflow_ctx: WorkflowContext | None = None,
    ) -> tuple[dict[str, dict], list[str]]:
        """
        Batch validate multiple locations with O(1) per-location lookup.

        Uses workflow_ctx for O(1) in-memory lookup when available,
        falls back to AssetService batch validation otherwise.

        Args:
            location_keys: List of location keys to validate
            user_companies: Companies user has access to
            workflow_ctx: Optional pre-loaded context for O(1) lookups

        Returns:
            Tuple of (location_index, errors)
            - location_index: Dict mapping location_key -> location_data for valid locations
            - errors: List of error messages for invalid/inaccessible locations
        """
        if not user_companies:
            return {}, ["No company access configured"]

        if not location_keys:
            return {}, []

        valid_locations: dict[str, dict] = {}
        errors: list[str] = []

        # If workflow_ctx available, use O(1) in-memory lookups
        if workflow_ctx is not None:
            for location_key in location_keys:
                normalized_key = location_key.lower().strip()
                location = workflow_ctx.get_location(normalized_key)
                if location:
                    valid_locations[normalized_key] = location
                else:
                    errors.append(
                        f"Location '{location_key}' not found in your accessible companies."
                    )
            return valid_locations, errors

        # Fallback to AssetService batch validation
        asset_service = get_asset_service()
        return await asset_service.validate_locations_batch(location_keys, user_companies)

    # =========================================================================
    # MAIN ROUTING METHOD
    # =========================================================================

    async def route_tool_call(
        self,
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
        user_companies: list[str] | None = None,
        workflow_ctx: WorkflowContext | None = None,
    ) -> bool:
        """
        Route a tool call to the appropriate handler method.

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
            workflow_ctx: Optional pre-loaded context for O(1) location lookups

        Returns:
            True if handled as function call, False otherwise
        """
        tool_name = tool_call.name
        args = tool_call.arguments

        # Build context dict for handlers
        ctx = {
            "channel": channel,
            "user_id": user_id,
            "status_ts": status_ts,
            "channel_event": channel_event,
            "user_input": user_input,
            "download_file_func": download_file_func,
            "handle_booking_order_parse_func": handle_booking_order_parse_func,
            "generate_mockup_queued_func": generate_mockup_queued_func,
            "generate_ai_mockup_queued_func": generate_ai_mockup_queued_func,
            "user_companies": user_companies,
            "workflow_ctx": workflow_ctx,
        }

        # Route to appropriate handler
        handlers = {
            "get_separate_proposals": self._handle_separate_proposals,
            "get_combined_proposal": self._handle_combined_proposal,
            "refresh_templates": self._handle_refresh_templates,
            "add_location": self._handle_add_location,
            "list_locations": self._handle_list_locations,
            "delete_location": self._handle_delete_location,
            "export_proposals_to_excel": self._handle_export_proposals,
            "export_booking_orders_to_excel": self._handle_export_booking_orders,
            "fetch_booking_order": self._handle_fetch_booking_order,
            "revise_booking_order": self._handle_revise_booking_order,
            "get_proposals_stats": self._handle_proposals_stats,
            "parse_booking_order": self._handle_parse_booking_order,
            "generate_mockup": self._handle_generate_mockup,
        }

        handler = handlers.get(tool_name)
        if handler:
            await handler(args, ctx)
            return True

        logger.warning(f"[TOOL_ROUTER] Unknown tool: {tool_name}")
        return True

    # =========================================================================
    # PROPOSAL HANDLERS
    # =========================================================================

    async def _handle_separate_proposals(self, args: dict, ctx: dict) -> None:
        """Handle get_separate_proposals tool call."""
        channel = ctx["channel"]
        user_id = ctx["user_id"]
        status_ts = ctx["status_ts"]
        user_companies = ctx["user_companies"]
        workflow_ctx = ctx["workflow_ctx"]

        # Company access validation
        has_access, error_msg = self.validate_company_access(user_companies)
        if not has_access:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content=error_msg)
            return

        proposals_data = args.get("proposals", [])
        client_name = args.get("client_name") or "Unknown Client"
        payment_terms = args.get("payment_terms", "100% upfront")
        currency = args.get("currency")

        logger.info(f"[SEPARATE] Raw args: {args}")
        logger.info(f"[SEPARATE] Proposals data: {proposals_data}")
        logger.info(f"[SEPARATE] Client: {client_name}, User: {user_id}")
        logger.info(f"[SEPARATE] Payment terms: {payment_terms}")
        logger.info(f"[SEPARATE] Currency: {currency or 'AED'}")
        logger.info(f"[SEPARATE] User companies: {user_companies}")

        if not proposals_data:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** No proposals data provided")
            return

        # Batch validate all locations with O(1) lookups
        location_keys = [
            p.get("location", "").strip().lower().replace(" ", "_")
            for p in proposals_data
            if p.get("location")
        ]
        _, validation_errors = await self.validate_locations_batch(location_keys, user_companies, workflow_ctx)
        if validation_errors:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            error_msg = (
                f"❌ **Location Not Found**\n\n"
                f"{validation_errors[0]} "
                f"Use 'list locations' to see available locations."
            )
            await self._send_tool_message(channel_id=channel, content=error_msg)
            return

        # Update status
        await self._channel.update_message(channel_id=channel, message_id=status_ts, content="⏳ _Building Proposal..._")

        result = await process_proposals(proposals_data, "separate", None, user_id, client_name, payment_terms, currency, user_companies)
        await self._handle_proposal_result(result, channel, status_ts)

    async def _handle_combined_proposal(self, args: dict, ctx: dict) -> None:
        """Handle get_combined_proposal tool call."""
        channel = ctx["channel"]
        user_id = ctx["user_id"]
        status_ts = ctx["status_ts"]
        user_companies = ctx["user_companies"]
        workflow_ctx = ctx["workflow_ctx"]

        # Company access validation
        has_access, error_msg = self.validate_company_access(user_companies)
        if not has_access:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content=error_msg)
            return

        proposals_data = args.get("proposals", [])
        combined_net_rate = args.get("combined_net_rate", None)
        client_name = args.get("client_name") or "Unknown Client"
        payment_terms = args.get("payment_terms", "100% upfront")
        currency = args.get("currency")

        logger.info(f"[COMBINED] Raw args: {args}")
        logger.info(f"[COMBINED] Proposals data: {proposals_data}")
        logger.info(f"[COMBINED] Combined rate: {combined_net_rate}")
        logger.info(f"[COMBINED] Client: {client_name}, User: {user_id}")
        logger.info(f"[COMBINED] Payment terms: {payment_terms}")
        logger.info(f"[COMBINED] Currency: {currency or 'AED'}")
        logger.info(f"[COMBINED] User companies: {user_companies}")

        if not proposals_data:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** No proposals data provided")
            return
        elif not combined_net_rate:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** Combined package requires a combined net rate")
            return
        elif len(proposals_data) < 2:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** Combined package requires at least 2 locations")
            return

        # Batch validate all locations with O(1) lookups
        location_keys = [
            p.get("location", "").strip().lower().replace(" ", "_")
            for p in proposals_data
            if p.get("location")
        ]
        _, validation_errors = await self.validate_locations_batch(location_keys, user_companies, workflow_ctx)
        if validation_errors:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            error_msg = (
                f"❌ **Location Not Found**\n\n"
                f"{validation_errors[0]} "
                f"Use 'list locations' to see available locations."
            )
            await self._send_tool_message(channel_id=channel, content=error_msg)
            return

        # Update status
        await self._channel.update_message(channel_id=channel, message_id=status_ts, content="⏳ _Building Proposal..._")

        # Transform proposals data for combined package
        for proposal in proposals_data:
            if "duration" in proposal:
                proposal["durations"] = [proposal.pop("duration")]
                logger.info(f"[COMBINED] Transformed proposal: {proposal}")

        result = await process_proposals(proposals_data, "combined", combined_net_rate, user_id, client_name, payment_terms, currency, user_companies)
        await self._handle_proposal_result(result, channel, status_ts)

    async def _handle_proposal_result(self, result: dict, channel: str, status_ts: str) -> None:
        """Handle the result from proposal generation."""
        logger.info(f"[RESULT] Processing result: {result}")

        if result["success"]:
            await self._channel.update_message(channel_id=channel, message_id=status_ts, content="📤 Uploading proposals...")

            if result.get("is_combined"):
                logger.info(f"[RESULT] Combined package - PDF: {result.get('pdf_filename')}")
                await self._channel.upload_file(
                    channel_id=channel,
                    file_path=result["pdf_path"],
                    filename=result["pdf_filename"],
                    title=result["pdf_filename"],
                    comment=f"📦 **Combined Package Proposal**\n📍 Locations: {result['locations']}"
                )
                try:
                    os.unlink(result["pdf_path"])
                except OSError as cleanup_err:
                    logger.debug(f"[RESULT] Failed to cleanup combined PDF: {cleanup_err}")

            elif result.get("is_single"):
                logger.info(f"[RESULT] Single proposal - Location: {result.get('location')}")
                # Upload PPTX only if enabled (disabled by default due to large file size timeouts)
                if ENABLE_PPTX_UPLOADS:
                    logger.info(f"[RESULT] Uploading PPTX: {result['pptx_filename']} from {result['pptx_path']}")
                    pptx_result = await self._channel.upload_file(
                        channel_id=channel,
                        file_path=result["pptx_path"],
                        filename=result["pptx_filename"],
                        title=result["pptx_filename"],
                        comment=f"📊 **PowerPoint Proposal**\n📍 Location: {result['location']}"
                    )
                    logger.info(f"[RESULT] PPTX upload result: success={pptx_result.success}, error={pptx_result.error if not pptx_result.success else 'None'}")
                else:
                    logger.info(f"[RESULT] Skipping PPTX upload (disabled) - {result['pptx_filename']}")
                # Always upload PDF (smaller file size)
                logger.info(f"[RESULT] Uploading PDF: {result['pdf_filename']} from {result['pdf_path']}")
                pdf_result = await self._channel.upload_file(
                    channel_id=channel,
                    file_path=result["pdf_path"],
                    filename=result["pdf_filename"],
                    title=result["pdf_filename"],
                    comment=f"📄 **PDF Proposal**\n📍 Location: {result['location']}"
                )
                logger.info(f"[RESULT] PDF upload result: success={pdf_result.success}, error={pdf_result.error if not pdf_result.success else 'None'}")
                try:
                    # PDF-first flow may not have PPTX files
                    if result.get("pptx_path"):
                        os.unlink(result["pptx_path"])
                    os.unlink(result["pdf_path"])
                except OSError as cleanup_err:
                    logger.debug(f"[RESULT] Failed to cleanup single proposal files: {cleanup_err}")

            else:
                logger.info(f"[RESULT] Multiple separate proposals - Count: {len(result.get('individual_files', []))}")
                # Upload individual PPTXs only if enabled (disabled by default due to large file size timeouts)
                if ENABLE_PPTX_UPLOADS:
                    for f in result["individual_files"]:
                        logger.info(f"[RESULT] Uploading PPTX: {f['filename']}")
                        await self._channel.upload_file(
                            channel_id=channel,
                            file_path=f["path"],
                            filename=f["filename"],
                            title=f["filename"],
                            comment=f"📊 **PowerPoint Proposal**\n📍 Location: {f['location']}"
                        )
                else:
                    logger.info(f"[RESULT] Skipping {len(result.get('individual_files', []))} PPTX uploads (disabled)")
                # Always upload merged PDF (smaller file size)
                logger.info(f"[RESULT] Uploading merged PDF: {result['merged_pdf_filename']}")
                await self._channel.upload_file(
                    channel_id=channel,
                    file_path=result["merged_pdf_path"],
                    filename=result["merged_pdf_filename"],
                    title=result["merged_pdf_filename"],
                    comment=f"📄 **Combined PDF**\n📍 All Locations: {result['locations']}"
                )
                try:
                    for f in result["individual_files"]:
                        # PDF-first flow may not have individual PPTX files
                        if f.get("path"):
                            os.unlink(f["path"])
                    os.unlink(result["merged_pdf_path"])
                except OSError as cleanup_err:
                    logger.debug(f"[RESULT] Failed to cleanup merged proposal files: {cleanup_err}")

            try:
                await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            except Exception as e:
                logger.debug(f"[RESULT] Failed to delete status message: {e}")
        else:
            # Handle both 'error' (string) and 'errors' (list) formats
            error_msg = result.get('error') or '; '.join(result.get('errors', ['Unknown error']))
            logger.error(f"[RESULT] Error: {error_msg}")
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content=f"❌ **Error:** {error_msg}")

    # =========================================================================
    # TEMPLATE/LOCATION HANDLERS
    # =========================================================================

    async def _handle_refresh_templates(self, args: dict, ctx: dict) -> None:
        """Handle refresh_templates tool call."""
        channel = ctx["channel"]
        status_ts = ctx["status_ts"]

        config.refresh_templates()
        await self._channel.delete_message(channel_id=channel, message_id=status_ts)
        await self._send_tool_message(channel_id=channel, content="✅ Templates refreshed successfully.", permanent=True)

    async def _handle_add_location(self, args: dict, ctx: dict) -> None:
        """Handle add_location tool call."""
        channel = ctx["channel"]
        user_id = ctx["user_id"]
        status_ts = ctx["status_ts"]
        user_companies = ctx["user_companies"]

        # Admin permission gate
        if not config.is_admin(user_id):
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** You need admin privileges to add locations.")
            return

        # Validate company parameter
        target_company = args.get("company", "").strip().lower()
        if not target_company:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** Company is required. Please specify which company to add the location to.")
            return

        # Check user has access to the target company
        if not user_companies or target_company not in user_companies:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            available = ", ".join(user_companies) if user_companies else "none"
            await self._send_tool_message(
                channel_id=channel,
                content=f"❌ **Error:** You don't have access to company `{target_company}`. Your available companies: {available}"
            )
            return

        location_key = args.get("location_key", "").strip().lower().replace(" ", "_")
        if not location_key:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** Location key is required.")
            return

        # Check if location already exists
        from core.services.template_service import TemplateService
        template_service = TemplateService(companies=user_companies)
        template_exists, _ = await template_service.exists(location_key)
        mapping = config.get_location_mapping()

        if template_exists or location_key in mapping:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            if template_exists:
                logger.warning(f"[SECURITY] Duplicate location attempt blocked - storage check: {location_key}")
            await self._send_tool_message(channel_id=channel, content=f"⚠️ Location `{location_key}` already exists. Please use a different key.")
            return

        # Extract and validate metadata
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

        # Clean duration values
        if spot_duration is not None:
            spot_str = str(spot_duration).strip()
            spot_str = spot_str.rstrip('s"').rstrip('sec').rstrip('seconds').strip()
            try:
                spot_duration = int(spot_str)
                if spot_duration <= 0:
                    await self._channel.delete_message(channel_id=channel, message_id=status_ts)
                    await self._send_tool_message(channel_id=channel, content=f"❌ **Error:** Spot duration must be greater than 0 seconds. Got: {spot_duration}")
                    return
            except ValueError:
                await self._channel.delete_message(channel_id=channel, message_id=status_ts)
                await self._send_tool_message(channel_id=channel, content=f"❌ **Error:** Invalid spot duration '{spot_duration}'. Please provide a number in seconds (e.g., 10, 12, 16).")
                return

        if loop_duration is not None:
            loop_str = str(loop_duration).strip()
            loop_str = loop_str.rstrip('s"').rstrip('sec').rstrip('seconds').strip()
            try:
                loop_duration = int(loop_str)
                if loop_duration <= 0:
                    await self._channel.delete_message(channel_id=channel, message_id=status_ts)
                    await self._send_tool_message(channel_id=channel, content=f"❌ **Error:** Loop duration must be greater than 0 seconds. Got: {loop_duration}")
                    return
            except ValueError:
                await self._channel.delete_message(channel_id=channel, message_id=status_ts)
                await self._send_tool_message(channel_id=channel, content=f"❌ **Error:** Invalid loop duration '{loop_duration}'. Please provide a number in seconds (e.g., 96, 100).")
                return

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
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content=f"❌ **Error:** Missing required fields: {', '.join(missing)}")
            return

        # Store pending location data
        pending_location_additions[user_id] = {
            "location_key": location_key,
            "company": target_company,
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
            "timestamp": datetime.now(),
        }

        logger.info(f"[LOCATION_ADD] Stored pending location for user {user_id}: {location_key}")
        logger.info(f"[LOCATION_ADD] Current pending additions: {list(pending_location_additions.keys())}")

        # Build summary text
        summary_text = (
            f"✅ **Location metadata validated for `{location_key}`**\n\n"
            f"📋 **Summary:**\n"
            f"• Display Name: {display_name}\n"
            f"• Display Type: {display_type}\n"
            f"• Dimensions: {width} x {height}\n"
            f"• Faces: {number_of_faces}\n"
            f"• Series: {series}\n"
        )

        if display_type == "Digital":
            summary_text += (
                f"• SOV: {sov}\n"
                f"• Spot Duration: {spot_duration}s\n"
                f"• Loop Duration: {loop_duration}s\n"
                f"• Upload Fee: AED {upload_fee}\n"
            )

        summary_text += "\n📎 **Please upload the PDF template file now.** (Will be converted to PowerPoint at maximum quality)\n\n⏱️ _You have 10 minutes to upload the file._"

        await self._channel.delete_message(channel_id=channel, message_id=status_ts)
        await self._send_tool_message(channel_id=channel, content=summary_text, permanent=True)

    async def _handle_list_locations(self, args: dict, ctx: dict) -> None:
        """Handle list_locations tool call."""
        channel = ctx["channel"]
        status_ts = ctx["status_ts"]
        user_companies = ctx["user_companies"]

        # Company access validation
        has_access, error_msg = self.validate_company_access(user_companies)
        if not has_access:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content=error_msg)
            return

        locations = db.get_locations_for_companies(user_companies)
        await self._channel.delete_message(channel_id=channel, message_id=status_ts)

        if not locations:
            await self._send_tool_message(channel_id=channel, content="📍 No locations available for your companies.", permanent=True)
        else:
            # Group by company
            by_company: dict[str, list[str]] = {}
            for loc in locations:
                company = loc.get("company_schema", "Unknown")
                if company not in by_company:
                    by_company[company] = []
                display_name = loc.get("display_name", loc.get("location_key", "Unknown"))
                by_company[company].append(display_name)

            listing_parts = []
            for company, names in sorted(by_company.items()):
                company_display = company.replace("_", " ").title()
                listing_parts.append(f"\n**{company_display}:**")
                for name in sorted(names):
                    listing_parts.append(f"• {name}")

            listing = "\n".join(listing_parts)
            await self._send_tool_message(channel_id=channel, content=f"📍 **Available locations:**{listing}", permanent=True)

    async def _handle_delete_location(self, args: dict, ctx: dict) -> None:
        """Handle delete_location tool call."""
        channel = ctx["channel"]
        user_id = ctx["user_id"]
        status_ts = ctx["status_ts"]

        # Admin permission gate
        if not config.is_admin(user_id):
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** You need admin privileges to delete locations.")
            return

        location_input = args.get("location_key", "").strip()
        if not location_input:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** Please specify which location to delete.")
            return

        # Find the actual location key
        location_key = None
        display_name = None

        if location_input.lower().replace(" ", "_") in config.LOCATION_METADATA:
            location_key = location_input.lower().replace(" ", "_")
            display_name = config.LOCATION_METADATA[location_key].get('display_name', location_key)
        else:
            for key, meta in config.LOCATION_METADATA.items():
                if meta.get('display_name', '').lower() == location_input.lower():
                    location_key = key
                    display_name = meta.get('display_name', key)
                    break

        if not location_key:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            available = ", ".join(config.available_location_names())
            await self._send_tool_message(
                channel_id=channel,
                content=f"❌ **Error:** Location '{location_input}' not found.\n\n**Available locations:** {available}"
            )
            return

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

        await self._channel.delete_message(channel_id=channel, message_id=status_ts)
        await self._send_tool_message(channel_id=channel, content=confirmation_text, permanent=True)

    # =========================================================================
    # EXPORT HANDLERS
    # =========================================================================

    async def _handle_export_proposals(self, args: dict, ctx: dict) -> None:
        """Handle export_proposals_to_excel tool call."""
        channel = ctx["channel"]
        user_id = ctx["user_id"]
        status_ts = ctx["status_ts"]

        logger.info(f"[EXCEL_EXPORT] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[EXCEL_EXPORT] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** You need admin privileges to export the database.")
            return

        logger.info("[EXCEL_EXPORT] User requested Excel export")
        try:
            excel_path = db.export_to_excel()
            logger.info(f"[EXCEL_EXPORT] Created Excel file at {excel_path}")

            file_size = os.path.getsize(excel_path)
            size_mb = file_size / (1024 * 1024)

            await self._channel.update_message(channel_id=channel, message_id=status_ts, content="📤 Uploading export...")

            await self._channel.upload_file(
                channel_id=channel,
                file_path=excel_path,
                title=f"proposals_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                comment=(
                    f"📊 **Proposals Database Export**\n"
                    f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📁 Size: {size_mb:.2f} MB"
                )
            )

            try:
                await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            except Exception as e:
                logger.debug(f"[EXCEL_EXPORT] Failed to delete status message: {e}")

            try:
                os.unlink(excel_path)
            except OSError as cleanup_err:
                logger.debug(f"[EXCEL_EXPORT] Failed to cleanup temp file: {cleanup_err}")

        except Exception as e:
            logger.error(f"[EXCEL_EXPORT] Error: {e}", exc_info=True)
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** Failed to export database to Excel. Please try again.")

    async def _handle_export_booking_orders(self, args: dict, ctx: dict) -> None:
        """Handle export_booking_orders_to_excel tool call."""
        channel = ctx["channel"]
        user_id = ctx["user_id"]
        status_ts = ctx["status_ts"]

        logger.info(f"[BO_EXPORT] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[BO_EXPORT] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** You need admin privileges to export booking orders.")
            return

        logger.info("[BO_EXPORT] User requested booking orders Excel export")
        try:
            excel_path = db.export_booking_orders_to_excel()
            logger.info(f"[BO_EXPORT] Created Excel file at {excel_path}")

            file_size = os.path.getsize(excel_path)
            size_mb = file_size / (1024 * 1024)

            await self._channel.update_message(channel_id=channel, message_id=status_ts, content="📤 Uploading export...")

            await self._channel.upload_file(
                channel_id=channel,
                file_path=excel_path,
                title=f"booking_orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                comment=(
                    f"📋 **Booking Orders Database Export**\n"
                    f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📁 Size: {size_mb:.2f} MB"
                )
            )

            try:
                await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            except Exception as e:
                logger.debug(f"[BO_EXPORT] Failed to delete status message: {e}")

            try:
                os.unlink(excel_path)
            except OSError as cleanup_err:
                logger.debug(f"[BO_EXPORT] Failed to cleanup temp file: {cleanup_err}")

        except Exception as e:
            logger.error(f"[BO_EXPORT] Error: {e}", exc_info=True)
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** Failed to export booking orders to Excel. Please try again.")

    # =========================================================================
    # BOOKING ORDER HANDLERS
    # =========================================================================

    async def _handle_fetch_booking_order(self, args: dict, ctx: dict) -> None:
        """Handle fetch_booking_order tool call."""
        channel = ctx["channel"]
        user_id = ctx["user_id"]
        status_ts = ctx["status_ts"]

        logger.info(f"[BO_FETCH] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[BO_FETCH] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** You need admin privileges to fetch booking orders.")
            return

        bo_number = args.get("bo_number")
        logger.info(f"[BO_FETCH] User requested BO by number: '{bo_number}' (type: {type(bo_number)}, len: {len(bo_number) if bo_number else 0})")

        try:
            bo_data = db.get_booking_order_by_number(bo_number)
            logger.info(f"[BO_FETCH] Database query result: {'Found' if bo_data else 'Not found'}")

            if not bo_data:
                conn = db._connect()
                sample_bos = conn.execute("SELECT bo_number FROM booking_orders LIMIT 10").fetchall()
                conn.close()
                logger.info(f"[BO_FETCH] Sample BOs in database: {[bo[0] for bo in sample_bos if bo[0]]}")

                await self._channel.delete_message(channel_id=channel, message_id=status_ts)
                await self._send_tool_message(
                    channel_id=channel,
                    content=f"❌ **Booking Order Not Found**\n\nBO Number: `{bo_number}` does not exist in the database."
                )
                return

            bo_ref = bo_data.get("bo_ref")
            safe_bo_number = sanitize_filename(bo_number)
            combined_pdf_path = bo_data.get("original_file_path") or bo_data.get("parsed_excel_path")

            if combined_pdf_path and os.path.exists(combined_pdf_path):
                await self._channel.update_message(channel_id=channel, message_id=status_ts, content="📤 Uploading BO...")

                details = "📋 **Booking Order Found**\n\n"
                details += f"**BO Number:** {bo_number}\n"
                details += f"**Client:** {bo_data.get('client', 'N/A')}\n"
                details += f"**Campaign:** {bo_data.get('brand_campaign', 'N/A')}\n"
                details += f"**Gross Total:** AED {bo_data.get('gross_amount', 0):,.2f}\n"
                details += f"**Created:** {bo_data.get('created_at', 'N/A')}\n"

                await self._channel.upload_file(
                    channel_id=channel,
                    file_path=combined_pdf_path,
                    title=f"{safe_bo_number}.pdf",
                    comment=details
                )

                try:
                    await self._channel.delete_message(channel_id=channel, message_id=status_ts)
                except Exception as e:
                    logger.debug(f"[BO_FETCH] Failed to delete status message: {e}")
            else:
                await self._channel.update_message(channel_id=channel, message_id=status_ts, content="📤 Regenerating and uploading BO...")

                parser = BookingOrderParser(company=bo_data.get("company", "backlite"))
                excel_path = await parser.generate_excel(bo_data, bo_ref)

                details = "📋 **Booking Order Found (Regenerated)**\n\n"
                details += f"**BO Number:** {bo_number}\n"
                details += f"**Client:** {bo_data.get('client', 'N/A')}\n"
                details += f"**Campaign:** {bo_data.get('brand_campaign', 'N/A')}\n"
                details += f"**Gross Total:** AED {bo_data.get('gross_amount', 0):,.2f}\n"
                details += f"**Created:** {bo_data.get('created_at', 'N/A')}\n"
                details += "\n⚠️ _Original file not found - regenerated from database_"

                await self._channel.upload_file(
                    channel_id=channel,
                    file_path=str(excel_path),
                    title=f"{safe_bo_number}.xlsx",
                    comment=details
                )

                try:
                    await self._channel.delete_message(channel_id=channel, message_id=status_ts)
                except Exception as e:
                    logger.debug(f"[BO_FETCH] Failed to delete status message: {e}")

                try:
                    excel_path.unlink()
                except OSError as cleanup_err:
                    logger.debug(f"[BO_FETCH] Failed to cleanup temp file: {cleanup_err}")

        except Exception as e:
            logger.error(f"[BO_FETCH] Error: {e}", exc_info=True)
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(
                channel_id=channel,
                content=f"❌ **Error:** Failed to fetch booking order `{bo_number}`. Error: {str(e)}"
            )

    async def _handle_revise_booking_order(self, args: dict, ctx: dict) -> None:
        """Handle revise_booking_order tool call."""
        channel = ctx["channel"]
        user_id = ctx["user_id"]
        status_ts = ctx["status_ts"]

        logger.info(f"[BO_REVISE] Checking admin privileges for user: {user_id}")
        is_admin_user = config.is_admin(user_id)
        logger.info(f"[BO_REVISE] User {user_id} admin status: {is_admin_user}")

        if not is_admin_user:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content="❌ **Error:** You need admin privileges to revise booking orders.")
            return

        bo_number = args.get("bo_number")
        logger.info(f"[BO_REVISE] Admin requested revision for BO: '{bo_number}'")

        try:
            from workflows import bo_approval as bo_approval_workflow

            bo_data = db.get_booking_order_by_number(bo_number)
            logger.info(f"[BO_REVISE] Database query result: {'Found' if bo_data else 'Not found'}")

            if not bo_data:
                await self._channel.delete_message(channel_id=channel, message_id=status_ts)
                await self._send_tool_message(
                    channel_id=channel,
                    content=f"❌ **Booking Order Not Found**\n\nBO Number: `{bo_number}` does not exist in the database."
                )
                return

            await self._channel.update_message(channel_id=channel, message_id=status_ts, content="⏳ _Starting revision workflow..._")

            await bo_approval_workflow.start_revision_workflow(
                bo_data=bo_data,
                requester_user_id=user_id,
                requester_channel=channel
            )

            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(
                channel_id=channel,
                content=f"✅ **Revision workflow started for BO {bo_number}**\n\nThe booking order has been sent to the Sales Coordinator for edits.",
                permanent=True
            )

        except Exception as e:
            logger.error(f"[BO_REVISE] Error: {e}", exc_info=True)
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(
                channel_id=channel,
                content=f"❌ **Error:** Failed to start revision workflow. Error: {str(e)}"
            )

    async def _handle_parse_booking_order(self, args: dict, ctx: dict) -> None:
        """Handle parse_booking_order tool call."""
        channel = ctx["channel"]
        status_ts = ctx["status_ts"]
        user_id = ctx["user_id"]
        channel_event = ctx["channel_event"]
        user_input = ctx["user_input"]
        handle_booking_order_parse_func = ctx["handle_booking_order_parse_func"]

        company = args.get("company")
        user_notes = args.get("user_notes", "")

        await self._channel.update_message(channel_id=channel, message_id=status_ts, content="⏳ _Parsing booking order..._")

        await handle_booking_order_parse_func(
            company=company,
            channel_event=channel_event,
            channel=channel,
            status_ts=status_ts,
            user_notes=user_notes,
            user_id=user_id,
            user_message=user_input
        )

    # =========================================================================
    # STATS & MOCKUP HANDLERS
    # =========================================================================

    async def _handle_proposals_stats(self, args: dict, ctx: dict) -> None:
        """Handle get_proposals_stats tool call."""
        channel = ctx["channel"]
        status_ts = ctx["status_ts"]

        logger.info("[STATS] User requested proposals statistics")
        try:
            stats = db.get_proposals_summary()

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

            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content=message, permanent=True)

        except Exception as e:
            logger.error(f"[STATS] Error: {e}", exc_info=True)

    async def _handle_generate_mockup(self, args: dict, ctx: dict) -> None:
        """Handle generate_mockup tool call."""
        channel = ctx["channel"]
        user_id = ctx["user_id"]
        status_ts = ctx["status_ts"]
        user_companies = ctx["user_companies"]
        workflow_ctx = ctx["workflow_ctx"]
        channel_event = ctx["channel_event"]
        download_file_func = ctx["download_file_func"]
        generate_mockup_queued_func = ctx["generate_mockup_queued_func"]
        generate_ai_mockup_queued_func = ctx["generate_ai_mockup_queued_func"]

        # Company access validation
        has_access, error_msg = self.validate_company_access(user_companies)
        if not has_access:
            await self._channel.delete_message(channel_id=channel, message_id=status_ts)
            await self._send_tool_message(channel_id=channel, content=error_msg)
            return

        # Validate the requested location
        location_name = args.get("location", "").strip()
        company_hint = None
        if location_name:
            location_key = location_name.lower().replace(" ", "_")
            is_valid, loc_error, company_hint = self.validate_location_access(location_key, user_companies, workflow_ctx)
            if not is_valid:
                await self._channel.delete_message(channel_id=channel, message_id=status_ts)
                await self._send_tool_message(channel_id=channel, content=loc_error)
                return

        # Delegate to extracted mockup handler
        await handle_mockup_generation(
            location_name=location_name,
            time_of_day=args.get("time_of_day", "").strip().lower() or "all",
            side=args.get("side", "").strip().lower() or "all",
            ai_prompts=args.get("ai_prompts", []) or [],
            user_id=user_id,
            channel=channel,
            status_ts=status_ts,
            user_companies=user_companies,
            channel_event=channel_event,
            download_file_func=download_file_func,
            generate_mockup_queued_func=generate_mockup_queued_func,
            generate_ai_mockup_queued_func=generate_ai_mockup_queued_func,
            company_hint=company_hint,
            venue_type=args.get("venue_type", "").strip().lower() or "all",
            asset_type_key=args.get("asset_type_key"),
        )


# =============================================================================
# BACKWARD COMPATIBILITY - Legacy function wrapper
# =============================================================================

# Module-level router instance (lazy-loaded)
_router: ToolRouter | None = None


def get_tool_router() -> ToolRouter:
    """Get the singleton ToolRouter instance."""
    global _router
    if _router is None:
        _router = ToolRouter()
    return _router


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
    workflow_ctx: WorkflowContext | None = None,
):
    """
    Legacy function wrapper for backward compatibility.

    New code should use ToolRouter class directly:
        router = ToolRouter()
        await router.route_tool_call(...)

    Or use the singleton:
        router = get_tool_router()
        await router.route_tool_call(...)
    """
    router = get_tool_router()
    return await router.route_tool_call(
        tool_call=tool_call,
        channel=channel,
        user_id=user_id,
        status_ts=status_ts,
        channel_event=channel_event,
        user_input=user_input,
        download_file_func=download_file_func,
        handle_booking_order_parse_func=handle_booking_order_parse_func,
        generate_mockup_queued_func=generate_mockup_queued_func,
        generate_ai_mockup_queued_func=generate_ai_mockup_queued_func,
        user_companies=user_companies,
        workflow_ctx=workflow_ctx,
    )


# Backward compatibility aliases for validation functions
_validate_company_access = ToolRouter.validate_company_access
_validate_location_access = ToolRouter.validate_location_access
