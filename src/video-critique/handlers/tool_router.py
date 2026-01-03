"""
Tool Router for Video Critique.

Dispatches LLM tool calls to the appropriate service methods.
This is the bridge between the LLM conversation loop and the
business logic in the services layer.
"""

import json
from datetime import datetime
from typing import Any

from core.services.task_service import TaskService
from core.services.notification_service import NotificationService
from core.utils.logging import get_logger

import config

logger = get_logger(__name__)


class ToolRouter:
    """
    Routes LLM tool calls to appropriate service methods.

    This class provides a clean interface between the LLM conversation
    loop and the business logic services.
    """

    def __init__(
        self,
        task_service: TaskService | None = None,
        notification_service: NotificationService | None = None,
        config_service: Any = None,
    ):
        """
        Initialize the tool router with services.

        Args:
            task_service: TaskService instance
            notification_service: NotificationService instance
            config_service: Optional config service for loading mappings
        """
        self._task_service = task_service or TaskService()
        self._notification_service = notification_service or NotificationService()
        self._config_service = config_service

    async def route_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | str,
        user_id: str,
        user_name: str | None = None,
        state: Any = None,
        channel: Any = None,
    ) -> str:
        """
        Route a tool call to the appropriate handler.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments (dict or JSON string)
            user_id: User making the request
            user_name: User's display name
            state: Conversation state object
            channel: Channel adapter for sending messages

        Returns:
            Response message string
        """
        # Parse arguments if string
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return f"Error: Invalid arguments for {tool_name}"

        logger.info(f"[ToolRouter] Routing {tool_name} with args: {arguments}")

        try:
            if tool_name == "log_design_request":
                return await self._handle_log_design_request(
                    arguments, user_id, user_name, state
                )

            elif tool_name == "edit_task":
                return await self._handle_edit_task(
                    arguments, user_id, state
                )

            elif tool_name == "delete_task":
                return await self._handle_delete_task(
                    arguments, user_id, state
                )

            elif tool_name == "export_current_data":
                return await self._handle_export_data(
                    arguments, user_id, channel
                )

            elif tool_name == "manage_videographer":
                return await self._handle_manage_videographer(
                    arguments, user_id
                )

            elif tool_name == "manage_location":
                return await self._handle_manage_location(
                    arguments, user_id
                )

            elif tool_name == "manage_salesperson":
                return await self._handle_manage_salesperson(
                    arguments, user_id
                )

            elif tool_name == "update_person_ids":
                return await self._handle_update_ids(
                    arguments, user_id
                )

            elif tool_name == "edit_reviewer":
                return await self._handle_edit_reviewer(arguments, user_id)

            elif tool_name == "edit_hod":
                return await self._handle_edit_hod(arguments, user_id)

            elif tool_name == "edit_head_of_sales":
                return await self._handle_edit_head_of_sales(arguments, user_id)

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            logger.error(f"[ToolRouter] Error handling {tool_name}: {e}")
            return f"Error processing {tool_name}: {str(e)}"

    # =========================================================================
    # DESIGN REQUEST HANDLERS
    # =========================================================================

    async def _handle_log_design_request(
        self,
        args: dict[str, Any],
        user_id: str,
        user_name: str | None,
        state: Any,
    ) -> str:
        """Handle log_design_request tool call."""
        # Parse and normalize the data
        parsed_data = {
            "brand": args.get("brand", ""),
            "start_date": self._normalize_date(args.get("campaign_start_date", "")),
            "end_date": self._normalize_date(args.get("campaign_end_date", "")),
            "reference_number": args.get("reference_number", ""),
            "location": args.get("location", ""),
            "sales_person": args.get("sales_person", ""),
            "task_type": args.get("task_type", "videography"),
            "time_block": args.get("time_block", "both"),
            "submitted_by": user_name or user_id,
        }

        # Store in pending confirmation
        if state:
            state.pending_confirmation = parsed_data

        # Format confirmation message
        msg = "**I've parsed the following details from your request:**\n\n"
        msg += f"- **Brand/Client:** {parsed_data['brand']}\n"
        msg += f"- **Campaign Start Date:** {parsed_data['start_date']}\n"
        msg += f"- **Campaign End Date:** {parsed_data['end_date']}\n"
        msg += f"- **Reference:** `{parsed_data['reference_number']}`\n"
        msg += f"- **Location:** {parsed_data['location']}\n"
        msg += f"- **Sales Person:** {parsed_data['sales_person']}\n"
        msg += f"- **Task Type:** {parsed_data['task_type']}\n"
        msg += f"- **Time Block:** {parsed_data['time_block']}\n"
        msg += f"- **Submitted by:** _{parsed_data['submitted_by']}_\n\n"
        msg += "**Is this correct?** Please confirm to save or let me know what needs to be changed."

        return msg

    async def save_design_request(
        self,
        user_id: str,
        data: dict[str, Any],
        state: Any,
        allow_duplicate: bool = False,
    ) -> str:
        """Save a confirmed design request."""
        try:
            # Check for duplicates first (unless explicitly allowed)
            if not allow_duplicate:
                dup_check = await self._task_service.check_duplicate_reference(
                    data.get("reference_number", "")
                )
                if dup_check.get("is_duplicate"):
                    existing = dup_check.get("existing_entry", {})

                    # Set duplicate flag in state
                    data["_duplicate_confirm"] = True
                    if state:
                        state.pending_confirmation = data

                    msg = "**Duplicate Reference Number Detected!**\n\n"
                    msg += f"The reference `{data['reference_number']}` is already used by:\n\n"
                    msg += f"- **Brand:** {existing.get('Brand', existing.get('brand', ''))}\n"
                    msg += f"- **Location:** {existing.get('Location', existing.get('location', ''))}\n"
                    msg += f"- **Campaign:** {existing.get('Campaign Start Date', existing.get('start_date', ''))} to "
                    msg += f"{existing.get('Campaign End Date', existing.get('end_date', ''))}\n\n"
                    msg += "**Do you want to proceed with this duplicate?**\n"
                    msg += "- Say **'yes'** to create anyway\n"
                    msg += "- Say **'no'** to cancel\n"
                    msg += "- Say **'edit'** to change the reference"
                    return msg

            # Create the task
            result = await self._task_service.create_task(
                brand=data.get("brand", ""),
                reference_number=data.get("reference_number", ""),
                location=data.get("location", ""),
                campaign_start_date=data.get("start_date", ""),
                campaign_end_date=data.get("end_date", ""),
                sales_person=data.get("sales_person", ""),
                submitted_by=data.get("submitted_by", user_id),
                task_type=data.get("task_type", "videography"),
                time_block=data.get("time_block", "both"),
            )

            # Clear pending state
            if state:
                state.pending_confirmation = None

            if result.get("success"):
                task_number = result.get("task_number")
                brand = data.get("brand", "")
                reference = data.get("reference_number", "")

                msg = f"**Task #{task_number} created successfully!**\n\n"
                msg += f"**{brand} - Design Request**\n"
                msg += f"- Reference: `{reference}`\n"
                msg += f"- Campaign: {data.get('start_date', '')} to {data.get('end_date', '')}\n"
                msg += f"- Location: {data.get('location', '')}\n"
                msg += f"- Sales Person: {data.get('sales_person', '')}"

                if allow_duplicate:
                    msg += "\n\n_(duplicate reference accepted)_"

                return msg
            else:
                return f"Error saving request: {result.get('error', 'Unknown error')}"

        except Exception as e:
            logger.error(f"[ToolRouter] Error saving design request: {e}")
            return f"Error saving your request: {str(e)}"

    # =========================================================================
    # TASK MANAGEMENT HANDLERS
    # =========================================================================

    async def _handle_edit_task(
        self,
        args: dict[str, Any],
        user_id: str,
        state: Any,
    ) -> str:
        """Handle edit_task tool call."""
        task_number = args.get("task_number")

        # Get the task data
        task_data = await self._task_service.get_task(task_number)

        if not task_data:
            return f"I couldn't find Task #{task_number}. Please check the task number and try again."

        # Enter edit mode
        if state:
            state.pending_edit = {
                "task_number": task_number,
                "current_data": task_data,
                "updates": {},
            }

        msg = f"**Editing Task #{task_number}**\n\n"
        msg += "**Current task data:**\n"
        msg += f"- Brand: {task_data.get('Brand', 'N/A')}\n"
        msg += f"- Campaign Start Date: {task_data.get('Campaign Start Date', 'N/A')}\n"
        msg += f"- Campaign End Date: {task_data.get('Campaign End Date', 'N/A')}\n"
        msg += f"- Reference Number: {task_data.get('Reference Number', 'N/A')}\n"
        msg += f"- Location: {task_data.get('Location', 'N/A')}\n"
        msg += f"- Sales Person: {task_data.get('Sales Person', 'N/A')}\n"
        msg += f"- Status: {task_data.get('Status', 'N/A')}\n"
        msg += f"- Filming Date: {task_data.get('Filming Date', 'N/A')}\n"

        if task_data.get("Videographer"):
            msg += f"- Videographer: {task_data.get('Videographer')}\n"

        msg += "\nTell me what you'd like to change. Say 'save' when done or 'cancel' to exit."

        return msg

    async def save_task_edits(
        self,
        user_id: str,
        task_number: int,
        updates: dict[str, Any],
        current_data: dict[str, Any],
        state: Any,
        allow_duplicate: bool = False,
    ) -> str:
        """Save task edits."""
        try:
            # Check for duplicate reference if changed
            if "Reference Number" in updates and not allow_duplicate:
                new_ref = updates["Reference Number"]
                current_ref = current_data.get("Reference Number", "")

                if new_ref != current_ref:
                    dup_check = await self._task_service.check_duplicate_reference(new_ref)
                    if dup_check.get("is_duplicate"):
                        # Set duplicate flag
                        if state and state.pending_edit:
                            state.pending_edit["_duplicate_confirm"] = True

                        existing = dup_check.get("existing_entry", {})
                        msg = "**Duplicate Reference Number Detected!**\n\n"
                        msg += f"The reference `{new_ref}` is already used by:\n\n"
                        msg += f"- **Brand:** {existing.get('Brand', '')}\n"
                        msg += f"- **Location:** {existing.get('Location', '')}\n\n"
                        msg += "Say 'save' to update with duplicate, 'cancel' to stop, or 'edit' to continue."
                        return msg

            # Apply updates
            result = await self._task_service.update_task(task_number, updates)

            # Clear pending state
            if state:
                state.pending_edit = None

            if result.get("success"):
                msg = f"**Task #{task_number} updated successfully!**\n\n**Changes made:**\n"
                for field, value in updates.items():
                    old_value = current_data.get(field, "N/A")
                    msg += f"- {field}: {old_value} -> {value}\n"

                if result.get("warning"):
                    msg += f"\n_Note: {result['warning']}_"

                return msg
            else:
                return f"Error updating Task #{task_number}: {result.get('error', 'Unknown error')}"

        except Exception as e:
            logger.error(f"[ToolRouter] Error saving task edits: {e}")
            return f"Error updating task: {str(e)}"

    async def _handle_delete_task(
        self,
        args: dict[str, Any],
        user_id: str,
        state: Any,
    ) -> str:
        """Handle delete_task tool call."""
        task_number = args.get("task_number")

        # Get task data first
        task_data = await self._task_service.get_task(task_number)

        if not task_data:
            return f"I couldn't find Task #{task_number}. Please check the task number and try again."

        # Enter delete confirmation mode
        if state:
            state.pending_delete = {
                "task_number": task_number,
                "task_data": task_data,
            }

        msg = f"**Delete Confirmation for Task #{task_number}**\n\n"
        msg += "**You are about to delete the following task:**\n"
        msg += f"- Brand: {task_data.get('Brand', 'N/A')}\n"
        msg += f"- Reference: {task_data.get('Reference Number', 'N/A')}\n"
        msg += f"- Location: {task_data.get('Location', 'N/A')}\n"
        msg += f"- Campaign: {task_data.get('Campaign Start Date', 'N/A')} to {task_data.get('Campaign End Date', 'N/A')}\n"
        msg += f"- Status: {task_data.get('Status', 'N/A')}\n"

        if str(task_data.get("Status", "")).startswith("Assigned to"):
            msg += f"- Videographer: {task_data.get('Videographer', 'N/A')}\n"
            msg += "\n_Note: This task has a Trello card that will be archived._\n"

        msg += "\n**Are you sure you want to delete this task?**\n"
        msg += "- Say **'yes'** to delete permanently\n"
        msg += "- Say **'no'** to keep the task"

        return msg

    async def delete_task(
        self,
        user_id: str,
        task_number: int,
        task_data: dict[str, Any] | None,
        state: Any,
    ) -> str:
        """Execute task deletion."""
        try:
            result = await self._task_service.delete_task(task_number)

            # Clear pending state
            if state:
                state.pending_delete = None

            if result.get("success"):
                deleted_data = result.get("task_data", task_data or {})
                trello_archived = result.get("trello_archived", False)

                msg = f"**Task #{task_number} has been deleted successfully!**\n\n"
                msg += "**Deleted task details:**\n"
                msg += f"- Brand: {deleted_data.get('Brand', 'N/A')}\n"
                msg += f"- Reference: {deleted_data.get('Reference Number', 'N/A')}\n"
                msg += f"- Location: {deleted_data.get('Location', 'N/A')}\n"

                if str(deleted_data.get("Status", "")).startswith("Assigned to"):
                    if trello_archived:
                        msg += "\n_The associated Trello card has been archived._"
                    else:
                        msg += "\n_The task was assigned but no Trello card was found to archive._"

                msg += "\n\n_The task has been archived in the history database._"
                return msg
            else:
                return f"Error deleting Task #{task_number}: {result.get('error', 'Unknown error')}"

        except Exception as e:
            logger.error(f"[ToolRouter] Error deleting task: {e}")
            return f"Error deleting task: {str(e)}"

    # =========================================================================
    # EXPORT HANDLER
    # =========================================================================

    async def _handle_export_data(
        self,
        args: dict[str, Any],
        user_id: str,
        channel: Any,
    ) -> str:
        """Handle export_current_data tool call."""
        include_history = args.get("include_history", False)

        try:
            result = await self._task_service.export_tasks(
                include_history=include_history,
                user_id=user_id,
            )

            if result.get("success"):
                files = result.get("files", [])
                if files:
                    # Upload files via channel if available
                    if channel:
                        for file_info in files:
                            await channel.upload_file(
                                channel_id=user_id,  # DM to user
                                file_path=file_info.get("path"),
                                filename=file_info.get("name"),
                                title=file_info.get("title", "Task Export"),
                            )

                    return f"Exported {len(files)} file(s) successfully."
                else:
                    return "No data to export."
            else:
                return f"Error exporting data: {result.get('error', 'Unknown error')}"

        except Exception as e:
            logger.error(f"[ToolRouter] Error exporting data: {e}")
            return f"Error exporting data: {str(e)}"

    # =========================================================================
    # MANAGEMENT HANDLERS
    # =========================================================================

    async def _handle_manage_videographer(
        self,
        args: dict[str, Any],
        user_id: str,
    ) -> str:
        """Handle manage_videographer tool call."""
        action = args.get("action", "list")

        if action == "list":
            result = await self._task_service.list_videographers()
            if result.get("success"):
                videographers = result.get("videographers", {})
                msg = f"**Videographer List** ({len(videographers)} total)\n\n"
                for name, details in videographers.items():
                    msg += f"- **{name}**\n"
                    msg += f"  - Email: {details.get('email', 'N/A')}\n"
                    msg += f"  - Status: {'Active' if details.get('active', True) else 'Inactive'}\n\n"
                return msg
            return f"Error: {result.get('error', 'Unknown error')}"

        elif action == "add":
            name = args.get("name")
            email = args.get("email")
            if not name or not email:
                return "Please provide both name and email for the new videographer."

            result = await self._task_service.add_videographer(
                name=name,
                email=email,
                user_id=args.get("user_id"),
                channel_id=args.get("channel_id"),
            )
            if result.get("success"):
                return f"Videographer '{name}' has been added with email {email}."
            return f"Error: {result.get('error', 'Unknown error')}"

        elif action == "remove":
            name = args.get("name")
            if not name:
                return "Please provide the name of the videographer to remove."

            result = await self._task_service.remove_videographer(name)
            if result.get("success"):
                return f"Videographer '{name}' has been removed."
            return f"Error: {result.get('error', 'Unknown error')}"

        return f"Unknown action: {action}"

    async def _handle_manage_location(
        self,
        args: dict[str, Any],
        user_id: str,
    ) -> str:
        """Handle manage_location tool call."""
        action = args.get("action", "list")

        if action == "list":
            result = await self._task_service.list_locations()
            if result.get("success"):
                mappings = result.get("location_mappings", {})

                # Group by videographer
                by_videographer: dict[str, list[str]] = {}
                for loc, vid in mappings.items():
                    if vid not in by_videographer:
                        by_videographer[vid] = []
                    by_videographer[vid].append(loc)

                msg = f"**Location Mappings** ({len(mappings)} total)\n\n"
                for videographer, locations in sorted(by_videographer.items()):
                    msg += f"**{videographer}:**\n"
                    for loc in sorted(locations):
                        msg += f"  - {loc}\n"
                    msg += "\n"
                return msg
            return f"Error: {result.get('error', 'Unknown error')}"

        elif action == "add":
            location = args.get("location")
            videographer = args.get("videographer")
            if not location or not videographer:
                return "Please provide both location name and videographer."

            result = await self._task_service.add_location(location, videographer)
            if result.get("success"):
                return f"Location '{location}' is now assigned to {videographer}."
            return f"Error: {result.get('error', 'Unknown error')}"

        elif action == "remove":
            location = args.get("location")
            if not location:
                return "Please provide the location name to remove."

            result = await self._task_service.remove_location(location)
            if result.get("success"):
                return f"Location '{location}' has been removed."
            return f"Error: {result.get('error', 'Unknown error')}"

        return f"Unknown action: {action}"

    async def _handle_manage_salesperson(
        self,
        args: dict[str, Any],
        user_id: str,
    ) -> str:
        """Handle manage_salesperson tool call."""
        action = args.get("action", "list")

        if action == "list":
            result = await self._task_service.list_salespeople()
            if result.get("success"):
                salespeople = result.get("salespeople", {})
                msg = f"**Salespeople** ({len(salespeople)} total)\n\n"
                for name, info in sorted(salespeople.items()):
                    msg += f"**{name}**\n"
                    msg += f"  - Email: {info.get('email', 'N/A')}\n"
                    msg += f"  - Status: {'Active' if info.get('active', True) else 'Inactive'}\n\n"
                return msg
            return f"Error: {result.get('error', 'Unknown error')}"

        elif action == "add":
            name = args.get("name")
            email = args.get("email")
            if not name or not email:
                return "Please provide both name and email for the new salesperson."

            result = await self._task_service.add_salesperson(
                name=name,
                email=email,
                user_id=args.get("user_id"),
                channel_id=args.get("channel_id"),
            )
            if result.get("success"):
                return f"Salesperson '{name}' has been added with email {email}."
            return f"Error: {result.get('error', 'Unknown error')}"

        elif action == "remove":
            name = args.get("name")
            if not name:
                return "Please provide the name of the salesperson to remove."

            result = await self._task_service.remove_salesperson(name)
            if result.get("success"):
                return f"Salesperson '{name}' has been removed."
            return f"Error: {result.get('error', 'Unknown error')}"

        return f"Unknown action: {action}"

    async def _handle_update_ids(
        self,
        args: dict[str, Any],
        caller_user_id: str,
    ) -> str:
        """Handle update_person_ids tool call."""
        person_type = args.get("person_type")
        person_name = args.get("person_name", "")
        user_id = args.get("user_id")
        channel_id = args.get("channel_id")

        if not user_id and not channel_id:
            return "Please provide at least one ID to update."

        if person_type not in ["reviewer", "hod"] and not person_name:
            return f"Please provide the name of the {person_type} to update."

        result = await self._task_service.update_ids(
            person_type=person_type,
            person_name=person_name,
            user_id=user_id,
            channel_id=channel_id,
        )

        if result.get("success"):
            msg = f"IDs updated successfully.\n\n"
            if user_id:
                msg += f"- User ID: `{user_id}`\n"
            if channel_id:
                msg += f"- Channel ID: `{channel_id}`\n"
            return msg
        return f"Error: {result.get('error', 'Unknown error')}"

    async def _handle_edit_reviewer(
        self,
        args: dict[str, Any],
        user_id: str,
    ) -> str:
        """Handle edit_reviewer tool call."""
        result = await self._task_service.update_reviewer(
            name=args.get("name"),
            email=args.get("email"),
            user_id=args.get("user_id"),
            channel_id=args.get("channel_id"),
            active=args.get("active"),
        )

        if result.get("success"):
            reviewer = result.get("reviewer", {})
            msg = "**Reviewer updated successfully!**\n\n"
            msg += f"- Name: {reviewer.get('name', 'Not set')}\n"
            msg += f"- Email: {reviewer.get('email', 'Not set')}\n"
            msg += f"- Status: {'Active' if reviewer.get('active', True) else 'Inactive'}\n"
            return msg
        return f"Error: {result.get('error', 'Unknown error')}"

    async def _handle_edit_hod(
        self,
        args: dict[str, Any],
        user_id: str,
    ) -> str:
        """Handle edit_hod tool call."""
        result = await self._task_service.update_hod(
            name=args.get("name"),
            email=args.get("email"),
            user_id=args.get("user_id"),
            channel_id=args.get("channel_id"),
            active=args.get("active"),
        )

        if result.get("success"):
            hod = result.get("hod", {})
            msg = "**Head of Department updated successfully!**\n\n"
            msg += f"- Name: {hod.get('name', 'Not set')}\n"
            msg += f"- Email: {hod.get('email', 'Not set')}\n"
            msg += f"- Status: {'Active' if hod.get('active', True) else 'Inactive'}\n"
            return msg
        return f"Error: {result.get('error', 'Unknown error')}"

    async def _handle_edit_head_of_sales(
        self,
        args: dict[str, Any],
        user_id: str,
    ) -> str:
        """Handle edit_head_of_sales tool call."""
        result = await self._task_service.update_head_of_sales(
            name=args.get("name"),
            email=args.get("email"),
            user_id=args.get("user_id"),
            channel_id=args.get("channel_id"),
            active=args.get("active"),
        )

        if result.get("success"):
            hos = result.get("head_of_sales", {})
            msg = "**Head of Sales updated successfully!**\n\n"
            msg += f"- Name: {hos.get('name', 'Not set')}\n"
            msg += f"- Email: {hos.get('email', 'Not set')}\n"
            msg += f"- Status: {'Active' if hos.get('active', True) else 'Inactive'}\n"
            return msg
        return f"Error: {result.get('error', 'Unknown error')}"

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _normalize_date(self, date_str: str) -> str:
        """Normalize date string to DD-MM-YYYY format."""
        if not date_str:
            return ""

        # Already in DD-MM-YYYY format
        if len(date_str) == 10 and date_str[2] == "-" and date_str[5] == "-":
            return date_str

        # Convert from YYYY-MM-DD to DD-MM-YYYY
        if len(date_str) == 10 and date_str[4] == "-":
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.strftime("%d-%m-%Y")
            except ValueError:
                pass

        return date_str
