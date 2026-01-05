"""
Abu Dhabi Dynamic Scheduling Algorithm

This module implements a holistic, dynamic scheduling algorithm for Abu Dhabi locations.
It optimizes filming dates for all pending Abu Dhabi tasks simultaneously, maximizing
campaign bundling while respecting hard constraints.

Key Features:
- Plans all Abu Dhabi tasks together (not individually)
- Maximizes campaign overlap on shoot dates
- Enforces: max 2 shoots/week, Tue/Thu/Fri only, min 1-day gap
- Respects T-1 freeze rule (no changes within 24hrs of shoot)
- Handles time blocks (DAY/NIGHT/BOTH)
"""

from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict
import pytz
from logger import logger
from abu_dhabi_config import (
    get_abu_dhabi_area,
    is_abu_dhabi_location,
    get_scheduling_config,
    get_area_display_name
)
from uae_holidays import is_working_day

UAE_TZ = pytz.timezone('Asia/Dubai')


class ShootDay:
    """Represents a planned shoot day with associated tasks"""
    def __init__(self, date: date, area: str, time_blocks: List[str]):
        self.date = date
        self.area = area  # 'GALLERIA_MALL' or 'AL_QANA'
        self.time_blocks = time_blocks  # ['day', 'night', 'both']
        self.tasks = []  # Task IDs assigned to this shoot
        self.score = 0  # Overlap score

    def can_add_time_block(self, time_block: str) -> bool:
        """Check if this time block is compatible with current shoot"""
        if time_block == 'both':
            return True
        if 'both' in self.time_blocks:
            return True
        if time_block in self.time_blocks:
            return True
        # Can add both 'day' and 'night' to same shoot
        return True

    def add_task(self, task_id: int, time_block: str):
        """Add a task to this shoot day"""
        self.tasks.append(task_id)
        if time_block not in self.time_blocks and time_block != 'both':
            self.time_blocks.append(time_block)

    def __repr__(self):
        return f"ShootDay({self.date}, {self.area}, blocks={self.time_blocks}, tasks={len(self.tasks)})"


def is_frozen(task: Dict[str, Any], today: date) -> bool:
    """
    Check if task is frozen (T-1 rule: within 24 hours of filming).

    Args:
        task: Task dict with 'Filming Date' field
        today: Current date

    Returns:
        True if task is frozen and should not be rescheduled
    """
    filming_date_str = task.get('Filming Date')
    if not filming_date_str:
        return False  # No filming date set yet, not frozen

    try:
        filming_date = datetime.strptime(filming_date_str, '%d-%m-%Y').date()
        delta = (filming_date - today).days

        config = get_scheduling_config()
        freeze_threshold_hours = config.get('freeze_threshold_hours', 24)
        freeze_threshold_days = freeze_threshold_hours / 24.0

        return delta <= freeze_threshold_days
    except:
        return False


def get_candidate_dates(
    campaign_start: date,
    campaign_end: date,
    week_limit: int = 4,
    today: Optional[date] = None
) -> List[date]:
    """
    Generate candidate shoot dates within campaign window.

    Rules:
    - Only Tue/Thu/Fri (configurable via allowed_weekdays)
    - Within campaign window
    - Up to week_limit weeks ahead
    - Must be future dates

    Args:
        campaign_start: Campaign start date
        campaign_end: Campaign end date
        week_limit: Max weeks to look ahead
        today: Current date (defaults to today)

    Returns:
        List of valid candidate dates
    """
    if today is None:
        today = datetime.now(UAE_TZ).date()

    config = get_scheduling_config()
    allowed_weekdays = config.get('allowed_weekdays', [1, 3, 4])  # Tue=1, Thu=3, Fri=4

    # Start from max of today and campaign_start
    start_date = max(today, campaign_start)
    end_date = min(campaign_end, today + timedelta(weeks=week_limit))

    candidates = []
    current = start_date

    while current <= end_date:
        # Check if weekday is allowed (Mon=0, Tue=1, ..., Sun=6)
        if current.weekday() in allowed_weekdays:
            candidates.append(current)
        current += timedelta(days=1)

    return candidates


def calculate_live_overlap_score(
    shoot_date: date,
    area: str,
    time_block: str,
    pending_tasks: List[Dict[str, Any]]
) -> Tuple[int, List[int]]:
    """
    Count how many campaigns are live on shoot_date.

    Campaign is "live" if:
    - campaign_start_date <= shoot_date <= campaign_end_date
    - Same area
    - Compatible time_block

    Args:
        shoot_date: Proposed filming date
        area: 'GALLERIA_MALL' or 'AL_QANA'
        time_block: 'day', 'night', or 'both'
        pending_tasks: List of pending task dicts

    Returns:
        Tuple of (score, list of matching task numbers)
    """
    score = 0
    matching_tasks = []

    for task in pending_tasks:
        # Check area match
        task_location = task.get('Location', '')
        task_area = get_abu_dhabi_area(task_location)
        if task_area != area:
            continue

        # Check time block compatibility
        task_time_block = (task.get('Time Block') or '').lower()
        if not task_time_block:
            continue

        # Time blocks are compatible if:
        # - Either is 'both'
        # - They match exactly
        # - Different blocks can share same day (day + night = both)
        is_compatible = (
            time_block == 'both' or
            task_time_block == 'both' or
            time_block == task_time_block
        )

        if not is_compatible:
            continue

        # Check if campaign is live on shoot_date
        try:
            start_str = task.get('Campaign Start Date', '')
            end_str = task.get('Campaign End Date', '')

            if not start_str:
                continue

            start_date = datetime.strptime(start_str, '%d-%m-%Y').date()

            # If no end date, use start date + 30 days as default
            if end_str:
                end_date = datetime.strptime(end_str, '%d-%m-%Y').date()
            else:
                end_date = start_date + timedelta(days=30)

            # Check if shoot_date is within campaign window
            if start_date <= shoot_date <= end_date:
                score += 1
                matching_tasks.append(task.get('Task #', task.get('task_number')))

        except Exception as e:
            logger.warning(f"Error parsing dates for task {task.get('Task #')}: {e}")
            continue

    return score, matching_tasks


def can_add_shoot_to_week(
    proposed_date: date,
    existing_shoots: List[date]
) -> bool:
    """
    Check if adding a shoot violates weekly constraints.

    Returns True if:
    - Week has < 2 shoots
    - Proposed date has >= 1 day gap from existing shoots
    - Proposed date is Tue/Thu/Fri

    Args:
        proposed_date: Date we want to add
        existing_shoots: List of already scheduled shoot dates in same week

    Returns:
        True if we can add this shoot, False otherwise
    """
    config = get_scheduling_config()
    max_shoots_per_week = config.get('max_shoots_per_week', 2)
    min_gap_days = config.get('min_gap_between_shoots_days', 1)
    allowed_weekdays = config.get('allowed_weekdays', [1, 3, 4])

    # Check weekday constraint
    if proposed_date.weekday() not in allowed_weekdays:
        return False

    # Check max shoots per week
    if len(existing_shoots) >= max_shoots_per_week:
        return False

    # Check minimum gap
    for existing in existing_shoots:
        gap = abs((proposed_date - existing).days)
        if gap < min_gap_days:
            return False

    return True


def get_week_key(date_obj: date) -> str:
    """Get ISO week key (e.g., '2025-W03')"""
    iso = date_obj.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def plan_week_shoots(
    area: str,
    tasks: List[Dict[str, Any]],
    week_start: date,
    existing_schedule: Dict[str, List[ShootDay]]
) -> List[ShootDay]:
    """
    Plan optimal shoots for one area in one week.

    Algorithm:
    1. Generate all candidate dates (Tue/Thu/Fri) in this week
    2. For each candidate, calculate overlap score
    3. Select date with highest score
    4. Repeat until week is full (2 shoots) or no more tasks

    Args:
        area: 'GALLERIA_MALL' or 'AL_QANA'
        tasks: All pending tasks for this area
        week_start: Start date of the week
        existing_schedule: Already planned shoots (may affect constraints)

    Returns:
        List of ShootDay objects for this week
    """
    week_end = week_start + timedelta(days=6)
    week_key = get_week_key(week_start)

    # Get existing shoots from ALL weeks in the schedule (not just this planning week)
    # This is needed because candidates can span ISO week boundaries
    existing_shoots_in_week = []
    for week_shoots in existing_schedule.values():
        existing_shoots_in_week.extend(week_shoots)
    existing_dates = [shoot.date for shoot in existing_shoots_in_week]

    planned_shoots = []
    config = get_scheduling_config()
    preferred_weekdays = config.get('preferred_weekdays', [1, 4, 3])  # Tue, Fri, Thu

    # Filter tasks that have campaigns overlapping this week
    relevant_tasks = []
    for task in tasks:
        try:
            start_str = task.get('Campaign Start Date', '')
            end_str = task.get('Campaign End Date', '')

            if not start_str:
                continue

            start_date = datetime.strptime(start_str, '%d-%m-%Y').date()
            end_date = datetime.strptime(end_str, '%d-%m-%Y').date() if end_str else start_date + timedelta(days=30)

            # Check if campaign overlaps with this week
            if not (end_date < week_start or start_date > week_end):
                relevant_tasks.append(task)
        except:
            continue

    if not relevant_tasks:
        return planned_shoots

    # Generate candidate dates for this week (Tue/Thu/Fri)
    # Use large week_limit since week_start/week_end already constrain the range
    candidates = get_candidate_dates(week_start, week_end, week_limit=52)

    # Sort candidates by preferred weekday order
    def weekday_priority(d: date) -> int:
        try:
            return preferred_weekdays.index(d.weekday())
        except ValueError:
            return 999

    candidates.sort(key=weekday_priority)

    # Try to add shoots until week is full
    while len(planned_shoots) < config.get('max_shoots_per_week', 2):
        best_date = None
        best_score = 0
        best_tasks = []
        best_time_blocks = set()

        for candidate in candidates:
            # Check if we can add this date
            # Filter existing_dates to only those in the same ISO week as candidate
            candidate_week = get_week_key(candidate)
            existing_in_same_week = [d for d in existing_dates if get_week_key(d) == candidate_week]
            all_shoots_in_week = existing_in_same_week + [s.date for s in planned_shoots]
            if not can_add_shoot_to_week(candidate, all_shoots_in_week):
                continue

            # Calculate score for each time block
            for time_block in ['day', 'night', 'both']:
                score, matching_tasks = calculate_live_overlap_score(
                    candidate, area, time_block, relevant_tasks
                )

                if score > best_score:
                    best_score = score
                    best_date = candidate
                    best_tasks = matching_tasks
                    best_time_blocks = {time_block}

        # If we found a good date, add it
        if best_date and best_score >= config.get('min_campaigns_per_shoot', 2):
            shoot = ShootDay(best_date, area, list(best_time_blocks))
            shoot.score = best_score
            shoot.tasks = best_tasks
            planned_shoots.append(shoot)
            logger.info(f"Planned shoot: {shoot}")
        else:
            break  # No more good candidates

    return planned_shoots


async def notify_unschedulable_tasks(tasks: List[Dict[str, Any]]):
    """
    Notify Reviewer and Head of Sales about campaigns that couldn't be scheduled.

    Args:
        tasks: List of tasks that couldn't be assigned filming dates
    """
    if not tasks:
        return

    try:
        import asyncio
        from messaging import send_message
        from config import VIDEOGRAPHER_CONFIG_PATH
        import json

        with open(VIDEOGRAPHER_CONFIG_PATH) as f:
            config = json.load(f)

        # Build notification message
        task_details = []
        for task in tasks:
            task_num = task.get('Task #', task.get('task_number', 'Unknown'))
            brand = task.get('Brand', 'Unknown')
            location = task.get('Location', 'Unknown')
            campaign_end = task.get('Campaign End Date', 'Unknown')
            sales_person = task.get('Sales Person', 'Unknown')

            task_details.append(
                f"• Task #{task_num}: {brand} at {location}\n"
                f"  Sales: {sales_person} | Expires: {campaign_end}"
            )

        message = (
            f"🚨 **CRITICAL: Abu Dhabi Scheduling Failure**\n\n"
            f"{len(tasks)} campaign(s) could NOT be scheduled even after fallback strategies:\n\n"
            + "\n".join(task_details) +
            f"\n\n**This is critical** - All normal and fallback scheduling attempts failed.\n"
            f"Possible reasons:\n"
            f"• Campaign dates fall outside valid filming windows (Tue/Thu/Fri)\n"
            f"• Campaign period is too short with no available dates\n"
            f"• All available dates are already frozen (T-1 rule)\n\n"
            f"**IMMEDIATE ACTION REQUIRED**: Manual intervention needed to prevent missed campaigns\n\n"
            f"_This is an automated alert from the Abu Dhabi scheduling system_"
        )

        # Notify Reviewer
        reviewer = config.get('reviewer', {})
        if reviewer:
            reviewer_data = list(reviewer.values())[0] if isinstance(reviewer, dict) else reviewer
            reviewer_channel = reviewer_data.get('slack_channel_id')
            if reviewer_channel:
                await send_message(reviewer_channel, message)
                logger.info(f"✅ Notified Reviewer about {len(tasks)} unschedulable tasks")

        # Notify Head of Sales
        hos = config.get('head_of_sales', {})
        hos_channel = hos.get('slack_channel_id')
        if hos_channel:
            await send_message(hos_channel, message)
            logger.info(f"✅ Notified Head of Sales about {len(tasks)} unschedulable tasks")

    except Exception as e:
        logger.error(f"Failed to send unschedulable task notifications: {e}")


async def schedule_abu_dhabi_tasks(pending_tasks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Main scheduling algorithm - optimizes all pending Abu Dhabi tasks.

    This function:
    1. Fetches all pending Abu Dhabi tasks
    2. Groups by area (Galleria / Al Qana)
    3. Plans optimal shoot dates for 4 weeks ahead
    4. Notifies stakeholders about unschedulable tasks
    5. Returns filming date assignments

    Args:
        pending_tasks: Optional list of pending tasks (if None, fetches from DB)

    Returns:
        Dict mapping task_number -> assigned_filming_date
    """
    today = datetime.now(UAE_TZ).date()

    # Fetch pending tasks if not provided
    if pending_tasks is None:
        from db_utils import select_all_tasks
        all_tasks = select_all_tasks()
        pending_tasks = [t for t in all_tasks if t.get('Status') == 'Not assigned yet']

    # Filter for Abu Dhabi locations only
    abu_dhabi_tasks = [
        task for task in pending_tasks
        if is_abu_dhabi_location(task.get('Location', ''))
    ]

    if not abu_dhabi_tasks:
        logger.info("No pending Abu Dhabi tasks")
        return {}

    # Filter out frozen tasks
    unfrozen_tasks = [
        task for task in abu_dhabi_tasks
        if not is_frozen(task, today)
    ]

    if not unfrozen_tasks:
        logger.info("All Abu Dhabi tasks are frozen")
        return {}

    logger.info(f"Processing {len(unfrozen_tasks)} Abu Dhabi tasks")

    # Group by area
    galleria_tasks = [t for t in unfrozen_tasks if get_abu_dhabi_area(t.get('Location')) == 'GALLERIA_MALL']
    alqana_tasks = [t for t in unfrozen_tasks if get_abu_dhabi_area(t.get('Location')) == 'AL_QANA']

    logger.info(f"Galleria: {len(galleria_tasks)}, Al Qana: {len(alqana_tasks)}")

    # Build weekly schedule
    schedule = {}
    config = get_scheduling_config()
    horizon_weeks = config.get('planning_horizon_weeks', 4)

    for week_offset in range(horizon_weeks):
        week_start = today + timedelta(weeks=week_offset)
        week_key = get_week_key(week_start)

        # Plan shoots for both areas
        # Plan Galleria first
        galleria_shoots = plan_week_shoots('GALLERIA_MALL', galleria_tasks, week_start, schedule)

        # Add Galleria shoots to schedule BEFORE planning Al Qana
        # Use each shoot's actual date's ISO week, not the planning week
        for shoot in galleria_shoots:
            shoot_week = get_week_key(shoot.date)
            if shoot_week not in schedule:
                schedule[shoot_week] = []
            schedule[shoot_week].append(shoot)

        # Now plan Al Qana with awareness of Galleria's shoots
        alqana_shoots = plan_week_shoots('AL_QANA', alqana_tasks, week_start, schedule)

        # Add Al Qana shoots to schedule using their actual date's ISO week
        for shoot in alqana_shoots:
            shoot_week = get_week_key(shoot.date)
            if shoot_week not in schedule:
                schedule[shoot_week] = []
            schedule[shoot_week].append(shoot)

        # Log planning for this week
        logger.info(f"{week_key}: {len(galleria_shoots) + len(alqana_shoots)} shoots planned")

    # Assign tasks to shoots
    assignments = {}

    for week_key, shoots in schedule.items():
        for shoot in shoots:
            for task_num in shoot.tasks:
                assignments[task_num] = shoot.date.strftime('%d-%m-%Y')

    # Identify tasks that couldn't be scheduled
    assigned_task_nums = set(assignments.keys())
    unassigned_tasks = [
        task for task in unfrozen_tasks
        if (task.get('Task #', task.get('task_number')) not in assigned_task_nums)
    ]

    # FALLBACK STRATEGY: Try aggressive scheduling for unassigned tasks
    if unassigned_tasks:
        logger.warning(f"⚠️ {len(unassigned_tasks)} tasks unassigned after first pass - applying fallback strategies")

        # Sort by urgency (campaign end date)
        def get_expiry_date(task):
            try:
                end_str = task.get('Campaign End Date', '')
                if end_str:
                    return datetime.strptime(end_str, '%d-%m-%Y').date()
            except:
                pass
            return date.max  # Tasks without dates go to end

        unassigned_tasks.sort(key=get_expiry_date)

        # Try to schedule each unassigned task with relaxed constraints
        for task in unassigned_tasks:
            task_num = task.get('Task #', task.get('task_number'))
            area = get_abu_dhabi_area(task.get('Location'))

            if not area:
                continue

            # Get campaign dates
            try:
                start_str = task.get('Campaign Start Date', '')
                end_str = task.get('Campaign End Date', '')
                time_block = task.get('Time Block', 'day')

                if not start_str:
                    continue

                start_date = datetime.strptime(start_str, '%d-%m-%Y').date()
                end_date = datetime.strptime(end_str, '%d-%m-%Y').date() if end_str else start_date + timedelta(days=30)

                # Get valid candidate dates within campaign period
                # For fallback, don't limit by horizon - check entire campaign period
                candidates = get_candidate_dates(start_date, end_date, week_limit=52)  # Look up to 1 year ahead

                if not candidates:
                    logger.warning(f"⚠️ Task #{task_num} has NO valid Tue/Thu/Fri dates (campaign: {start_date} to {end_date}) - will try extreme fallback")
                else:
                    logger.info(f"Fallback: Found {len(candidates)} candidate dates for Task #{task_num}")

                # Find first available date that respects MINIMAL constraints
                best_date = None

                if candidates:
                    for candidate in candidates:
                        week_key = get_week_key(candidate)
                        week_shoots = schedule.get(week_key, [])
                        week_shoot_dates = [s.date for s in week_shoots]

                        # Check minimal constraints (still respect max 2/week and 1-day gap)
                        if can_add_shoot_to_week(candidate, week_shoot_dates):
                            best_date = candidate

                            # Create new shoot
                            new_shoot = ShootDay(best_date, area, [time_block])
                            new_shoot.tasks = [task_num]
                            new_shoot.score = 1

                            if week_key not in schedule:
                                schedule[week_key] = []
                            schedule[week_key].append(new_shoot)

                            assignments[task_num] = best_date.strftime('%d-%m-%Y')
                            logger.info(f"✅ Fallback (minimal constraints): Scheduled Task #{task_num} on {best_date}")
                            break

                # If still no date, try to fit in existing shoot of same area/time on that date
                if not best_date and candidates:
                    for candidate in candidates:
                        week_key = get_week_key(candidate)
                        week_shoots = schedule.get(week_key, [])

                        # Check if there's already a shoot on this date for same area
                        for shoot in week_shoots:
                            if shoot.date == candidate and shoot.area == area:
                                # Add to existing shoot
                                shoot.tasks.append(task_num)
                                # Update time blocks if new time block not already in list
                                if time_block not in shoot.time_blocks:
                                    shoot.time_blocks.append(time_block)
                                assignments[task_num] = candidate.strftime('%d-%m-%Y')
                                logger.info(f"✅ Fallback: Added Task #{task_num} to existing shoot on {candidate}")
                                best_date = candidate
                                break

                        if best_date:
                            break

                # If STILL no date, relax 1-day gap constraint (Tier 3)
                if not best_date and candidates:
                    logger.warning(f"⚠️ FALLBACK Tier 3: Relaxing 1-day gap constraint for Task #{task_num}")
                    for candidate in candidates:
                        week_key = get_week_key(candidate)
                        week_shoots = schedule.get(week_key, [])
                        week_shoot_dates = [s.date for s in week_shoots]

                        # Check max 2/week AND avoid same date as different area (two-area same-day should be last resort)
                        if len(week_shoot_dates) < config.get('max_shoots_per_week', 2) and candidate not in week_shoot_dates:
                            best_date = candidate

                            new_shoot = ShootDay(best_date, area, [time_block])
                            new_shoot.tasks = [task_num]
                            new_shoot.score = 1

                            if week_key not in schedule:
                                schedule[week_key] = []
                            schedule[week_key].append(new_shoot)

                            assignments[task_num] = best_date.strftime('%d-%m-%Y')
                            logger.warning(f"⚠️ FALLBACK (relaxed gap): Scheduled Task #{task_num} on {best_date}")
                            break

                # If STILL no date, relax max 2/week constraint
                if not best_date and candidates:
                    logger.warning(f"⚠️ FALLBACK Tier 4: Relaxing max 2/week constraint for Task #{task_num}")
                    best_date = candidates[0]  # Use first valid Tue/Thu/Fri
                    week_key = get_week_key(best_date)

                    new_shoot = ShootDay(best_date, area, [time_block])
                    new_shoot.tasks = [task_num]
                    new_shoot.score = 1

                    if week_key not in schedule:
                        schedule[week_key] = []
                    schedule[week_key].append(new_shoot)

                    assignments[task_num] = best_date.strftime('%d-%m-%Y')
                    logger.warning(f"⚠️ FALLBACK (relaxed weekly limit): Scheduled Task #{task_num} on {best_date}")

                # If STILL no date, relax Tue/Thu/Fri constraint (ABSOLUTE LAST RESORT)
                # BUT NEVER schedule on weekends/holidays (working week is Mon-Thu only)
                if not best_date:
                    logger.error(f"⚠️ FALLBACK Tier 5 (EXTREME): Relaxing Tue/Thu/Fri constraint for Task #{task_num}")
                    # Find ANY working day (Mon-Thu, excluding holidays) within campaign period
                    current = start_date
                    extreme_candidates = []
                    while current <= end_date and len(extreme_candidates) < 30:  # Limit search
                        # Use is_working_day to check: Mon-Thu (0-3), NOT Fri/Sat/Sun (4/5/6), NOT holidays
                        if current >= today and is_working_day(current, holiday_pad_days=0):
                            extreme_candidates.append(current)
                        current += timedelta(days=1)

                    if extreme_candidates:
                        best_date = extreme_candidates[0]
                        week_key = get_week_key(best_date)

                        new_shoot = ShootDay(best_date, area, [time_block])
                        new_shoot.tasks = [task_num]
                        new_shoot.score = 1

                        if week_key not in schedule:
                            schedule[week_key] = []
                        schedule[week_key].append(new_shoot)

                        assignments[task_num] = best_date.strftime('%d-%m-%Y')
                        logger.error(f"🚨 EXTREME FALLBACK: Scheduled Task #{task_num} on {best_date} ({best_date.strftime('%A')}) - Relaxed to weekday outside Tue/Thu!")

                if not best_date:
                    logger.error(f"❌ CRITICAL: Could not schedule Task #{task_num} - campaign may be expired or no valid dates exist")

            except Exception as e:
                logger.error(f"Error in fallback scheduling for Task #{task_num}: {e}")
                continue

    # Final check: identify truly unschedulable tasks
    final_assigned_nums = set(assignments.keys())
    truly_unschedulable = [
        task for task in unfrozen_tasks
        if (task.get('Task #', task.get('task_number')) not in final_assigned_nums)
    ]

    # Notify stakeholders only about truly unschedulable tasks
    if truly_unschedulable:
        logger.error(f"❌ CRITICAL: {len(truly_unschedulable)} tasks could NOT be scheduled even with fallback")
        await notify_unschedulable_tasks(truly_unschedulable)
    elif unassigned_tasks:
        logger.info(f"✅ Successfully scheduled {len(unassigned_tasks)} tasks using fallback strategies")

    return assignments


def calculate_abu_dhabi_filming_date(
    location: str,
    campaign_start_date: str,
    campaign_end_date: str,
    task_type: str,
    time_block: str,
    all_pending_tasks: List[Dict[str, Any]]
) -> str:
    """
    Calculate optimal filming date for a single Abu Dhabi task.

    This is called when creating a NEW task. It considers all other pending
    Abu Dhabi tasks to find the optimal bundling opportunity.

    Args:
        location: Task location
        campaign_start_date: Campaign start (dd-mm-yyyy)
        campaign_end_date: Campaign end (dd-mm-yyyy)
        task_type: 'videography', 'photography', or 'both'
        time_block: 'day', 'night', or 'both'
        all_pending_tasks: All current pending tasks

    Returns:
        Filming date as dd-mm-yyyy string
    """
    area = get_abu_dhabi_area(location)
    if not area:
        # Not an Abu Dhabi location, shouldn't happen
        logger.error(f"calculate_abu_dhabi_filming_date called for non-Abu Dhabi location: {location}")
        return campaign_start_date

    try:
        start_date = datetime.strptime(campaign_start_date, '%d-%m-%Y').date()
        end_date = datetime.strptime(campaign_end_date, '%d-%m-%Y').date() if campaign_end_date else start_date + timedelta(days=30)
    except:
        logger.error(f"Invalid date format: {campaign_start_date} or {campaign_end_date}")
        return campaign_start_date

    # Get candidate dates
    candidates = get_candidate_dates(start_date, end_date)

    if not candidates:
        logger.warning(f"No valid candidate dates for campaign {campaign_start_date} to {campaign_end_date}")
        return campaign_start_date

    # Score each candidate by overlap with other pending tasks
    best_date = None
    best_score = 0

    for candidate in candidates:
        score, _ = calculate_live_overlap_score(candidate, area, time_block, all_pending_tasks)

        if score > best_score:
            best_score = score
            best_date = candidate

    # Use the date with best overlap, or first candidate if no overlap
    if best_date:
        return best_date.strftime('%d-%m-%Y')
    else:
        return candidates[0].strftime('%d-%m-%Y')
