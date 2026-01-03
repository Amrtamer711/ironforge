"""
Base Scheduler for Video Critique.

Provides abstract interface and common utilities for filming date calculation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SchedulingConfig:
    """Configuration for scheduling rules."""

    # Standard scheduling
    main_filming_days: list[int] = field(default_factory=lambda: [2, 17])
    lead_time_days: int = 2
    weekend_days: set[int] = field(default_factory=lambda: {4, 5})  # Fri=4, Sat=5

    # Abu Dhabi specific
    abu_dhabi_allowed_weekdays: list[int] = field(
        default_factory=lambda: [1, 3, 4]
    )  # Tue=1, Thu=3, Fri=4
    max_shoots_per_week: int = 2
    min_gap_between_shoots_days: int = 1
    min_campaigns_per_shoot: int = 2
    freeze_threshold_hours: int = 24

    # Holiday handling
    holiday_pad_days: int = 0


class Scheduler(ABC):
    """
    Abstract base class for filming date schedulers.

    Different locations may have different scheduling rules.
    Subclasses implement specific scheduling algorithms.
    """

    def __init__(self, config: SchedulingConfig | None = None):
        """
        Initialize scheduler with configuration.

        Args:
            config: Optional SchedulingConfig (uses defaults if not provided)
        """
        self.config = config or SchedulingConfig()

    @abstractmethod
    def calculate_filming_date(
        self,
        campaign_start: date,
        campaign_end: date | None = None,
        **kwargs,
    ) -> date:
        """
        Calculate optimal filming date for a campaign.

        Args:
            campaign_start: Campaign start date
            campaign_end: Campaign end date (optional)
            **kwargs: Additional scheduler-specific parameters

        Returns:
            Calculated filming date
        """
        pass

    def is_working_day(self, check_date: date) -> bool:
        """
        Check if a date is a working day.

        Args:
            check_date: Date to check

        Returns:
            True if working day (not weekend, not holiday)
        """
        # Check weekend
        if check_date.weekday() in self.config.weekend_days:
            return False

        # Check UAE holidays
        try:
            from core.utils.holidays import is_uae_holiday

            if is_uae_holiday(check_date, pad_days=self.config.holiday_pad_days):
                return False
        except ImportError:
            pass

        return True

    def add_working_days(self, start_date: date, num_days: int) -> date:
        """
        Add working days to a date.

        Args:
            start_date: Starting date
            num_days: Number of working days to add

        Returns:
            Date after adding working days
        """
        current = start_date
        days_added = 0

        while days_added < num_days:
            current += timedelta(days=1)
            if self.is_working_day(current):
                days_added += 1

        return current

    def get_previous_working_day(self, check_date: date) -> date:
        """
        Get the previous working day if date is not a working day.

        Args:
            check_date: Date to check

        Returns:
            Previous working day (or same date if already working day)
        """
        current = check_date
        max_iterations = 30

        for _ in range(max_iterations):
            if self.is_working_day(current):
                return current
            current -= timedelta(days=1)

        logger.warning(f"Could not find working day before {check_date}")
        return check_date

    def get_next_working_day(self, check_date: date) -> date:
        """
        Get the next working day if date is not a working day.

        Args:
            check_date: Date to check

        Returns:
            Next working day (or same date if already working day)
        """
        current = check_date
        max_iterations = 30

        for _ in range(max_iterations):
            if self.is_working_day(current):
                return current
            current += timedelta(days=1)

        logger.warning(f"Could not find working day after {check_date}")
        return check_date

    def count_working_days(self, start_date: date, end_date: date) -> int:
        """
        Count working days between two dates (inclusive).

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Number of working days
        """
        if start_date > end_date:
            return 0

        count = 0
        current = start_date

        while current <= end_date:
            if self.is_working_day(current):
                count += 1
            current += timedelta(days=1)

        return count
