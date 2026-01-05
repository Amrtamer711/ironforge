"""
Assignment Service for Video Critique.

Handles automatic and manual task assignment to videographers:
- Daily assignment checks
- Workload balancing
- Leave awareness
- Filming date calculation
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.time import get_uae_time
from db.database import db

if TYPE_CHECKING:
    from integrations.trello import TrelloClient

logger = get_logger(__name__)


@dataclass
class AssignmentResult:
    """Result of an assignment operation."""
    success: bool
    task_number: int
    videographer: str | None = None
    filming_date: date | None = None
    trello_card_id: str | None = None
    error: str = ""


@dataclass
class WorkloadSummary:
    """Summary of videographer workloads."""
    workloads: dict[str, int]
    on_leave: list[str]
    available: list[str]
    recommended: str | None = None


class AssignmentService:
    """
    Service for managing task assignments to videographers.

    Handles automatic assignment runs, manual assignments,
    and workload balancing across the team.
    """

    def __init__(
        self,
        trello_client: "TrelloClient | None" = None,
        location_mappings: dict[str, str] | None = None,
        videographers: list[str] | None = None,
    ):
        """
        Initialize assignment service.

        Args:
            trello_client: Optional TrelloClient for workload tracking
            location_mappings: Dict mapping locations to preferred videographers
            videographers: List of all videographer names
        """
        self._trello = trello_client
        self._location_mappings = location_mappings or {}
        self._videographers = videographers or []
        self._db = db

    async def _get_trello(self) -> "TrelloClient":
        """Get or create Trello client."""
        if self._trello is None:
            from integrations.trello import TrelloClient
            self._trello = TrelloClient.from_config()
        return self._trello

    def set_location_mappings(self, mappings: dict[str, str]) -> None:
        """Update location to videographer mappings."""
        self._location_mappings = mappings

    def set_videographers(self, videographers: list[str]) -> None:
        """Update list of videographers."""
        self._videographers = videographers

    # ========================================================================
    # ASSIGNMENT OPERATIONS
    # ========================================================================

    async def assign_task(
        self,
        task_number: int,
        videographer: str,
        filming_date: date | None = None,
        create_trello_card: bool = True,
    ) -> AssignmentResult:
        """
        Assign a task to a videographer.

        Args:
            task_number: Task number
            videographer: Videographer name
            filming_date: Optional filming date override
            create_trello_card: Whether to create a Trello card

        Returns:
            AssignmentResult with assignment details
        """
        try:
            # Get task
            task = await self._db.get_task(task_number)
            if not task:
                return AssignmentResult(
                    success=False,
                    task_number=task_number,
                    error="Task not found",
                )

            # Use provided filming date or calculate
            if filming_date is None:
                filming_date = task.filming_date

            # Update task
            updates = {
                "videographer": videographer,
                "status": f"Assigned to {videographer}",
                "filming_date": filming_date,
                "updated_at": get_uae_time(),
            }

            success = await self._db.update_task(task_number, updates)
            if not success:
                return AssignmentResult(
                    success=False,
                    task_number=task_number,
                    error="Failed to update task",
                )

            # Create Trello card
            trello_card_id = None
            if create_trello_card:
                trello_card_id = await self._create_trello_card(
                    task_number=task_number,
                    videographer=videographer,
                    filming_date=filming_date,
                    task_data={
                        "brand": task.brand,
                        "reference_number": task.reference_number,
                        "location": task.location,
                        "campaign_start_date": task.campaign_start_date,
                        "campaign_end_date": task.campaign_end_date,
                        "sales_person": task.sales_person,
                    },
                )

            logger.info(
                f"[AssignmentService] Assigned task #{task_number} to {videographer}"
            )

            return AssignmentResult(
                success=True,
                task_number=task_number,
                videographer=videographer,
                filming_date=filming_date,
                trello_card_id=trello_card_id,
            )

        except Exception as e:
            logger.error(f"[AssignmentService] Error assigning task #{task_number}: {e}")
            return AssignmentResult(
                success=False,
                task_number=task_number,
                error=str(e),
            )

    async def run_assignment_check(
        self,
        calculate_filming_date_func=None,
    ) -> list[AssignmentResult]:
        """
        Run automatic assignment for all unassigned tasks.

        Assigns tasks based on:
        1. Location-based preferred videographer
        2. Workload balancing if preferred is unavailable

        Args:
            calculate_filming_date_func: Optional function to calculate filming dates

        Returns:
            List of AssignmentResult for each processed task
        """
        results = []

        try:
            # Get unassigned tasks
            unassigned = await self._db.list_tasks({"status": "Not assigned yet"})

            if not unassigned:
                logger.info("[AssignmentService] No unassigned tasks found")
                return []

            logger.info(f"[AssignmentService] Found {len(unassigned)} unassigned tasks")

            for task in unassigned:
                result = await self._assign_single_task(
                    task,
                    calculate_filming_date_func,
                )
                results.append(result)

            assigned_count = sum(1 for r in results if r.success)
            logger.info(
                f"[AssignmentService] Assignment run complete: {assigned_count}/{len(unassigned)} assigned"
            )

        except Exception as e:
            logger.error(f"[AssignmentService] Error in assignment run: {e}")

        return results

    async def _assign_single_task(
        self,
        task,
        calculate_filming_date_func=None,
    ) -> AssignmentResult:
        """Assign a single task to the appropriate videographer."""
        task_number = task.task_number

        try:
            # Calculate filming date if function provided
            filming_date = task.filming_date
            if calculate_filming_date_func and task.campaign_start_date:
                filming_date = calculate_filming_date_func(
                    task.campaign_start_date,
                    task.campaign_end_date,
                    location=task.location,
                    task_type=task.task_type,
                    time_block=task.time_block,
                )

            # Determine preferred videographer
            preferred = self._get_preferred_videographer(task.location)

            # Check availability
            videographer = await self._get_available_videographer(
                preferred=preferred,
                filming_date=filming_date,
            )

            if not videographer:
                return AssignmentResult(
                    success=False,
                    task_number=task_number,
                    error="No available videographers",
                )

            # Perform assignment
            return await self.assign_task(
                task_number=task_number,
                videographer=videographer,
                filming_date=filming_date,
                create_trello_card=True,
            )

        except Exception as e:
            logger.error(f"[AssignmentService] Error assigning task #{task_number}: {e}")
            return AssignmentResult(
                success=False,
                task_number=task_number,
                error=str(e),
            )

    # ========================================================================
    # WORKLOAD MANAGEMENT
    # ========================================================================

    async def get_workload_summary(
        self,
        target_date: date | None = None,
    ) -> WorkloadSummary:
        """
        Get workload summary for all videographers.

        Args:
            target_date: Date to check availability for

        Returns:
            WorkloadSummary with workloads and availability
        """
        try:
            from integrations.trello.operations import get_all_workloads

            trello = await self._get_trello()
            workloads, on_leave = get_all_workloads(
                trello,
                self._videographers,
                target_date=target_date,
            )

            available = [v for v in self._videographers if v not in on_leave]

            # Find recommended (lowest workload)
            recommended = None
            if workloads:
                recommended = min(workloads, key=workloads.get)

            return WorkloadSummary(
                workloads=workloads,
                on_leave=on_leave,
                available=available,
                recommended=recommended,
            )

        except Exception as e:
            logger.error(f"[AssignmentService] Error getting workload summary: {e}")
            return WorkloadSummary(
                workloads={},
                on_leave=[],
                available=self._videographers,
            )

    async def get_best_videographer(
        self,
        exclude: str | None = None,
        filming_date: date | None = None,
    ) -> str | None:
        """
        Get the best available videographer based on workload.

        Args:
            exclude: Videographer to exclude (e.g., currently assigned)
            filming_date: Date to check availability

        Returns:
            Videographer name or None
        """
        try:
            from integrations.trello.operations import get_best_videographer_for_assignment

            trello = await self._get_trello()
            recommendation = get_best_videographer_for_assignment(
                trello,
                self._videographers,
                primary_videographer=exclude,
                target_date=filming_date,
            )

            if recommendation:
                return recommendation.videographer

        except Exception as e:
            logger.error(f"[AssignmentService] Error getting best videographer: {e}")

        return None

    async def _get_available_videographer(
        self,
        preferred: str | None = None,
        filming_date: date | None = None,
    ) -> str | None:
        """Get an available videographer, preferring the specified one."""
        try:
            from integrations.trello.operations import will_be_available_on_date

            trello = await self._get_trello()

            # Check if preferred is available
            if preferred and preferred in self._videographers:
                if filming_date:
                    available = will_be_available_on_date(
                        trello, preferred, filming_date
                    )
                    if available:
                        return preferred
                else:
                    return preferred

            # Fall back to workload-based selection
            return await self.get_best_videographer(
                exclude=preferred,
                filming_date=filming_date,
            )

        except Exception as e:
            logger.warning(f"[AssignmentService] Error checking availability: {e}")

            # Return first available from list
            return self._videographers[0] if self._videographers else None

    def _get_preferred_videographer(self, location: str | None) -> str | None:
        """Get preferred videographer for a location."""
        if not location:
            return None
        return self._location_mappings.get(location)

    # ========================================================================
    # TRELLO INTEGRATION
    # ========================================================================

    async def _create_trello_card(
        self,
        task_number: int,
        videographer: str,
        filming_date: date | None,
        task_data: dict[str, Any],
    ) -> str | None:
        """Create a Trello card for an assigned task."""
        try:
            from integrations.trello.operations import (
                build_task_card_title,
                build_task_card_description,
                create_production_timeline_checklist,
            )

            trello = await self._get_trello()

            # Build card content
            title = build_task_card_title(
                task_number,
                task_data.get("brand", ""),
                task_data.get("location", ""),
            )

            description = build_task_card_description(
                task_number=task_number,
                brand=task_data.get("brand", ""),
                reference_number=task_data.get("reference_number", ""),
                location=task_data.get("location", ""),
                campaign_start=task_data.get("campaign_start_date"),
                campaign_end=task_data.get("campaign_end_date"),
                filming_date=filming_date,
                sales_person=task_data.get("sales_person"),
            )

            # Create card in videographer's list
            result = trello.create_card(
                title=title,
                description=description,
                list_name=videographer,
                due_date=datetime.combine(filming_date, datetime.min.time()) if filming_date else None,
            )

            if result.success:
                # Add production timeline checklist
                if filming_date:
                    create_production_timeline_checklist(
                        trello,
                        result.card_id,
                        filming_date,
                    )

                logger.info(f"[AssignmentService] Created Trello card for task #{task_number}")
                return result.card_id

        except Exception as e:
            logger.error(f"[AssignmentService] Error creating Trello card: {e}")

        return None

    async def archive_trello_card(self, task_number: int) -> bool:
        """
        Archive the Trello card for a task.

        Args:
            task_number: Task number

        Returns:
            True if successful
        """
        try:
            trello = await self._get_trello()
            card = trello.get_card_by_task_number(task_number)

            if card:
                return trello.archive_card(card["id"])

        except Exception as e:
            logger.error(f"[AssignmentService] Error archiving Trello card: {e}")

        return False

    async def update_trello_filming_date(
        self,
        task_number: int,
        new_filming_date: date,
    ) -> bool:
        """
        Update filming date on Trello card.

        Args:
            task_number: Task number
            new_filming_date: New filming date

        Returns:
            True if successful
        """
        try:
            from integrations.trello.operations import update_production_timeline_dates

            trello = await self._get_trello()
            card = trello.get_card_by_task_number(task_number)

            if card:
                # Update due date
                trello.update_card(
                    card["id"],
                    due=new_filming_date.strftime("%Y-%m-%dT12:00:00.000Z"),
                )

                # Update checklist dates
                update_production_timeline_dates(trello, card["id"], new_filming_date)

                return True

        except Exception as e:
            logger.error(f"[AssignmentService] Error updating Trello dates: {e}")

        return False
