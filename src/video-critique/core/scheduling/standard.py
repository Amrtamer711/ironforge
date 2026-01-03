"""
Standard Scheduler for Video Critique.

Implements standard filming date calculation rules:
- Main filming dates are 2nd and 17th of each month
- If campaign is too short, use lead time days post campaign start
- If filming lands on non-working day, use previous working day
"""

from datetime import date, datetime, timedelta

from core.scheduling.base import Scheduler, SchedulingConfig
from core.utils.logging import get_logger

logger = get_logger(__name__)


class StandardScheduler(Scheduler):
    """
    Standard filming date scheduler.

    Uses fixed monthly filming dates (2nd and 17th) with fallback
    rules for short campaigns and non-working days.
    """

    def calculate_filming_date(
        self,
        campaign_start: date,
        campaign_end: date | None = None,
        **kwargs,
    ) -> date:
        """
        Calculate filming date based on standard rules.

        Rules:
        1. Main filming dates are 2nd and 17th of each month
        2. If campaign is too short (ends before next filming date),
           use lead_time_days after campaign start
        3. If filming date lands on non-working day, use previous working day

        Args:
            campaign_start: Campaign start date
            campaign_end: Campaign end date
            **kwargs: Additional parameters (ignored)

        Returns:
            Calculated filming date
        """
        # Convert datetime to date if needed
        if isinstance(campaign_start, datetime):
            campaign_start = campaign_start.date()
        if isinstance(campaign_end, datetime):
            campaign_end = campaign_end.date()

        # Find the next main filming date (2nd or 17th)
        next_filming = self._get_next_main_filming_date(campaign_start)

        # Check if campaign ends before the filming date
        if campaign_end and next_filming > campaign_end:
            # Campaign too short - use lead time days post campaign start
            next_filming = self.add_working_days(
                campaign_start, self.config.lead_time_days
            )

        # Ensure filming date is a working day (use previous if not)
        if not self.is_working_day(next_filming):
            next_filming = self.get_previous_working_day(next_filming)

        return next_filming

    def _get_next_main_filming_date(self, from_date: date) -> date:
        """
        Get the next main filming date (2nd or 17th) from a given date.

        Args:
            from_date: Date to start searching from

        Returns:
            Next main filming date
        """
        main_days = self.config.main_filming_days
        day = from_date.day
        month = from_date.month
        year = from_date.year

        # Sort main filming days to find next one
        sorted_days = sorted(main_days)

        # Find next filming day in current month
        for filming_day in sorted_days:
            if day <= filming_day:
                try:
                    return date(year, month, filming_day)
                except ValueError:
                    # Day doesn't exist in this month
                    continue

        # Move to next month
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1

        # Return first main filming day of next month
        return date(year, month, sorted_days[0])

    def calculate_editing_deadline(
        self,
        filming_date: date,
        working_days: int = 3,
    ) -> date:
        """
        Calculate the editing deadline based on filming date.

        Args:
            filming_date: Filming date
            working_days: Number of working days after filming

        Returns:
            Editing deadline date
        """
        return self.add_working_days(filming_date, working_days)
