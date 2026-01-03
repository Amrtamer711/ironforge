"""
Trello Integration for Video Critique.

This module provides a clean API client for Trello operations
required by the video production workflow:
- Task card management
- Videographer list management
- Leave tracking via "On Leave" cards
- Workload balancing
- Production timeline checklists

Usage:
    from integrations.trello import TrelloClient

    # Initialize client
    client = TrelloClient.from_config()

    # Get card for a task
    card = client.get_card_by_task_number(123)

    # Create a new task card
    result = await client.create_card_async(
        title="Task #124: Brand - Location",
        list_name="Videographer Name",
        due_date=filming_date,
    )

    # Check workloads
    from integrations.trello import get_all_workloads
    workloads, on_leave = get_all_workloads(client, videographer_list)
"""

from integrations.trello.client import (
    CardResult,
    ListResult,
    TrelloClient,
)
from integrations.trello.operations import (
    AssignmentRecommendation,
    WorkloadInfo,
    build_task_card_description,
    build_task_card_title,
    count_active_tasks,
    create_production_timeline_checklist,
    create_production_timeline_checklist_async,
    get_all_workloads,
    get_all_workloads_async,
    get_best_videographer_for_assignment,
    get_best_videographer_for_assignment_async,
    get_leave_dates,
    get_leave_dates_async,
    get_videographer_cards,
    get_videographer_cards_async,
    get_videographer_workload,
    get_videographer_workload_async,
    is_videographer_on_leave,
    is_videographer_on_leave_async,
    update_production_timeline_dates,
    update_production_timeline_dates_async,
    will_be_available_on_date,
    will_be_available_on_date_async,
)

__all__ = [
    # Client
    "TrelloClient",
    "CardResult",
    "ListResult",
    # Data classes
    "WorkloadInfo",
    "AssignmentRecommendation",
    # Videographer operations
    "get_videographer_cards",
    "get_videographer_cards_async",
    "get_videographer_workload",
    "get_videographer_workload_async",
    "count_active_tasks",
    # Leave management
    "is_videographer_on_leave",
    "is_videographer_on_leave_async",
    "get_leave_dates",
    "get_leave_dates_async",
    "will_be_available_on_date",
    "will_be_available_on_date_async",
    # Workload balancing
    "get_all_workloads",
    "get_all_workloads_async",
    "get_best_videographer_for_assignment",
    "get_best_videographer_for_assignment_async",
    # Task card utilities
    "build_task_card_title",
    "build_task_card_description",
    # Checklist utilities
    "create_production_timeline_checklist",
    "create_production_timeline_checklist_async",
    "update_production_timeline_dates",
    "update_production_timeline_dates_async",
]
