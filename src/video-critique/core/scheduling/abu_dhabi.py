"""
Abu Dhabi Dynamic Scheduler for Video Critique.

Implements holistic, dynamic scheduling for Abu Dhabi locations.
Optimizes filming dates for all pending Abu Dhabi tasks simultaneously,
maximizing campaign bundling while respecting constraints.

Key Features:
- Plans all Abu Dhabi tasks together (not individually)
- Maximizes campaign overlap on shoot dates
- Enforces: max 2 shoots/week, Tue/Thu/Fri only, min 1-day gap
- Respects T-1 freeze rule (no changes within 24hrs of shoot)
- Handles time blocks (DAY/NIGHT/BOTH)
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from core.scheduling.base import Scheduler, SchedulingConfig
from core.utils.logging import get_logger

logger = get_logger(__name__)


# Abu Dhabi areas and their locations
ABU_DHABI_AREAS = {
    "GALLERIA_MALL": [
        "galleria mall",
        "galleria",
        "al maryah island",
        "al maryah",
    ],
    "AL_QANA": [
        "al qana",
        "alqana",
        "al-qana",
    ],
}


def is_abu_dhabi_location(location: str) -> bool:
    """Check if a location is an Abu Dhabi location."""
    if not location:
        return False
    loc_lower = location.lower().strip()
    for area_locations in ABU_DHABI_AREAS.values():
        for area_loc in area_locations:
            if area_loc in loc_lower:
                return True
    return False


def get_abu_dhabi_area(location: str) -> str | None:
    """Get the Abu Dhabi area for a location."""
    if not location:
        return None
    loc_lower = location.lower().strip()
    for area, locations in ABU_DHABI_AREAS.items():
        for area_loc in locations:
            if area_loc in loc_lower:
                return area
    return None


@dataclass
class ShootDay:
    """Represents a planned shoot day with associated tasks."""

    date: date
    area: str  # 'GALLERIA_MALL' or 'AL_QANA'
    time_blocks: list[str] = field(default_factory=list)  # ['day', 'night', 'both']
    tasks: list[int] = field(default_factory=list)  # Task IDs
    score: int = 0  # Overlap score

    def can_add_time_block(self, time_block: str) -> bool:
        """Check if time block is compatible with current shoot."""
        if time_block == "both":
            return True
        if "both" in self.time_blocks:
            return True
        if time_block in self.time_blocks:
            return True
        # Can add both 'day' and 'night' to same shoot
        return True

    def add_task(self, task_id: int, time_block: str) -> None:
        """Add a task to this shoot day."""
        self.tasks.append(task_id)
        if time_block not in self.time_blocks and time_block != "both":
            self.time_blocks.append(time_block)


class AbuDhabiScheduler(Scheduler):
    """
    Dynamic scheduler for Abu Dhabi locations.

    Optimizes filming dates across all pending tasks to maximize
    campaign bundling while respecting constraints.
    """

    def __init__(self, config: SchedulingConfig | None = None):
        """Initialize with Abu Dhabi specific defaults."""
        if config is None:
            config = SchedulingConfig(
                abu_dhabi_allowed_weekdays=[1, 3, 4],  # Tue, Thu, Fri
                max_shoots_per_week=2,
                min_gap_between_shoots_days=1,
                min_campaigns_per_shoot=2,
                freeze_threshold_hours=24,
            )
        super().__init__(config)

    def calculate_filming_date(
        self,
        campaign_start: date,
        campaign_end: date | None = None,
        location: str | None = None,
        time_block: str | None = None,
        pending_tasks: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> date:
        """
        Calculate filming date for an Abu Dhabi task.

        For individual tasks, finds the best date based on campaign window.
        For batch processing, use plan_all_shoots() instead.

        Args:
            campaign_start: Campaign start date
            campaign_end: Campaign end date
            location: Location name
            time_block: Time block ('day', 'night', 'both')
            pending_tasks: Optional list of other pending tasks for bundling
            **kwargs: Additional parameters

        Returns:
            Calculated filming date
        """
        if isinstance(campaign_start, datetime):
            campaign_start = campaign_start.date()
        if isinstance(campaign_end, datetime):
            campaign_end = campaign_end.date()

        # Default end date if not provided
        if not campaign_end:
            campaign_end = campaign_start + timedelta(days=30)

        area = get_abu_dhabi_area(location) if location else None
        time_block = (time_block or "both").lower()

        # Get candidate dates
        candidates = self._get_candidate_dates(campaign_start, campaign_end)

        if not candidates:
            # No valid candidates - fall back to campaign start + lead time
            return self.add_working_days(campaign_start, self.config.lead_time_days)

        # If no pending tasks provided, just return best candidate
        if not pending_tasks:
            return candidates[0]

        # Calculate scores for each candidate
        best_date = candidates[0]
        best_score = 0

        for candidate in candidates:
            score, _ = self._calculate_overlap_score(
                candidate, area, time_block, pending_tasks
            )
            if score > best_score:
                best_score = score
                best_date = candidate

        return best_date

    def plan_all_shoots(
        self,
        tasks: list[dict[str, Any]],
        today: date | None = None,
        weeks_ahead: int = 4,
    ) -> dict[str, list[ShootDay]]:
        """
        Plan optimal shoots for all Abu Dhabi tasks.

        Groups tasks by area and plans shoots to maximize campaign bundling.

        Args:
            tasks: All pending Abu Dhabi tasks
            today: Current date (defaults to today)
            weeks_ahead: Number of weeks to plan ahead

        Returns:
            Dict mapping week keys to lists of ShootDay objects
        """
        if today is None:
            today = datetime.now().date()

        schedule: dict[str, list[ShootDay]] = defaultdict(list)

        # Group tasks by area
        tasks_by_area: dict[str, list[dict]] = defaultdict(list)
        for task in tasks:
            location = task.get("Location", "")
            area = get_abu_dhabi_area(location)
            if area:
                tasks_by_area[area].append(task)

        # Plan each week
        for week_offset in range(weeks_ahead):
            week_start = today + timedelta(days=(7 - today.weekday()) % 7 + week_offset * 7)
            week_key = self._get_week_key(week_start)

            for area, area_tasks in tasks_by_area.items():
                # Filter non-frozen tasks
                active_tasks = [
                    t for t in area_tasks
                    if not self.is_frozen(t, today)
                ]

                if active_tasks:
                    week_shoots = self._plan_week_shoots(
                        area, active_tasks, week_start, schedule
                    )
                    schedule[week_key].extend(week_shoots)

        return dict(schedule)

    def is_frozen(self, task: dict[str, Any], today: date) -> bool:
        """
        Check if task is frozen (T-1 rule).

        Task is frozen if within freeze_threshold_hours of filming.

        Args:
            task: Task dict with 'Filming Date' field
            today: Current date

        Returns:
            True if frozen
        """
        filming_date_str = task.get("Filming Date")
        if not filming_date_str:
            return False

        try:
            filming_date = datetime.strptime(filming_date_str, "%d-%m-%Y").date()
            delta_days = (filming_date - today).days
            freeze_threshold_days = self.config.freeze_threshold_hours / 24.0
            return delta_days <= freeze_threshold_days
        except (ValueError, TypeError):
            return False

    def _get_candidate_dates(
        self,
        campaign_start: date,
        campaign_end: date,
        today: date | None = None,
    ) -> list[date]:
        """Get valid candidate shoot dates within campaign window."""
        if today is None:
            today = datetime.now().date()

        allowed_weekdays = self.config.abu_dhabi_allowed_weekdays
        start_date = max(today, campaign_start)

        candidates = []
        current = start_date

        while current <= campaign_end:
            if current.weekday() in allowed_weekdays:
                if self.is_working_day(current):
                    candidates.append(current)
            current += timedelta(days=1)

        return candidates

    def _calculate_overlap_score(
        self,
        shoot_date: date,
        area: str | None,
        time_block: str,
        tasks: list[dict[str, Any]],
    ) -> tuple[int, list[int]]:
        """
        Calculate how many campaigns are live on shoot_date.

        Args:
            shoot_date: Proposed filming date
            area: Abu Dhabi area
            time_block: Time block
            tasks: Pending tasks

        Returns:
            Tuple of (score, matching task IDs)
        """
        score = 0
        matching_tasks = []

        for task in tasks:
            # Check area match
            task_location = task.get("Location", "")
            task_area = get_abu_dhabi_area(task_location)
            if area and task_area != area:
                continue

            # Check time block compatibility
            task_time_block = (task.get("Time Block") or "both").lower()
            is_compatible = (
                time_block == "both"
                or task_time_block == "both"
                or time_block == task_time_block
            )
            if not is_compatible:
                continue

            # Check if campaign is live on shoot_date
            try:
                start_str = task.get("Campaign Start Date", "")
                end_str = task.get("Campaign End Date", "")

                if not start_str:
                    continue

                start_date = datetime.strptime(start_str, "%d-%m-%Y").date()
                end_date = (
                    datetime.strptime(end_str, "%d-%m-%Y").date()
                    if end_str
                    else start_date + timedelta(days=30)
                )

                if start_date <= shoot_date <= end_date:
                    score += 1
                    task_id = task.get("Task #", task.get("task_number"))
                    if task_id:
                        matching_tasks.append(task_id)

            except (ValueError, TypeError):
                continue

        return score, matching_tasks

    def _can_add_shoot_to_week(
        self,
        proposed_date: date,
        existing_shoots: list[date],
    ) -> bool:
        """Check if adding a shoot violates weekly constraints."""
        # Check weekday constraint
        if proposed_date.weekday() not in self.config.abu_dhabi_allowed_weekdays:
            return False

        # Check max shoots per week
        if len(existing_shoots) >= self.config.max_shoots_per_week:
            return False

        # Check minimum gap
        for existing in existing_shoots:
            gap = abs((proposed_date - existing).days)
            if gap < self.config.min_gap_between_shoots_days:
                return False

        return True

    def _get_week_key(self, date_obj: date) -> str:
        """Get ISO week key (e.g., '2025-W03')."""
        iso = date_obj.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    def _plan_week_shoots(
        self,
        area: str,
        tasks: list[dict[str, Any]],
        week_start: date,
        existing_schedule: dict[str, list[ShootDay]],
    ) -> list[ShootDay]:
        """Plan optimal shoots for one area in one week."""
        week_end = week_start + timedelta(days=6)
        planned_shoots = []

        # Get existing shoot dates
        existing_dates = []
        for week_shoots in existing_schedule.values():
            for shoot in week_shoots:
                if shoot.area == area:
                    existing_dates.append(shoot.date)

        # Filter tasks relevant to this week
        relevant_tasks = []
        for task in tasks:
            try:
                start_str = task.get("Campaign Start Date", "")
                end_str = task.get("Campaign End Date", "")

                if not start_str:
                    continue

                start_date = datetime.strptime(start_str, "%d-%m-%Y").date()
                end_date = (
                    datetime.strptime(end_str, "%d-%m-%Y").date()
                    if end_str
                    else start_date + timedelta(days=30)
                )

                # Check overlap with week
                if not (end_date < week_start or start_date > week_end):
                    relevant_tasks.append(task)
            except (ValueError, TypeError):
                continue

        if not relevant_tasks:
            return planned_shoots

        # Generate candidates for this week
        candidates = self._get_candidate_dates(week_start, week_end)

        # Try to add shoots until week is full
        while len(planned_shoots) < self.config.max_shoots_per_week:
            best_date = None
            best_score = 0
            best_tasks = []
            best_time_blocks = set()

            for candidate in candidates:
                # Check constraints
                all_shoots = existing_dates + [s.date for s in planned_shoots]
                if not self._can_add_shoot_to_week(candidate, all_shoots):
                    continue

                # Calculate scores for each time block
                for time_block in ["day", "night", "both"]:
                    score, matching_tasks = self._calculate_overlap_score(
                        candidate, area, time_block, relevant_tasks
                    )

                    if score > best_score:
                        best_score = score
                        best_date = candidate
                        best_tasks = matching_tasks
                        best_time_blocks = {time_block}

            # Add shoot if score meets minimum
            if best_date and best_score >= self.config.min_campaigns_per_shoot:
                shoot = ShootDay(
                    date=best_date,
                    area=area,
                    time_blocks=list(best_time_blocks),
                    tasks=best_tasks,
                    score=best_score,
                )
                planned_shoots.append(shoot)
                logger.info(f"[AbuDhabiScheduler] Planned shoot: {shoot}")
            else:
                break

        return planned_shoots
