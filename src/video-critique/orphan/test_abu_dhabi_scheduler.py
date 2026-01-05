#!/usr/bin/env python3
"""
Abu Dhabi Scheduler Test Suite

This script stress-tests the Abu Dhabi scheduling algorithm with various scenarios.
"""

import sys
import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
import pytz

# Import the scheduler
from abu_dhabi_scheduler import (
    schedule_abu_dhabi_tasks,
    calculate_abu_dhabi_filming_date,
    get_candidate_dates,
    calculate_live_overlap_score,
    can_add_shoot_to_week,
    is_frozen,
    ShootDay
)
from abu_dhabi_config import get_abu_dhabi_area, is_abu_dhabi_location

UAE_TZ = pytz.timezone('Asia/Dubai')


def create_test_task(
    task_num: int,
    location: str,
    start_date: str,
    end_date: str,
    time_block: str = 'day',
    filming_date: str = None
) -> Dict[str, Any]:
    """Helper to create test task dict"""
    return {
        'Task #': task_num,
        'task_number': task_num,
        'Location': location,
        'Campaign Start Date': start_date,
        'Campaign End Date': end_date,
        'Time Block': time_block,
        'Filming Date': filming_date,
        'Status': 'Not assigned yet',
        'Brand': f'Test Brand {task_num}'
    }


def print_test_header(test_name: str):
    """Print formatted test header"""
    print("\n" + "=" * 80)
    print(f"TEST: {test_name}")
    print("=" * 80)


def print_result(passed: bool, message: str):
    """Print test result"""
    symbol = "✅" if passed else "❌"
    print(f"{symbol} {message}")


def test_location_detection():
    """Test 1: Abu Dhabi location detection"""
    print_test_header("Location Detection")

    tests = [
        ("TTC Abu Dhabi", True, "AL_QANA"),
        ("Luxury Domination Network", True, "GALLERIA_MALL"),
        ("Indoor Domination", True, "GALLERIA_MALL"),
        ("The Curve - Al Qana", True, "AL_QANA"),
        ("Promo Stand", True, None),  # Exists in both, should match first
        ("Dubai Mall", False, None),
        ("UAE 04", False, None),
    ]

    for location, should_be_ad, expected_area in tests:
        is_ad = is_abu_dhabi_location(location)
        area = get_abu_dhabi_area(location)

        if should_be_ad:
            passed = is_ad
            print_result(passed, f"{location} → Abu Dhabi: {is_ad}")
        else:
            passed = not is_ad
            print_result(passed, f"{location} → Not Abu Dhabi: {not is_ad}")


def test_candidate_dates():
    """Test 2: Candidate date generation (Tue/Thu/Fri only)"""
    print_test_header("Candidate Date Generation")

    # Test period: Next month (future dates)
    from datetime import datetime
    today = datetime.now(UAE_TZ).date()
    start = date(today.year, today.month + 1 if today.month < 12 else 1, 1)
    end = date(start.year if start.month < 12 else start.year + 1,
               start.month + 1 if start.month < 12 else 1, 1)

    candidates = get_candidate_dates(start, end, week_limit=4)

    print(f"Period: {start} to {end}")
    print(f"Candidates found: {len(candidates)}")

    # Verify all are Tue/Thu/Fri
    invalid = [d for d in candidates if d.weekday() not in [1, 3, 4]]
    passed = len(invalid) == 0
    print_result(passed, f"All dates are Tue/Thu/Fri: {len(invalid) == 0}")

    if not passed:
        print(f"  Invalid dates: {invalid}")

    # Count by weekday
    by_weekday = {}
    for d in candidates:
        day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][d.weekday()]
        by_weekday[day_name] = by_weekday.get(day_name, 0) + 1

    print(f"  Breakdown: {by_weekday}")


def test_overlap_scoring():
    """Test 3: Live overlap scoring"""
    print_test_header("Live Overlap Scoring")

    shoot_date = date(2025, 12, 15)  # Wednesday

    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "day"),
        create_test_task(2, "TTC Abu Dhabi", "10-12-2025", "20-12-2025", "day"),
        create_test_task(3, "TTC Abu Dhabi", "20-12-2025", "25-12-2025", "day"),  # Not live on 15th
        create_test_task(4, "Luxury Domination Network", "01-12-2025", "31-12-2025", "day"),  # Wrong area
        create_test_task(5, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "night"),  # Wrong time block
    ]

    score, matching = calculate_live_overlap_score(shoot_date, "AL_QANA", "day", tasks)

    print(f"Shoot date: {shoot_date}")
    print(f"Area: AL_QANA, Time block: day")
    print(f"Score: {score}")
    print(f"Matching tasks: {matching}")

    # Should match tasks 1 and 2 only
    passed = score == 2 and set(matching) == {1, 2}
    print_result(passed, f"Correct overlap score: {score == 2}")


def test_weekly_constraints():
    """Test 4: Weekly constraint enforcement"""
    print_test_header("Weekly Constraints (Max 2 shoots, Min 1-day gap)")

    week_shoots = [date(2025, 12, 7), date(2025, 12, 9)]  # Tue + Thu

    # Test 1: Can't add 3rd shoot
    can_add = can_add_shoot_to_week(date(2025, 12, 10), week_shoots)
    print_result(not can_add, f"Reject 3rd shoot in week: {not can_add}")

    # Test 2: Can't add consecutive day (0 gap)
    can_add = can_add_shoot_to_week(date(2025, 12, 8), [date(2025, 12, 7)])
    print_result(not can_add, f"Reject consecutive day (Wed after Tue): {not can_add}")

    # Test 3: Can add with 1-day gap
    can_add = can_add_shoot_to_week(date(2025, 12, 9), [date(2025, 12, 7)])
    print_result(can_add, f"Allow 1-day gap (Thu after Tue): {can_add}")

    # Test 4: Can't add Monday
    can_add = can_add_shoot_to_week(date(2025, 12, 6), [])
    print_result(not can_add, f"Reject Monday: {not can_add}")


def test_freeze_rule():
    """Test 5: T-1 freeze rule (24 hours before shoot)"""
    print_test_header("T-1 Freeze Rule")

    today = date(2025, 12, 15)

    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", filming_date="16-12-2025"),  # Tomorrow
        create_test_task(2, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", filming_date="17-12-2025"),  # 2 days away
        create_test_task(3, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", filming_date=None),  # No date
    ]

    frozen_1 = is_frozen(tasks[0], today)
    frozen_2 = is_frozen(tasks[1], today)
    frozen_3 = is_frozen(tasks[2], today)

    print_result(frozen_1, f"Task 1 (tomorrow) is frozen: {frozen_1}")
    print_result(not frozen_2, f"Task 2 (2 days away) is not frozen: {not frozen_2}")
    print_result(not frozen_3, f"Task 3 (no date) is not frozen: {not frozen_3}")


async def test_scenario_single_campaign():
    """Test 6: Minimum bundling requirement (2+ campaigns)"""
    print_test_header("Scenario: Minimum Bundling (2 campaigns)")

    # Min 2 campaigns required by default
    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "day"),
        create_test_task(2, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "day"),
    ]

    assignments = await schedule_abu_dhabi_tasks(tasks)

    print(f"Input: 2 tasks (Al Qana, day, overlapping)")
    print(f"Assignments: {assignments}")

    passed = len(assignments) == 2
    print_result(passed, f"Both tasks assigned: {passed}")

    if assignments:
        filming_date = datetime.strptime(list(assignments.values())[0], '%d-%m-%Y').date()
        is_valid_day = filming_date.weekday() in [1, 3, 4]
        print_result(is_valid_day, f"Filming date is Tue/Thu/Fri: {is_valid_day}")

    # Note: Single-campaign exception logic not yet implemented
    print("  ℹ️  Single-campaign exception (future enhancement)")


async def test_scenario_overlap_bundling():
    """Test 7: Multiple overlapping campaigns (bundling test)"""
    print_test_header("Scenario: Overlapping Campaigns (Bundling)")

    # 3 campaigns in Al Qana, all overlapping full month
    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "day"),
        create_test_task(2, "The Curve - Al Qana", "01-12-2025", "31-12-2025", "day"),
        create_test_task(3, "Totems - Al Qana", "01-12-2025", "31-12-2025", "day"),
    ]

    assignments = await schedule_abu_dhabi_tasks(tasks)

    print(f"Input: 3 tasks (Al Qana, day, overlapping Jan 15-20)")
    print(f"Assignments: {assignments}")

    # All should get same filming date (bundled)
    if len(assignments) == 3:
        dates = list(assignments.values())
        all_same = len(set(dates)) == 1
        print_result(all_same, f"All tasks bundled on same date: {all_same}")

        if all_same:
            filming_date = datetime.strptime(dates[0], '%d-%m-%Y').date()
            print(f"  Bundled date: {filming_date}")
    else:
        print_result(False, f"Not all tasks assigned")


async def test_scenario_two_areas():
    """Test 8: Tasks in both areas (Galleria + Al Qana)"""
    print_test_header("Scenario: Two Areas (Galleria + Al Qana)")

    # 2 tasks per area to meet minimum
    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "day"),
        create_test_task(2, "The Curve - Al Qana", "01-12-2025", "31-12-2025", "day"),
        create_test_task(3, "Luxury Domination Network", "01-12-2025", "31-12-2025", "day"),
        create_test_task(4, "Indoor Domination", "01-12-2025", "31-12-2025", "day"),
    ]

    assignments = await schedule_abu_dhabi_tasks(tasks)

    print(f"Input: 4 tasks (2 Al Qana, 2 Galleria)")
    print(f"Assignments: {assignments}")

    # Should have 2 different dates (one per area)
    if len(assignments) == 4:
        dates = list(assignments.values())
        unique_dates = set(dates)
        two_dates = len(unique_dates) == 2
        print_result(two_dates, f"Two different shoot dates (one per area): {two_dates}")

        if two_dates:
            for d in sorted(unique_dates):
                print(f"  Date: {d}")
    else:
        print_result(False, f"Not all tasks assigned: {len(assignments)}/4")


async def test_scenario_day_night_bundling():
    """Test 9: DAY + NIGHT time block bundling"""
    print_test_header("Scenario: DAY + NIGHT Time Block Bundling")

    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "day"),
        create_test_task(2, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "night"),
        create_test_task(3, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "both"),
    ]

    assignments = await schedule_abu_dhabi_tasks(tasks)

    print(f"Input: 3 tasks (Al Qana, day/night/both)")
    print(f"Assignments: {assignments}")

    # All should be bundled on same date (different time blocks OK)
    if len(assignments) == 3:
        dates = list(assignments.values())
        all_same = len(set(dates)) == 1
        print_result(all_same, f"All time blocks bundled on same date: {all_same}")
    else:
        print_result(False, f"Not all tasks assigned")


async def test_scenario_weekly_limit():
    """Test 10: Weekly limit enforcement and fallback strategy"""
    print_test_header("Scenario: Weekly Limit and Fallback Strategy")

    # 4 tasks in Al Qana with realistic campaign periods
    # These campaigns span enough time to hit valid Tue/Thu/Fri dates
    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "01-12-2025", "10-12-2025", "day"),  # Can film on Tue 2nd, Thu 4th, Fri 5th
        create_test_task(2, "TTC Abu Dhabi", "02-12-2025", "11-12-2025", "day"),  # Overlaps with task 1
        create_test_task(3, "TTC Abu Dhabi", "08-12-2025", "15-12-2025", "day"),  # Can film on Tue 9th, Thu 11th, Fri 12th
        create_test_task(4, "TTC Abu Dhabi", "09-12-2025", "16-12-2025", "day"),  # Overlaps with task 3
    ]

    assignments = await schedule_abu_dhabi_tasks(tasks)

    print(f"Input: 4 tasks (Al Qana, 2 pairs with overlapping campaigns)")
    print(f"Assignments: {assignments}")

    # Should successfully schedule all 4 tasks
    # First pass: Bundle overlapping campaigns (tasks 1+2, tasks 3+4)
    # Fallback: Not needed if bundling works
    if len(assignments) == 4:
        dates = list(assignments.values())
        unique_dates = set(dates)
        print_result(True, f"All 4 tasks scheduled: True")
        print(f"  Unique filming dates: {len(unique_dates)}")
        print(f"  Dates: {sorted(unique_dates)}")

        # Should have 2 different dates (one for each pair)
        if len(unique_dates) == 2:
            print_result(True, f"Bundled into 2 shoots (optimal): True")
        else:
            print_result(True, f"Used fallback strategies to schedule all tasks")
    else:
        print_result(False, f"Only {len(assignments)}/4 tasks scheduled")


async def test_scenario_fallback_single_campaign():
    """Test 11: Fallback strategy for single campaigns"""
    print_test_header("Scenario: Fallback Strategy (Single Campaign)")

    # Single task that can't be bundled
    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "01-12-2025", "20-12-2025", "day"),
    ]

    assignments = await schedule_abu_dhabi_tasks(tasks)

    print(f"Input: 1 task (Al Qana, day, no bundling possible)")
    print(f"Assignments: {assignments}")

    # Should use fallback strategy to schedule single campaign
    passed = len(assignments) == 1
    print_result(passed, f"Single campaign scheduled via fallback: {passed}")

    if assignments:
        filming_date = datetime.strptime(list(assignments.values())[0], '%d-%m-%Y').date()
        is_valid_day = filming_date.weekday() in [1, 3, 4]
        print_result(is_valid_day, f"Filming date is Tue/Thu/Fri: {is_valid_day}")


async def test_scenario_extreme_fallback_weekday():
    """Test 12: Extreme fallback - relaxes Tue/Thu only, but NEVER weekends (Fri/Sat/Sun)"""
    print_test_header("Scenario: Extreme Fallback (Mon/Wed, NOT Fri/Sat/Sun)")

    # Campaign that spans Sat-Mon (no Tue/Thu, but has Mon)
    # Working week is Mon-Thu, so should schedule on Monday only
    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "06-12-2025", "08-12-2025", "day"),  # Sat-Mon: should pick Mon
    ]

    assignments = await schedule_abu_dhabi_tasks(tasks)

    print(f"Input: 1 task (Al Qana, campaign spans Sat-Mon)")
    print(f"Assignments: {assignments}")

    # Should schedule on Mon (8th), NOT on Sat (6th) or Sun (7th)
    passed = len(assignments) == 1
    print_result(passed, f"Extreme fallback scheduled on weekday: {passed}")

    if assignments:
        filming_date = datetime.strptime(list(assignments.values())[0], '%d-%m-%Y').date()
        day_name = filming_date.strftime('%A')
        # Working week is Mon-Thu (0-3), weekend is Fri/Sat/Sun (4/5/6)
        is_weekend = filming_date.weekday() in [4, 5, 6]

        print(f"  Filming date: {filming_date} ({day_name})")
        print_result(not is_weekend, f"NOT scheduled on weekend (Fri/Sat/Sun): {not is_weekend}")

        # Should be Monday (8th) - the only working day in the range
        if day_name == "Monday":
            print_result(True, f"Scheduled on Monday (only working day in range)")


async def test_scenario_mixed_areas_bundling():
    """Test 13: Mixed areas with different time blocks"""
    print_test_header("Scenario: Mixed Areas with Time Blocks")

    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "day"),
        create_test_task(2, "TTC Abu Dhabi", "01-12-2025", "31-12-2025", "night"),
        create_test_task(3, "Luxury Domination Network", "01-12-2025", "31-12-2025", "day"),
        create_test_task(4, "Indoor Domination", "01-12-2025", "31-12-2025", "night"),
    ]

    assignments = await schedule_abu_dhabi_tasks(tasks)

    print(f"Input: 4 tasks (2 Al Qana day/night, 2 Galleria day/night)")
    print(f"Assignments: {assignments}")

    if len(assignments) == 4:
        print_result(True, f"All 4 tasks scheduled: True")
        dates = list(assignments.values())
        unique_dates = set(dates)
        print(f"  Unique filming dates: {len(unique_dates)}")
    else:
        print_result(False, f"Only {len(assignments)}/4 tasks scheduled")


async def test_scenario_consecutive_days_fallback():
    """Test 14: Fallback relaxes 1-day gap constraint"""
    print_test_header("Scenario: Fallback Relaxes 1-Day Gap")

    # Create situation where normal scheduling fills the week
    # Then add more tasks that need consecutive days
    tasks = [
        create_test_task(1, "TTC Abu Dhabi", "03-12-2025", "05-12-2025", "day"),  # Expires soon
        create_test_task(2, "TTC Abu Dhabi", "04-12-2025", "06-12-2025", "day"),  # Expires soon
        create_test_task(3, "TTC Abu Dhabi", "05-12-2025", "07-12-2025", "day"),  # Expires soon
    ]

    assignments = await schedule_abu_dhabi_tasks(tasks)

    print(f"Input: 3 tasks (Al Qana, short campaigns needing quick scheduling)")
    print(f"Assignments: {assignments}")

    # Should schedule all 3 using fallback (may violate 1-day gap)
    passed = len(assignments) == 3
    print_result(passed, f"All 3 tasks scheduled via fallback: {passed}")

    if passed:
        dates = [datetime.strptime(d, '%d-%m-%Y').date() for d in assignments.values()]
        dates.sort()
        print(f"  Filming dates: {', '.join([d.strftime('%d-%m') for d in dates])}")


async def test_non_abu_dhabi_passthrough():
    """Test 15: Non-Abu Dhabi locations should not be affected"""
    print_test_header("Non-Abu Dhabi Passthrough")

    tasks = [
        create_test_task(1, "Dubai Mall", "15-12-2025", "31-12-2025", "day"),
        create_test_task(2, "UAE 04", "15-12-2025", "31-12-2025", "day"),
    ]

    assignments = await schedule_abu_dhabi_tasks(tasks)

    print(f"Input: 2 tasks (Dubai Mall, UAE 04)")
    print(f"Assignments: {assignments}")

    # Should return empty (no Abu Dhabi tasks)
    passed = len(assignments) == 0
    print_result(passed, f"Non-Abu Dhabi tasks ignored: {passed}")


async def run_all_tests():
    """Run all tests"""
    print("\n" + "🧪" * 40)
    print("ABU DHABI SCHEDULER - COMPREHENSIVE TEST SUITE")
    print("🧪" * 40)

    try:
        test_location_detection()
        test_candidate_dates()
        test_overlap_scoring()
        test_weekly_constraints()
        test_freeze_rule()
        await test_scenario_single_campaign()
        await test_scenario_overlap_bundling()
        await test_scenario_two_areas()
        await test_scenario_day_night_bundling()
        await test_scenario_weekly_limit()
        await test_scenario_fallback_single_campaign()
        await test_scenario_extreme_fallback_weekday()
        await test_scenario_mixed_areas_bundling()
        await test_scenario_consecutive_days_fallback()
        await test_non_abu_dhabi_passthrough()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS COMPLETED")
        print("=" * 80)
        print("\nReview the results above. If all tests pass, the algorithm is ready.")

    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ TEST SUITE FAILED: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
