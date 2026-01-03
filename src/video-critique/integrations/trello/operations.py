"""
Trello Helper Operations for Video Critique.

Provides utility functions for working with Trello board structure
used in the video production workflow, including:
- Videographer workload tracking
- Leave management via "On Leave" cards
- Task card management
- Checklist timeline management
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from integrations.trello.client import TrelloClient

logger = get_logger(__name__)


@dataclass
class WorkloadInfo:
    """Workload information for a videographer."""
    name: str
    task_count: int
    on_leave: bool = False
    leave_start: date | None = None
    leave_end: date | None = None


@dataclass
class AssignmentRecommendation:
    """Recommendation for task assignment."""
    videographer: str
    workload: int
    reason: str
    all_workloads: dict[str, int]
    unavailable: list[str]


# ========================================================================
# VIDEOGRAPHER CARDS & WORKLOAD
# ========================================================================

def get_videographer_cards(
    client: "TrelloClient",
    videographer_name: str,
    board_id: str | None = None,
) -> list[dict]:
    """
    Get all cards assigned to a videographer (cards in their list).

    Args:
        client: TrelloClient instance
        videographer_name: Name of the videographer (list name)
        board_id: Board ID (uses default if not provided)

    Returns:
        List of card data dicts
    """
    list_id = client.get_list_id(videographer_name, board_id)
    if not list_id:
        return []
    return client.get_cards_in_list(list_id)


async def get_videographer_cards_async(
    client: "TrelloClient",
    videographer_name: str,
    board_id: str | None = None,
) -> list[dict]:
    """Async wrapper for get_videographer_cards."""
    list_id = await client.get_list_id_async(videographer_name, board_id)
    if not list_id:
        return []
    return await client.get_cards_in_list_async(list_id)


def count_active_tasks(cards: list[dict]) -> int:
    """
    Count active tasks from a list of cards.

    Excludes "On Leave" cards from the count.

    Args:
        cards: List of card data dicts

    Returns:
        Number of active task cards
    """
    return sum(
        1 for card in cards
        if card.get("name", "").lower() != "on leave"
    )


def get_videographer_workload(
    client: "TrelloClient",
    videographer_name: str,
    board_id: str | None = None,
) -> int:
    """
    Get the task count for a videographer.

    Args:
        client: TrelloClient instance
        videographer_name: Name of the videographer
        board_id: Board ID

    Returns:
        Number of active tasks
    """
    cards = get_videographer_cards(client, videographer_name, board_id)
    return count_active_tasks(cards)


async def get_videographer_workload_async(
    client: "TrelloClient",
    videographer_name: str,
    board_id: str | None = None,
) -> int:
    """Async wrapper for get_videographer_workload."""
    cards = await get_videographer_cards_async(client, videographer_name, board_id)
    return count_active_tasks(cards)


# ========================================================================
# LEAVE MANAGEMENT
# ========================================================================

def is_videographer_on_leave(
    client: "TrelloClient",
    videographer_name: str,
    board_id: str | None = None,
) -> bool:
    """
    Check if a videographer is currently on leave.

    Leave is indicated by an "On Leave" card in their list.

    Args:
        client: TrelloClient instance
        videographer_name: Name of the videographer
        board_id: Board ID

    Returns:
        True if on leave
    """
    cards = get_videographer_cards(client, videographer_name, board_id)
    return any(
        card.get("name", "").lower() == "on leave"
        for card in cards
    )


async def is_videographer_on_leave_async(
    client: "TrelloClient",
    videographer_name: str,
    board_id: str | None = None,
) -> bool:
    """Async wrapper for is_videographer_on_leave."""
    cards = await get_videographer_cards_async(client, videographer_name, board_id)
    return any(
        card.get("name", "").lower() == "on leave"
        for card in cards
    )


def get_leave_dates(
    client: "TrelloClient",
    videographer_name: str,
    board_id: str | None = None,
) -> tuple[date | None, date | None]:
    """
    Get leave dates from an "On Leave" card.

    The card's start date is the leave start, and due date is leave end.
    If start is not set, falls back to card creation date.

    Args:
        client: TrelloClient instance
        videographer_name: Name of the videographer
        board_id: Board ID

    Returns:
        Tuple of (start_date, end_date), either may be None
    """
    cards = get_videographer_cards(client, videographer_name, board_id)

    for card in cards:
        if card.get("name", "").lower() == "on leave":
            # Start date - prefer 'start' field, fallback to activity date
            start_date_str = card.get("start") or card.get("dateLastActivity")
            end_date_str = card.get("due")

            start_date = None
            end_date = None

            if start_date_str:
                try:
                    start_date = datetime.fromisoformat(
                        start_date_str.replace("Z", "+00:00")
                    ).date()
                except (ValueError, TypeError):
                    pass

            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(
                        end_date_str.replace("Z", "+00:00")
                    ).date()
                except (ValueError, TypeError):
                    pass

            return start_date, end_date

    return None, None


async def get_leave_dates_async(
    client: "TrelloClient",
    videographer_name: str,
    board_id: str | None = None,
) -> tuple[date | None, date | None]:
    """Async wrapper for get_leave_dates."""
    cards = await get_videographer_cards_async(client, videographer_name, board_id)

    for card in cards:
        if card.get("name", "").lower() == "on leave":
            start_date_str = card.get("start") or card.get("dateLastActivity")
            end_date_str = card.get("due")

            start_date = None
            end_date = None

            if start_date_str:
                try:
                    start_date = datetime.fromisoformat(
                        start_date_str.replace("Z", "+00:00")
                    ).date()
                except (ValueError, TypeError):
                    pass

            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(
                        end_date_str.replace("Z", "+00:00")
                    ).date()
                except (ValueError, TypeError):
                    pass

            return start_date, end_date

    return None, None


def will_be_available_on_date(
    client: "TrelloClient",
    videographer_name: str,
    target_date: date | datetime,
    board_id: str | None = None,
) -> bool:
    """
    Check if a videographer will be available on a specific date.

    A videographer is unavailable if the target date falls within
    their leave period (start_date <= target <= end_date).

    Args:
        client: TrelloClient instance
        videographer_name: Name of the videographer
        target_date: Date to check availability
        board_id: Board ID

    Returns:
        True if available on that date
    """
    if not is_videographer_on_leave(client, videographer_name, board_id):
        return True

    start_date, end_date = get_leave_dates(client, videographer_name, board_id)

    # Convert datetime to date if needed
    if isinstance(target_date, datetime):
        target_date = target_date.date()

    # If no dates specified, assume unavailable
    if not start_date and not end_date:
        return False

    # Only end date - on leave until that date (inclusive)
    if not start_date and end_date:
        return target_date > end_date

    # Only start date - on leave from that date onwards
    if start_date and not end_date:
        return target_date < start_date

    # Both dates - check if target falls within leave period
    return not (start_date <= target_date <= end_date)


async def will_be_available_on_date_async(
    client: "TrelloClient",
    videographer_name: str,
    target_date: date | datetime,
    board_id: str | None = None,
) -> bool:
    """Async wrapper for will_be_available_on_date."""
    if not await is_videographer_on_leave_async(client, videographer_name, board_id):
        return True

    start_date, end_date = await get_leave_dates_async(
        client, videographer_name, board_id
    )

    if isinstance(target_date, datetime):
        target_date = target_date.date()

    if not start_date and not end_date:
        return False

    if not start_date and end_date:
        return target_date > end_date

    if start_date and not end_date:
        return target_date < start_date

    return not (start_date <= target_date <= end_date)


# ========================================================================
# WORKLOAD BALANCING
# ========================================================================

def get_all_workloads(
    client: "TrelloClient",
    videographers: list[str],
    board_id: str | None = None,
    target_date: date | datetime | None = None,
    exclude_on_leave: bool = True,
) -> tuple[dict[str, int], list[str]]:
    """
    Get workload for all videographers.

    Args:
        client: TrelloClient instance
        videographers: List of videographer names
        board_id: Board ID
        target_date: If provided, check availability on this date
        exclude_on_leave: Whether to exclude those on leave

    Returns:
        Tuple of (workloads dict, list of on-leave names)
    """
    workloads = {}
    on_leave = []

    for videographer in videographers:
        # Check leave status
        if target_date:
            available = will_be_available_on_date(
                client, videographer, target_date, board_id
            )
            if not available:
                on_leave.append(videographer)
                if exclude_on_leave:
                    continue
        elif is_videographer_on_leave(client, videographer, board_id):
            on_leave.append(videographer)
            if exclude_on_leave:
                continue

        # Get workload
        workload = get_videographer_workload(client, videographer, board_id)
        workloads[videographer] = workload

    return workloads, on_leave


async def get_all_workloads_async(
    client: "TrelloClient",
    videographers: list[str],
    board_id: str | None = None,
    target_date: date | datetime | None = None,
    exclude_on_leave: bool = True,
) -> tuple[dict[str, int], list[str]]:
    """Async wrapper for get_all_workloads."""
    workloads = {}
    on_leave = []

    for videographer in videographers:
        if target_date:
            available = await will_be_available_on_date_async(
                client, videographer, target_date, board_id
            )
            if not available:
                on_leave.append(videographer)
                if exclude_on_leave:
                    continue
        elif await is_videographer_on_leave_async(client, videographer, board_id):
            on_leave.append(videographer)
            if exclude_on_leave:
                continue

        workload = await get_videographer_workload_async(
            client, videographer, board_id
        )
        workloads[videographer] = workload

    return workloads, on_leave


def get_best_videographer_for_assignment(
    client: "TrelloClient",
    videographers: list[str],
    board_id: str | None = None,
    primary_videographer: str | None = None,
    target_date: date | datetime | None = None,
) -> AssignmentRecommendation | None:
    """
    Get the best videographer for a new assignment based on workload.

    Selects the available videographer with the lowest workload,
    excluding the primary videographer and those on leave.

    Args:
        client: TrelloClient instance
        videographers: List of all videographer names
        board_id: Board ID
        primary_videographer: Videographer to exclude (e.g., already assigned)
        target_date: Date to check availability

    Returns:
        AssignmentRecommendation or None if no one available
    """
    workloads, on_leave = get_all_workloads(
        client, videographers, board_id, target_date
    )

    # Filter out primary videographer
    available_workloads = {
        k: v for k, v in workloads.items()
        if k != primary_videographer
    }

    if not available_workloads:
        return None

    # Find minimum workload
    best_videographer = min(available_workloads, key=available_workloads.get)

    return AssignmentRecommendation(
        videographer=best_videographer,
        workload=available_workloads[best_videographer],
        reason="lowest_workload",
        all_workloads=workloads,
        unavailable=on_leave,
    )


async def get_best_videographer_for_assignment_async(
    client: "TrelloClient",
    videographers: list[str],
    board_id: str | None = None,
    primary_videographer: str | None = None,
    target_date: date | datetime | None = None,
) -> AssignmentRecommendation | None:
    """Async wrapper for get_best_videographer_for_assignment."""
    workloads, on_leave = await get_all_workloads_async(
        client, videographers, board_id, target_date
    )

    available_workloads = {
        k: v for k, v in workloads.items()
        if k != primary_videographer
    }

    if not available_workloads:
        return None

    best_videographer = min(available_workloads, key=available_workloads.get)

    return AssignmentRecommendation(
        videographer=best_videographer,
        workload=available_workloads[best_videographer],
        reason="lowest_workload",
        all_workloads=workloads,
        unavailable=on_leave,
    )


# ========================================================================
# TASK CARD UTILITIES
# ========================================================================

def build_task_card_title(
    task_number: int,
    brand: str,
    location: str,
) -> str:
    """
    Build a standard task card title.

    Format: Task #N: Brand - Location

    Args:
        task_number: Task number
        brand: Brand name
        location: Location name

    Returns:
        Formatted card title
    """
    return f"Task #{task_number}: {brand} - {location}"


def build_task_card_description(
    task_number: int,
    brand: str,
    reference_number: str,
    location: str,
    campaign_start: date | datetime | None = None,
    campaign_end: date | datetime | None = None,
    filming_date: date | datetime | None = None,
    sales_person: str | None = None,
    notes: str | None = None,
) -> str:
    """
    Build a standard task card description.

    Args:
        task_number: Task number
        brand: Brand name
        reference_number: Reference number
        location: Location name
        campaign_start: Campaign start date
        campaign_end: Campaign end date
        filming_date: Assigned filming date
        sales_person: Sales person name
        notes: Additional notes

    Returns:
        Formatted card description
    """
    lines = [
        f"**Task #{task_number}**",
        "",
        f"**Brand:** {brand}",
        f"**Reference:** {reference_number}",
        f"**Location:** {location}",
    ]

    if campaign_start:
        if isinstance(campaign_start, datetime):
            campaign_start = campaign_start.date()
        lines.append(f"**Campaign Start:** {campaign_start.strftime('%d-%m-%Y')}")

    if campaign_end:
        if isinstance(campaign_end, datetime):
            campaign_end = campaign_end.date()
        lines.append(f"**Campaign End:** {campaign_end.strftime('%d-%m-%Y')}")

    if filming_date:
        if isinstance(filming_date, datetime):
            filming_date = filming_date.date()
        lines.append(f"**Filming Date:** {filming_date.strftime('%d-%m-%Y')}")

    if sales_person:
        lines.append(f"**Sales Person:** {sales_person}")

    if notes:
        lines.extend(["", "---", "", notes])

    return "\n".join(lines)


# ========================================================================
# CHECKLIST UTILITIES
# ========================================================================

def create_production_timeline_checklist(
    client: "TrelloClient",
    card_id: str,
    filming_date: date | datetime,
    editing_days: int = 3,
    add_working_days_func=None,
) -> bool:
    """
    Create a production timeline checklist on a card.

    Creates checklist items for:
    - Filming (with filming_date as due)
    - Editing (with filming_date + editing_days as due)

    Args:
        client: TrelloClient instance
        card_id: ID of the card
        filming_date: Filming date
        editing_days: Working days after filming for editing deadline
        add_working_days_func: Function to add working days (defaults to simple addition)

    Returns:
        True if successful
    """
    if isinstance(filming_date, date) and not isinstance(filming_date, datetime):
        filming_dt = datetime.combine(filming_date, datetime.min.time())
    else:
        filming_dt = filming_date

    # Calculate editing date
    if add_working_days_func:
        editing_dt = add_working_days_func(filming_dt, editing_days)
    else:
        # Simple fallback - just add calendar days
        editing_dt = filming_dt + timedelta(days=editing_days)

    items = [
        {
            "name": f"Filming - Due: {filming_dt.strftime('%d-%m-%Y')}",
            "due": filming_dt,
        },
        {
            "name": f"Editing - Due: {editing_dt.strftime('%d-%m-%Y')}",
            "due": editing_dt,
        },
    ]

    result = client.create_checklist(card_id, "Video Production Timeline", items)
    return result is not None


async def create_production_timeline_checklist_async(
    client: "TrelloClient",
    card_id: str,
    filming_date: date | datetime,
    editing_days: int = 3,
    add_working_days_func=None,
) -> bool:
    """Async wrapper for create_production_timeline_checklist."""
    if isinstance(filming_date, date) and not isinstance(filming_date, datetime):
        filming_dt = datetime.combine(filming_date, datetime.min.time())
    else:
        filming_dt = filming_date

    if add_working_days_func:
        editing_dt = add_working_days_func(filming_dt, editing_days)
    else:
        editing_dt = filming_dt + timedelta(days=editing_days)

    items = [
        {
            "name": f"Filming - Due: {filming_dt.strftime('%d-%m-%Y')}",
            "due": filming_dt,
        },
        {
            "name": f"Editing - Due: {editing_dt.strftime('%d-%m-%Y')}",
            "due": editing_dt,
        },
    ]

    result = await client.create_checklist_async(
        card_id, "Video Production Timeline", items
    )
    return result is not None


def update_production_timeline_dates(
    client: "TrelloClient",
    card_id: str,
    new_filming_date: date | datetime,
    editing_days: int = 3,
    add_working_days_func=None,
) -> bool:
    """
    Update the production timeline checklist with new dates.

    Args:
        client: TrelloClient instance
        card_id: ID of the card
        new_filming_date: New filming date
        editing_days: Working days after filming for editing
        add_working_days_func: Function to add working days

    Returns:
        True if successful
    """
    if isinstance(new_filming_date, date) and not isinstance(new_filming_date, datetime):
        filming_dt = datetime.combine(new_filming_date, datetime.min.time())
    else:
        filming_dt = new_filming_date

    if add_working_days_func:
        editing_dt = add_working_days_func(filming_dt, editing_days)
    else:
        editing_dt = filming_dt + timedelta(days=editing_days)

    try:
        checklists = client.get_checklists(card_id)

        for checklist in checklists:
            if checklist.get("name") == "Video Production Timeline":
                for item in checklist.get("checkItems", []):
                    item_id = item["id"]
                    item_name = item.get("name", "")

                    if "Filming" in item_name:
                        new_name = f"Filming - Due: {filming_dt.strftime('%d-%m-%Y')}"
                        new_due = filming_dt.strftime("%Y-%m-%dT12:00:00.000Z")
                        client.update_checklist_item(
                            card_id, item_id, name=new_name, due=new_due
                        )

                    elif "Editing" in item_name:
                        new_name = f"Editing - Due: {editing_dt.strftime('%d-%m-%Y')}"
                        new_due = editing_dt.strftime("%Y-%m-%dT12:00:00.000Z")
                        client.update_checklist_item(
                            card_id, item_id, name=new_name, due=new_due
                        )

                return True

        return False

    except Exception as e:
        logger.error(f"[Trello] Error updating timeline dates: {e}")
        return False


async def update_production_timeline_dates_async(
    client: "TrelloClient",
    card_id: str,
    new_filming_date: date | datetime,
    editing_days: int = 3,
    add_working_days_func=None,
) -> bool:
    """Async wrapper for update_production_timeline_dates."""
    if isinstance(new_filming_date, date) and not isinstance(new_filming_date, datetime):
        filming_dt = datetime.combine(new_filming_date, datetime.min.time())
    else:
        filming_dt = new_filming_date

    if add_working_days_func:
        editing_dt = add_working_days_func(filming_dt, editing_days)
    else:
        editing_dt = filming_dt + timedelta(days=editing_days)

    try:
        checklists = await client.get_checklists_async(card_id)

        for checklist in checklists:
            if checklist.get("name") == "Video Production Timeline":
                for item in checklist.get("checkItems", []):
                    item_id = item["id"]
                    item_name = item.get("name", "")

                    if "Filming" in item_name:
                        new_name = f"Filming - Due: {filming_dt.strftime('%d-%m-%Y')}"
                        new_due = filming_dt.strftime("%Y-%m-%dT12:00:00.000Z")
                        await client.update_checklist_item_async(
                            card_id, item_id, name=new_name, due=new_due
                        )

                    elif "Editing" in item_name:
                        new_name = f"Editing - Due: {editing_dt.strftime('%d-%m-%Y')}"
                        new_due = editing_dt.strftime("%Y-%m-%dT12:00:00.000Z")
                        await client.update_checklist_item_async(
                            card_id, item_id, name=new_name, due=new_due
                        )

                return True

        return False

    except Exception as e:
        logger.error(f"[Trello] Error updating timeline dates: {e}")
        return False
