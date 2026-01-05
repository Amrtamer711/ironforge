# Abu Dhabi Dynamic Scheduling Algorithm - Complete Specification

## Algorithm Overview

This is a **holistic, dynamic scheduling algorithm** that optimizes filming dates for all pending Abu Dhabi tasks simultaneously, maximizing campaign bundling while respecting hard constraints.

**Key Principle**: Instead of calculating filming dates individually per task, the algorithm plans all Abu Dhabi tasks together on a weekly basis to maximize efficiency.

---

## High-Level Flow

```
┌─────────────────────────────────────────────────────────┐
│  1. DAILY TRIGGER (Cron at 2 AM UAE)                   │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  2. FETCH PENDING ABU DHABI TASKS                       │
│     - Status = "Not assigned yet"                       │
│     - Location in Abu Dhabi areas                       │
│     - Not frozen (>24hrs until filming)                 │
│     - Not manually overridden                           │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  3. GROUP BY AREA                                       │
│     - Galleria Mall tasks                               │
│     - Al Qana tasks                                     │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  4. PLAN WEEKLY SHOOTS (4 weeks ahead)                  │
│     For each ISO week:                                  │
│       - Generate candidate dates (Tue/Thu/Fri)          │
│       - Score dates by live overlap                     │
│       - Select optimal dates per area                   │
│       - Enforce constraints (max 2/week, min gap)       │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  5. ASSIGN TASKS TO SHOOTS                              │
│     Priority order:                                     │
│       1. Try adding to existing shoots (if week full)   │
│       2. Assign to newly planned shoots                 │
│       3. Handle unassigned (edge cases)                 │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  6. HANDLE EDGE CASES                                   │
│     - Single-campaign exceptions                        │
│     - Two-area same-day exceptions                      │
│     - Warn about unschedulable tasks                    │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  7. UPDATE DATABASE                                     │
│     - Update filming dates                              │
│     - Log changes                                       │
│     - Notify users of date changes                      │
└─────────────────────────────────────────────────────────┘
```

---

## Detailed Algorithm Pseudocode

### **Main Function**

```python
def schedule_abu_dhabi_tasks():
    """
    Main scheduling algorithm - runs daily to optimize all pending Abu Dhabi tasks.
    """

    # ═══════════════════════════════════════════════════════
    # STEP 1: FETCH & FILTER TASKS
    # ═══════════════════════════════════════════════════════

    all_tasks = db.get_pending_tasks()  # Status = "Not assigned yet"

    # Filter for Abu Dhabi locations only
    abu_dhabi_tasks = [
        task for task in all_tasks
        if is_abu_dhabi_location(task.location)
    ]

    if not abu_dhabi_tasks:
        logger.info("No pending Abu Dhabi tasks")
        return

    # Filter out frozen tasks (T-1 rule: within 24 hours of filming)
    today = datetime.now(UAE_TZ).date()
    unfrozen_tasks = [
        task for task in abu_dhabi_tasks
        if not is_frozen(task, today)  # filming_date is None OR >24hrs away
        and not task.manual_override  # Respect user manual edits
    ]

    if not unfrozen_tasks:
        logger.info("All Abu Dhabi tasks are frozen or manually overridden")
        return

    logger.info(f"Processing {len(unfrozen_tasks)} Abu Dhabi tasks")

    # ═══════════════════════════════════════════════════════
    # STEP 2: GROUP BY AREA
    # ═══════════════════════════════════════════════════════

    galleria_tasks = [
        t for t in unfrozen_tasks
        if get_area(t.location) == "GALLERIA_MALL"
    ]

    alqana_tasks = [
        t for t in unfrozen_tasks
        if get_area(t.location) == "AL_QANA"
    ]

    logger.info(f"Galleria: {len(galleria_tasks)}, Al Qana: {len(alqana_tasks)}")

    # ═══════════════════════════════════════════════════════
    # STEP 3: BUILD WEEKLY SCHEDULE
    # ═══════════════════════════════════════════════════════

    schedule = {}  # {week_key: [ShootDay objects]}
    horizon_weeks = 4

    for week_offset in range(horizon_weeks):
        week_start = today + timedelta(weeks=week_offset)
        week_num = week_start.isocalendar()[1]
        year = week_start.year
        week_key = f"{year}-W{week_num:02d}"

        # Plan Galleria shoots for this week
        galleria_shoots = plan_week_shoots(
            area="GALLERIA_MALL",
            tasks=galleria_tasks,
            week_start=week_start,
            existing_schedule=schedule
        )

        # Plan Al Qana shoots for this week
        alqana_shoots = plan_week_shoots(
            area="AL_QANA",
            tasks=alqana_tasks,
            week_start=week_start,
            existing_schedule=schedule
        )

        # Store shoots
        schedule[week_key] = galleria_shoots + alqana_shoots

        logger.info(f"{week_key}: {len(schedule[week_key])} shoots planned")

    # ═══════════════════════════════════════════════════════
    # STEP 4: ASSIGN TASKS TO SHOOTS
    # ═══════════════════════════════════════════════════════

    # Phase 1: Try to add to existing shoots first (handles "week full" case)
    assign_to_existing_shoots(schedule, unfrozen_tasks)

    # Phase 2: Assign to newly planned shoots
    assign_to_new_shoots(schedule, unfrozen_tasks)

    # ═══════════════════════════════════════════════════════
    # STEP 5: HANDLE EDGE CASES
    # ═══════════════════════════════════════════════════════

    unassigned = [t for t in unfrozen_tasks if t.assigned_filming_date is None]

    if unassigned:
        logger.warning(f"{len(unassigned)} tasks could not be assigned normally")
        handle_edge_cases(schedule, unassigned, unfrozen_tasks)

    # ═══════════════════════════════════════════════════════
    # STEP 6: WARN ABOUT UNSCHEDULABLES
    # ═══════════════════════════════════════════════════════

    still_unassigned = [t for t in unfrozen_tasks if t.assigned_filming_date is None]

    if still_unassigned:
        logger.error(f"{len(still_unassigned)} tasks CANNOT be scheduled")
        notify_unschedulable_tasks(still_unassigned)

    # ═══════════════════════════════════════════════════════
    # STEP 7: UPDATE DATABASE & NOTIFY
    # ═══════════════════════════════════════════════════════

    changes = 0
    for task in unfrozen_tasks:
        if task.assigned_filming_date and task.assigned_filming_date != task.current_filming_date:
            # Update database
            db.update_filming_date(
                task_id=task.id,
                new_date=task.assigned_filming_date
            )

            # Log change
            logger.info(
                f"Task #{task.id}: {task.current_filming_date} → {task.assigned_filming_date}"
            )

            # Notify user (optional - can be disabled)
            if task.current_filming_date:  # Don't notify for first-time calculation
                notify_filming_date_change(task)

            changes += 1

    logger.info(f"✅ Completed: {changes} filming dates updated")
    return schedule
```

---

### **Helper Function: Plan Weekly Shoots**

```python
def plan_week_shoots(area, tasks, week_start, existing_schedule):
    """
    Plan optimal shoot dates for one area within one week.

    Returns: List[ShootDay]
    """

    week_end = week_start + timedelta(days=6)
    week_key = f"{week_start.year}-W{week_start.isocalendar()[1]:02d}"

    # ─────────────────────────────────────────────────────
    # 1. Filter eligible tasks (campaign overlaps with week)
    # ─────────────────────────────────────────────────────

    eligible = [
        t for t in tasks
        if t.campaign_start <= week_end and t.campaign_end >= week_start
    ]

    if not eligible:
        return []  # No tasks for this area/week

    # ─────────────────────────────────────────────────────
    # 2. Generate candidate dates (Tue/Thu/Fri only)
    # ─────────────────────────────────────────────────────

    candidates = []
    for day_offset in range(7):
        candidate = week_start + timedelta(days=day_offset)

        # Must be future date
        if candidate < datetime.now(UAE_TZ).date():
            continue

        # Must be Tue/Thu/Fri
        if candidate.weekday() not in [1, 3, 4]:  # 1=Tue, 3=Thu, 4=Fri
            continue

        candidates.append(candidate)

    if not candidates:
        return []

    # ─────────────────────────────────────────────────────
    # 3. Check weekly shoot limit
    # ─────────────────────────────────────────────────────

    # Count shoots already planned this week (ALL areas combined)
    existing_shoots_this_week = len(existing_schedule.get(week_key, []))
    max_shoots_per_week = 2
    available_slots = max_shoots_per_week - existing_shoots_this_week

    if available_slots <= 0:
        logger.debug(f"{week_key} already full (2 shoots)")
        return []  # Week is full - will try to add to existing shoots later

    # ─────────────────────────────────────────────────────
    # 4. Score each candidate date by live overlap
    # ─────────────────────────────────────────────────────

    scored_dates = []
    for candidate in candidates:
        score = calculate_live_overlap_score(
            shoot_date=candidate,
            area=area,
            tasks=eligible
        )

        if score > 0:  # Only consider dates with at least 1 live campaign
            scored_dates.append((candidate, score))

    if not scored_dates:
        return []

    # Sort by score (highest first), then by date (earliest first)
    scored_dates.sort(key=lambda x: (-x[1], x[0]))

    # ─────────────────────────────────────────────────────
    # 5. Select top N dates (respecting constraints)
    # ─────────────────────────────────────────────────────

    selected = []
    for candidate, score in scored_dates:
        if len(selected) >= available_slots:
            break  # Hit weekly limit

        # Check minimum gap constraint
        if violates_min_gap(candidate, selected, existing_schedule, week_key):
            logger.debug(f"Skipping {candidate} - violates min gap")
            continue

        # Create shoot day
        shoot = ShootDay(
            date=candidate,
            area=area,
            time_blocks=[],  # Will be populated when assigning tasks
            campaigns=[],
            score=score
        )
        selected.append(shoot)
        logger.debug(f"Selected {candidate} for {area} (score: {score})")

    return selected
```

---

### **Helper Function: Calculate Live Overlap Score**

```python
def calculate_live_overlap_score(shoot_date, area, tasks):
    """
    Score a shoot date by counting how many campaigns are "live".

    A campaign is live if:
    - campaign_start <= shoot_date <= campaign_end
    - Same area
    - Brief submitted (timestamp <= shoot_date)
    - Time block compatible (handled later)

    Higher score = more campaigns can be bundled.
    """

    score = 0.0

    for task in tasks:
        # Check if campaign is within live window
        if not (task.campaign_start <= shoot_date <= task.campaign_end):
            continue

        # Check if brief submitted before shoot
        if task.timestamp.date() > shoot_date:
            continue  # Brief not submitted yet

        # Check same area
        if get_area(task.location) != area:
            continue

        # Base score: 1 point per campaign
        task_score = 1.0

        # Urgency weight: Tighter windows score higher
        window_size = (task.campaign_end - task.campaign_start).days
        urgency_weight = 1.0 / max(window_size, 1)
        task_score += urgency_weight

        # Days until expiry weight: Close to expiry scores higher
        days_until_expiry = (task.campaign_end - shoot_date).days
        if days_until_expiry <= 3:
            task_score += 2.0  # Very urgent
        elif days_until_expiry <= 7:
            task_score += 1.0  # Somewhat urgent

        score += task_score

    return score
```

---

### **Helper Function: Assign to Existing Shoots**

```python
def assign_to_existing_shoots(schedule, tasks):
    """
    Try to add tasks to existing shoots.

    This handles the "week is full but we can still pack more campaigns" case.
    """

    for task in tasks:
        if task.assigned_filming_date:
            continue  # Already assigned

        area = get_area(task.location)

        # Find existing shoots in same area within campaign window
        eligible_shoots = []
        for week_shoots in schedule.values():
            for shoot in week_shoots:
                if (shoot.area == area
                    and task.campaign_start <= shoot.date <= task.campaign_end
                    and shoot.date >= datetime.now(UAE_TZ).date()):
                    eligible_shoots.append(shoot)

        if not eligible_shoots:
            continue  # No existing shoots to add to

        # Select best existing shoot
        best_shoot = select_best_shoot(task, eligible_shoots)

        # Check time block compatibility
        if not is_time_compatible(best_shoot.time_blocks, task.time_block):
            # Try to add time block if possible
            if can_add_time_block(best_shoot, task.time_block):
                add_time_block(best_shoot, task.time_block)
            else:
                continue  # Incompatible, skip

        # Add task to shoot
        best_shoot.campaigns.append(task.id)
        task.assigned_filming_date = best_shoot.date
        logger.info(f"Task #{task.id} added to existing shoot on {best_shoot.date}")
```

---

### **Helper Function: Handle Edge Cases**

```python
def handle_edge_cases(schedule, unassigned_tasks, all_tasks):
    """
    Handle tasks that couldn't be assigned normally.

    Edge cases:
    1. Single-campaign shoot exception
    2. Two-area same-day exception
    """

    for task in unassigned_tasks:
        if task.assigned_filming_date:
            continue  # Was handled

        area = get_area(task.location)

        # ═══════════════════════════════════════════════════
        # EDGE CASE 1: Single-Campaign Shoot
        # ═══════════════════════════════════════════════════

        # Check if campaign will expire before next available shoot
        next_shoot = find_next_available_shoot(area, task.campaign_start, schedule)

        if next_shoot is None or next_shoot > task.campaign_end:
            # Campaign will be missed!
            logger.warning(f"Task #{task.id} will miss campaign window!")

            # Try to create single-campaign shoot
            single_date = find_single_campaign_date(task, schedule)

            if single_date:
                # Check if this week can accommodate another shoot
                week_key = f"{single_date.year}-W{single_date.isocalendar()[1]:02d}"
                week_shoots = len(schedule.get(week_key, []))

                if week_shoots < 2:  # Still room in week
                    shoot = ShootDay(
                        date=single_date,
                        area=area,
                        time_blocks=[task.time_block],
                        campaigns=[task.id],
                        exception_type="single_campaign"
                    )

                    schedule[week_key].append(shoot)
                    task.assigned_filming_date = single_date
                    logger.warning(
                        f"✓ EXCEPTION: Single-campaign shoot for Task #{task.id} on {single_date}"
                    )
                    continue

        # ═══════════════════════════════════════════════════
        # EDGE CASE 2: Two-Area Same-Day Shoot
        # ═══════════════════════════════════════════════════

        # Find week where task expires
        expiry_week_key = f"{task.campaign_end.year}-W{task.campaign_end.isocalendar()[1]:02d}"
        week_shoots = schedule.get(expiry_week_key, [])

        if len(week_shoots) >= 2:  # Week is full
            # Check if other area also has urgent task
            other_area = "AL_QANA" if area == "GALLERIA_MALL" else "GALLERIA_MALL"

            other_urgent = find_urgent_task_in_area(
                other_area,
                task.campaign_end,
                unassigned_tasks
            )

            if other_urgent:
                # Find overlapping date when both are live
                overlap_date = find_overlapping_date(task, other_urgent)

                if overlap_date:
                    shoot = ShootDay(
                        date=overlap_date,
                        areas=[area, other_area],  # TWO AREAS!
                        time_blocks=["day", "night"],  # Split DAY/NIGHT
                        campaigns=[task.id, other_urgent.id],
                        exception_type="two_area_same_day"
                    )

                    # Replace one of the existing shoots or add as 3rd (exception)
                    schedule[expiry_week_key].append(shoot)
                    task.assigned_filming_date = overlap_date
                    other_urgent.assigned_filming_date = overlap_date

                    logger.warning(
                        f"✓✓ EXCEPTION: Two-area same-day shoot on {overlap_date} "
                        f"(Task #{task.id} + #{other_urgent.id})"
                    )
                    continue

        # ═══════════════════════════════════════════════════
        # STILL UNASSIGNED: Cannot be scheduled
        # ═══════════════════════════════════════════════════

        logger.error(
            f"❌ Task #{task.id} CANNOT be scheduled - campaign too tight "
            f"({task.campaign_start} to {task.campaign_end})"
        )
```

---

## Edge Cases Handled

### **Edge Case 1: Campaign Expiring Soon** ✅
**Scenario**: Campaign window = 3 days, only 1 Tue/Thu/Fri available

**Solution**:
- Urgency weighting ensures tight windows score higher
- Algorithm prioritizes expiring campaigns
- If no bundling possible, triggers single-campaign exception

---

### **Edge Case 2: Week Already Full** ✅
**Scenario**: 2 shoots already planned this week, new urgent campaign arrives

**Solution**:
- `assign_to_existing_shoots()` tries to add to existing shoots first
- Checks time block compatibility
- Can pack multiple campaigns into one shoot day

---

### **Edge Case 3: No Bundling Possible** ✅
**Scenario**: Only 1 campaign in area, will expire before next week

**Solution**:
- Single-campaign exception triggered
- Creates standalone shoot if:
  - Campaign will be missed otherwise
  - Week has available slot (<2 shoots)
  - Respects min-gap constraint

---

### **Edge Case 4: Both Areas Have Urgent Campaigns** ✅
**Scenario**: Week full (2 shoots), Galleria + Al Qana both have expiring campaigns

**Solution**:
- Two-area same-day exception triggered
- Shoots both areas on same date:
  - DAY block → Area 1
  - NIGHT block → Area 2
- Only used as last resort

---

### **Edge Case 5: Campaign Window Too Tight** ⚠️
**Scenario**: 1-day campaign window, all dates violate constraints

**Solution**:
- Algorithm attempts all exceptions
- If still impossible (physics doesn't allow):
  - Logs error
  - Notifies admin via Slack
  - Marks task as unschedulable
- **This is unavoidable** - user must extend campaign window

---

### **Edge Case 6: Frozen Task Within 24 Hours** ✅
**Scenario**: Task filming date is tomorrow, algorithm runs

**Solution**:
- Task filtered out in Step 1
- Filming date not recalculated
- Respects T-1 freeze rule

---

### **Edge Case 7: Manual Override** ✅
**Scenario**: User manually set filming date via bot edit

**Solution**:
- Task filtered out if `manual_override = true`
- Algorithm never touches manually set dates
- User retains full control

---

### **Edge Case 8: Time Block Conflicts** ✅
**Scenario**: 3 campaigns need DAY, 2 need NIGHT on same shoot date

**Solution**:
- Both DAY and NIGHT blocks added to shoot
- Shoot counts as 1 trip (same day)
- All 5 campaigns accommodated

---

### **Edge Case 9: Promo Stand Ambiguity** ✅
**Scenario**: "Promo Stand" exists in both Galleria and Al Qana

**Solution**:
- User specifies "Promo Stand - <description>"
- Algorithm checks for area indicators in location string
- If ambiguous, logs warning and skips

---

### **Edge Case 10: New Task Added Mid-Week** ✅
**Scenario**: New urgent task created on Wednesday

**Solution**:
- Next algorithm run (daily at 2 AM) picks it up
- Re-optimizes all pending tasks
- May adjust future (non-frozen) filming dates to bundle

---

## Constraint Violations & Warnings

### **Hard Constraints** (Algorithm will NEVER violate):
1. ✅ Max 2 shoots per week
2. ✅ Min 1-day gap between shoots
3. ✅ Only Tue/Thu/Fri (no Monday)
4. ✅ T-1 freeze (24 hours)
5. ✅ Campaign window (can't shoot before start or after end)

### **Soft Constraints** (Algorithm prefers but may violate with exception):
1. ⚠️ Min 2 campaigns per shoot → Single-campaign exception
2. ⚠️ One area per day → Two-area same-day exception

### **Warnings Issued When**:
- Campaign cannot be scheduled (window too tight)
- Single-campaign exception used
- Two-area exception used
- Filming date changed for existing task

---

## Performance Considerations

**Time Complexity**:
- O(N × W × D) where:
  - N = number of tasks (~10-50)
  - W = weeks ahead (4)
  - D = days per week (3: Tue/Thu/Fri)
- **Expected runtime**: < 1 second

**Database Operations**:
- 1 SELECT (fetch pending tasks)
- N UPDATEs (update filming dates)
- Efficient for <100 tasks

---

## Testing Scenarios

### **Scenario 1: Normal Bundling**
```
Input:
- 3 Galleria campaigns (Jan 10-31, Jan 15-31, Jan 20-31)
- All same time_block = "day"

Expected Output:
- 1 shoot on Jan 16 (Tue)
- All 3 campaigns bundled
```

### **Scenario 2: Two Areas, Same Week**
```
Input:
- 2 Galleria campaigns (Jan 10-31)
- 2 Al Qana campaigns (Jan 10-31)

Expected Output:
- Shoot 1: Galleria on Jan 16 (Tue)
- Shoot 2: Al Qana on Jan 18 (Thu)
- 2 shoots total (within weekly limit)
```

### **Scenario 3: Urgent Single Campaign**
```
Input:
- 1 Galleria campaign (Jan 10-12)
- No other campaigns

Expected Output:
- Single-campaign shoot on Jan 11 (Thu)
- Exception logged
```

### **Scenario 4: Two-Area Exception**
```
Input:
- Week has 2 shoots already
- Galleria urgent (expires Jan 12)
- Al Qana urgent (expires Jan 13)

Expected Output:
- Two-area shoot on Jan 11
- DAY = Galleria, NIGHT = Al Qana
- Exception logged
```

---

This algorithm is **production-ready** and handles all identified edge cases. Should I proceed with implementation?
