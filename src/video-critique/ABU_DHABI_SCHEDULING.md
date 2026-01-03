# Abu Dhabi Photographer Scheduling Implementation Plan

## Overview
This document outlines the implementation of a specialized scheduling algorithm for Abu Dhabi locations. This algorithm applies ONLY to Abu Dhabi-based campaigns and has NO effect on existing Dubai/other location scheduling logic.

---

## Current State Analysis

### Existing System
- **Filming Date Logic**: Uses 2nd/17th of month rule (see `utils.py:calculate_filming_date()`)
- **Assignment Logic**: Assigns videographer based on location mapping (see `assignment.py`)
- **Task Types**: videography, photography, both
- **Database Schema**:
  - `Filming Date` (TEXT) - calculated automatically
  - `Location` (TEXT) - free text field
  - `Task Type` (TEXT) - videography/photography/both
  - `Videographer` (TEXT) - assigned person

### What We Know

#### 1. Roles & Responsibilities
- **Videographers ARE photographers** - same people do both types of tasks
- Task type (videography/photography/both) is for:
  - Trello card descriptions
  - Workflow differentiation
- Uploads are ZIP files, so content type doesn't affect file handling

#### 2. Abu Dhabi Locations

**Area 1: Galleria Mall**
- Luxury Domination Network (Extension Outdoor + Luxury Indoor + Luxury Outdoor)
- Indoor Domination (Extension Indoor + Luxury Indoor)
- Outdoor Domination (Extension Outdoor + Luxury Outdoor)
- Full Domination (all 4 screen types)
- 7 Outdoor Screens (special package)

**Area 2: Al Qana**
- TTC Abu Dhabi (Triple Crown)
- The Curve - Al Qana
- Totems - Al Qana
- Promo Stand

**Question**: Do the detailed screen types (Luxury Indoor, Extension Outdoor, etc.) matter for scheduling, or just the area (Galleria vs Al Qana)?
- **Current assumption**: Only area matters for bundling. Screen type doesn't affect shoot scheduling.

#### 3. Time Blocks (NEW)
- Need to add: DAY, NIGHT, DAY_AND_NIGHT classification
- This is a NEW field not in current schema
- **Affects**: Trello card descriptions, shoot scheduling

#### 4. Abu Dhabi Videographer
- Based in Dubai
- Travels to Abu Dhabi ad-hoc
- Follows special scheduling rules (2 shoots/week, Tue/Thu/Fri preferred)

#### 5. Scope
- **ONLY Abu Dhabi locations** use new algorithm
- **All other locations** continue using 2nd/17th logic
- No impact on existing workflows

---

## Outstanding Questions (MUST ANSWER BEFORE IMPLEMENTATION)

### Critical Questions

#### Q1: Brief Submission Date Tracking ✅ DEFERRED
**Question**: Do we need to track when the brief was submitted separately from task creation?
- **Decision**: Leave for now - will revisit if needed
- **Implementation**: Use `Timestamp` field as proxy for brief submission date

#### Q2: Photo Editing Capacity ✅ ANSWERED
**Question**: How many photo edits can be completed per day?
- **Decision**: REMOVED - No editing capacity limits enforced
- **Implementation**: Algorithm will not limit based on editing capacity, only on shoot scheduling rules

#### Q3: Location Name Mapping Precision ⏳ AWAITING INPUT
**Question**: How are Abu Dhabi locations named in the system?
- **Status**: User will provide exact location name strings next
- **Need**: Exact string values as they appear in database

#### Q4: Manual Filming Date Override ✅ ANSWERED
**Question**: Should users be able to manually set filming dates that override the algorithm?
- **Decision**: Use existing edit flow - users can change filming date through bot chat (already implemented)
- **Implementation**: No new override mechanism needed - existing task editing handles this

#### Q5: Day/Night Time Block - Required or Optional? ✅ ANSWERED
**Question**: Is specifying DAY/NIGHT mandatory for every request?
- **Decision**: REQUIRED - user must specify DAY, NIGHT, or BOTH when creating Abu Dhabi tasks
- **Implementation**:
  - Add `time_block` to task creation form
  - LLM must ask user if not provided
  - Enum: ["day", "night", "both"]

#### Q6: Single-Campaign Shoot Exceptions ✅ ANSWERED
**Question**: Algorithm prefers 2+ campaigns per shoot. When exactly should we allow single-campaign shoots?
- **Decision**: Only in worst-case scenario where campaign will be missed
- **Logic**: Allow single-campaign shoot ONLY when:
  1. No other campaigns exist in same area for bundling within the week, AND
  2. Campaign will expire before next available shoot opportunity (next Tue/Thu/Fri)
- **Implementation**: Check if campaign.end_date < next_available_shoot_date

#### Q7: Two-Area Same-Day Criteria ✅ ANSWERED
**Question**: When exactly should we use the "two areas same day" exception?
- **Decision**: Same as Q6 - only in worst-case scenario where campaign will be missed
- **Logic**: Shoot both areas same day (DAY + NIGHT blocks) ONLY when:
  1. Week already has 2 shoots scheduled (max limit reached), AND
  2. Both Galleria AND Al Qana have campaigns that will expire before next week, AND
  3. No other scheduling option exists without missing campaigns
- **Implementation**: Last resort exception - prioritize separate days first

---

## Schema Changes Required

### New Fields to Add

#### 1. Time Block (for Abu Dhabi tasks)
```python
# Add to live_tasks and completed_tasks tables
"Time Block" TEXT DEFAULT NULL  # Values: 'DAY', 'NIGHT', 'DAY_AND_NIGHT', NULL (non-Abu Dhabi)
```

#### 2. Abu Dhabi Area Classification (derived field - no DB change)
```python
# Computed at runtime based on location name
# Maps location -> area ('GALLERIA_MALL', 'AL_QANA', or None)
```

#### 3. Brief Date (optional - see Q1)
```python
# If we track separately from creation timestamp
"Brief Date" TEXT DEFAULT NULL
```

#### 4. Manual Filming Date Override (optional - see Q4)
```python
# Flag to indicate if filming date was manually set
"Filming Date Override" INTEGER DEFAULT 0  # 0 = auto, 1 = manual
```

---

## Algorithm Implementation Plan

### Phase 1: Configuration & Location Mapping

#### 1.1 Define Abu Dhabi Location Mappings
**File**: `config.py` or new `abu_dhabi_config.json`

```python
ABU_DHABI_LOCATIONS = {
    "GALLERIA_MALL": [
        # TO BE FILLED based on Q3 answer
        "Luxury Domination Network",
        "Indoor Domination",
        "Outdoor Domination",
        "Full Domination",
        "7 Outdoor Screens",
        # ... exact names TBD
    ],
    "AL_QANA": [
        "TTC Abu Dhabi",
        "The Curve - Al Qana",
        "Totems - Al Qana",
        "Promo Stand",
        # ... exact names TBD
    ]
}

# Reverse lookup: location_name -> area
def get_abu_dhabi_area(location: str) -> str | None:
    """Returns 'GALLERIA_MALL', 'AL_QANA', or None"""
    for area, locations in ABU_DHABI_LOCATIONS.items():
        if location in locations:
            return area
    return None

def is_abu_dhabi_location(location: str) -> bool:
    """Check if location is in Abu Dhabi"""
    return get_abu_dhabi_area(location) is not None
```

#### 1.2 Add Abu Dhabi Videographer
- Identify who is the Abu Dhabi videographer
- Add to `videographer_config.json`
- Map Abu Dhabi locations to this person

### Phase 2: Time Block Implementation

#### 2.1 Add Time Block to Tools
**File**: `tools.py`

```python
"time_block": {
    "type": "string",
    "description": "Shooting time: 'day', 'night', or 'both' - ask user if not specified for Abu Dhabi locations",
    "enum": ["day", "night", "both"]
}
```

#### 2.2 Add Time Block to LLM Parsing
**File**: `llm_utils.py`

- Update parsing instructions to recognize time keywords
- Add to JSON schema
- Extract from user input

#### 2.3 Update Database Schema
**File**: `db_utils.py`

```sql
ALTER TABLE live_tasks ADD COLUMN "Time Block" TEXT DEFAULT NULL;
ALTER TABLE completed_tasks ADD COLUMN time_block TEXT DEFAULT NULL;
```

#### 2.4 Update Trello Card Descriptions
**File**: `assignment.py`

```python
# Add to card description
if time_block:
    card_description += f"• Time Block: {time_block.title()}\n"
```

### Phase 3: Core Scheduling Algorithm

#### 3.1 Create New Module
**File**: `abu_dhabi_scheduler.py` (NEW FILE)

**Key Functions**:

```python
def calculate_abu_dhabi_filming_date(
    location: str,
    campaign_start_date: str,
    campaign_end_date: str,
    task_type: str,
    time_block: str,
    all_pending_tasks: List[Dict]
) -> str:
    """
    Calculate optimal filming date for Abu Dhabi locations.

    Algorithm:
    1. Verify location is Abu Dhabi
    2. Determine area (GALLERIA_MALL or AL_QANA)
    3. Find all pending tasks in same area
    4. Generate candidate shoot dates (Tue/Thu/Fri only)
    5. Score each date by # of overlapping live campaigns
    6. Select date with max overlap (common live date)
    7. Enforce constraints:
       - Max 2 shoots/week
       - Min 1 day gap between shoots
       - Avoid Mondays
    8. Return optimal date or fallback to 2nd/17th logic
    """
    pass

def get_weekly_shoot_plan(week_start: date) -> List[ShootDate]:
    """Get planned shoot dates for a given week"""
    pass

def can_add_shoot_to_week(proposed_date: date, existing_shoots: List[date]) -> bool:
    """
    Check if adding a shoot violates weekly constraints.
    Returns True if:
    - Week has < 2 shoots
    - Proposed date has >= 1 day gap from existing shoots
    - Proposed date is Tue/Thu/Fri
    """
    pass

def calculate_live_overlap_score(
    shoot_date: date,
    area: str,
    time_block: str,
    pending_tasks: List[Dict]
) -> int:
    """
    Count how many campaigns are live on shoot_date.

    Campaign is "live" if:
    - campaign_start_date <= shoot_date <= campaign_end_date
    - Same area
    - Compatible time_block
    - Brief submitted before shoot_date (check Timestamp)
    """
    pass

def get_candidate_dates(
    campaign_start: date,
    campaign_end: date,
    week_limit: int = 4
) -> List[date]:
    """
    Generate candidate shoot dates within campaign window.

    Rules:
    - Only Tue/Thu/Fri (configurable)
    - Within campaign window
    - Up to week_limit weeks ahead
    - Must be future dates
    """
    pass
```

#### 3.2 Integration Point
**File**: `utils.py` - Modify `calculate_filming_date()`

```python
def calculate_filming_date(
    campaign_start_date_str: str,
    campaign_end_date_str: str = None,
    location: str = None,  # NEW PARAMETER
    task_type: str = None,  # NEW PARAMETER
    time_block: str = None  # NEW PARAMETER
) -> str:
    """Calculate filming date - routes to Abu Dhabi algo if applicable"""

    # NEW: Check if Abu Dhabi location
    if location and is_abu_dhabi_location(location):
        from abu_dhabi_scheduler import calculate_abu_dhabi_filming_date

        # Get all pending tasks for overlap analysis
        from db_utils import select_all_tasks
        pending_tasks = [t for t in select_all_tasks() if t['Status'] == 'Not assigned yet']

        return calculate_abu_dhabi_filming_date(
            location=location,
            campaign_start_date=campaign_start_date_str,
            campaign_end_date=campaign_end_date_str,
            task_type=task_type,
            time_block=time_block,
            all_pending_tasks=pending_tasks
        )

    # EXISTING: Use 2nd/17th logic for non-Abu Dhabi
    # ... existing code unchanged ...
```

### Phase 4: Delivery Planning (Simplified)

**Note**: Full delivery queue tracking is complex. Start with simplified version:

```python
def estimate_delivery_date(
    filming_date: date,
    task_type: str,
    num_campaigns_same_day: int
) -> date:
    """
    Estimate delivery date based on capacity.

    Rules:
    - Footage from shoot day lands next calendar day
    - Video capacity: 3/day
    - Photo capacity: TBD (see Q2)
    - If overloaded, add extra days

    Example:
    - Shoot on Tue
    - 5 videos shot
    - Deliver 3 on Wed, 2 on Thu
    """
    pass
```

**Add to Trello card**: Estimated delivery date

### Phase 5: Freeze Rule (T-1)

**Note**: This is a business process rule, not a system constraint initially.

**Implementation options**:
- A) Document as workflow guideline (no code)
- B) Add warning if user tries to modify next-day shoot
- C) Block edits to next-day shoots (strict)

**Recommendation**: Start with A, add B later if needed.

---

## Edge Cases & Potential Issues

### Edge Case 1: No Overlapping Campaigns
**Scenario**: Only 1 campaign in Abu Dhabi this week
**Algorithm behavior**:
- Cannot bundle with others
- Allow single-campaign exception (see Q6)
- OR defer to next week if window allows

### Edge Case 2: Both Areas Have Urgent Campaigns
**Scenario**: Galleria campaign expires Tue, Al Qana expires Wed
**Algorithm behavior**:
- Check if can fit 2 separate shoots in week (Tue + Thu)
- If not, use "two-area same-day" exception (see Q7)
- Assign: DAY block to one area, NIGHT to other

### Edge Case 3: Week Already Has 2 Shoots
**Scenario**: Algorithm tries to add 3rd shoot to week
**Algorithm behavior**:
- REJECT: Cannot exceed 2 shoots/week
- Push to next week
- If campaign expires, trigger urgent handling (see Q6/Q7)

### Edge Case 4: Minimum Gap Violation
**Scenario**: Shoots on Tue + Wed (only 1 day gap needed, 0 actual)
**Algorithm behavior**:
- REJECT: Must have >= 1 day gap
- Find alternative dates

### Edge Case 5: Campaign Window Too Short
**Scenario**: Campaign runs Mon-Wed only (no Tue/Thu/Fri available)
**Algorithm behavior**:
- Fallback to 2nd/17th logic?
- OR allow Monday exception?
- **Needs decision**

### Edge Case 6: Time Block Conflicts
**Scenario**: 3 campaigns need DAY, 2 need NIGHT on same date
**Algorithm behavior**:
- Can shoot both DAY and NIGHT same date
- Counts as 1 shoot day
- Include all 5 campaigns

### Edge Case 7: Manual Override Conflicts
**Scenario**: User sets manual filming date that violates rules
**Algorithm behavior** (if manual override allowed):
- Allow but warn?
- Block with error message?
- **Needs decision** (see Q4)

---

## Integration Risk Analysis

### Risk 1: Circular Dependencies
**Issue**: `utils.py` calls `db_utils.py` which calls `utils.py`
**Mitigation**:
- Move Abu Dhabi logic to separate module
- Import conditionally or use dependency injection

### Risk 2: Assignment Logic Bypass
**Issue**: `assignment.py` may assign before filming date calculated
**Current flow**:
1. Task created → filming date calculated (`db_utils.py:405`)
2. Later: Task assigned → Trello card created (`assignment.py`)

**Risk**: If filming date changes based on other tasks, assignment may use stale date
**Mitigation**:
- Recalculate filming date during assignment
- OR calculate filming date lazily (only when needed)

### Risk 3: Database Migration
**Issue**: Adding new columns to existing tables
**Mitigation**:
- Add columns with DEFAULT NULL
- Existing tasks unaffected (NULL = non-Abu Dhabi)
- Only new Abu Dhabi tasks populate fields

### Risk 4: Trello API Rate Limits
**Issue**: Querying all pending tasks may increase API calls
**Mitigation**:
- Cache pending tasks list
- Only query once per scheduling run
- No increase in Trello calls (we already query tasks)

### Risk 5: Timezone Issues
**Issue**: Algorithm uses dates, system uses UAE timezone
**Current handling**: System already handles UAE timezone
**Mitigation**: Ensure date comparisons use consistent timezone

### Risk 6: Excel vs Database Sync
**Issue**: System historically used Excel, now uses DB
**Current state**: Fully migrated to DB
**Risk**: None (Excel deprecated)

---

## Testing Strategy

### Unit Tests

```python
# test_abu_dhabi_scheduler.py

def test_location_classification():
    """Test that locations map to correct areas"""
    assert get_abu_dhabi_area("TTC Abu Dhabi") == "AL_QANA"
    assert get_abu_dhabi_area("Luxury Domination Network") == "GALLERIA_MALL"
    assert get_abu_dhabi_area("Dubai Mall") is None

def test_candidate_dates_generation():
    """Test Tue/Thu/Fri filtering"""
    start = date(2025, 1, 1)  # Wednesday
    end = date(2025, 1, 31)
    candidates = get_candidate_dates(start, end)
    # Should only include Tuesdays, Thursdays, Fridays
    for d in candidates:
        assert d.weekday() in [1, 3, 4]  # Tue=1, Thu=3, Fri=4

def test_weekly_constraint_enforcement():
    """Test 2-shoots-per-week limit"""
    week_shoots = [date(2025, 1, 7), date(2025, 1, 9)]  # Tue + Thu
    assert not can_add_shoot_to_week(date(2025, 1, 10), week_shoots)  # 3rd shoot

def test_minimum_gap_enforcement():
    """Test 1-day gap between shoots"""
    existing = [date(2025, 1, 7)]  # Tuesday
    assert not can_add_shoot_to_week(date(2025, 1, 8), existing)  # Wed (0 gap)
    assert can_add_shoot_to_week(date(2025, 1, 9), existing)  # Thu (1 gap)

def test_live_overlap_scoring():
    """Test campaign overlap calculation"""
    shoot_date = date(2025, 1, 15)
    tasks = [
        {"Location": "TTC Abu Dhabi", "Campaign Start Date": "01-01-2025", "Campaign End Date": "31-01-2025"},
        {"Location": "TTC Abu Dhabi", "Campaign Start Date": "20-01-2025", "Campaign End Date": "25-01-2025"},
        {"Location": "Luxury Domination", "Campaign Start Date": "01-01-2025", "Campaign End Date": "31-01-2025"},
    ]
    score = calculate_live_overlap_score(shoot_date, "AL_QANA", "DAY", tasks)
    assert score == 2  # Only first 2 tasks match area
```

### Integration Tests

```python
def test_abu_dhabi_routing():
    """Test that Abu Dhabi locations route to new algorithm"""
    result = calculate_filming_date(
        "15-01-2025", "31-01-2025",
        location="TTC Abu Dhabi",
        task_type="videography",
        time_block="day"
    )
    # Result should be Tue/Thu/Fri, not 2nd/17th
    parsed = datetime.strptime(result, "%d-%m-%Y")
    assert parsed.weekday() in [1, 3, 4]

def test_non_abu_dhabi_unchanged():
    """Test that other locations still use 2nd/17th"""
    result = calculate_filming_date(
        "15-01-2025", "31-01-2025",
        location="Dubai Mall",
        task_type="videography",
        time_block=None
    )
    # Should follow 2nd/17th logic
    parsed = datetime.strptime(result, "%d-%m-%Y")
    assert parsed.day in [2, 17] or parsed <= datetime.strptime("17-01-2025", "%d-%m-%Y").date()
```

### Manual Test Scenarios

#### Scenario 1: Single Abu Dhabi Campaign
1. Create task for "TTC Abu Dhabi"
2. Campaign: 15-Jan to 31-Jan
3. Expected: Filming date = nearest Tue/Thu/Fri after 15-Jan

#### Scenario 2: Multiple Overlapping Campaigns
1. Create 3 tasks for "TTC Abu Dhabi"
   - Campaign A: 10-Jan to 20-Jan
   - Campaign B: 15-Jan to 25-Jan
   - Campaign C: 18-Jan to 30-Jan
2. Expected: Filming date = Tue/Thu/Fri when most are live (around 18-Jan)

#### Scenario 3: Two Areas Same Week
1. Create 1 task for "TTC Abu Dhabi" (Al Qana)
2. Create 1 task for "Luxury Domination" (Galleria)
3. Both campaigns: 15-Jan to 20-Jan
4. Expected: 2 separate shoots on Tue + Thu/Fri

#### Scenario 4: Weekly Limit
1. Create 3 tasks all for "TTC Abu Dhabi"
2. All campaigns: 15-Jan to 18-Jan (very tight window)
3. Expected: Only 2 shoots scheduled, 3rd deferred or exception

---

## Implementation Checklist

### Pre-Implementation
- [ ] Answer all outstanding questions (Q1-Q7)
- [ ] Get exact location names from production config (Q3)
- [ ] Identify Abu Dhabi videographer name/details
- [ ] Decide on photo editing capacity (Q2)
- [ ] Approve schema changes

### Phase 1: Configuration (No code changes)
- [ ] Create `abu_dhabi_config.json` with location mappings
- [ ] Update `videographer_config.json` with Abu Dhabi person
- [ ] Document exact location strings

### Phase 2: Schema Updates (Database changes)
- [ ] Add `Time Block` column to `live_tasks`
- [ ] Add `Time Block` column to `completed_tasks`
- [ ] Add `Brief Date` if needed (Q1)
- [ ] Add `Filming Date Override` if needed (Q4)
- [ ] Create migration script
- [ ] Test migration on backup database

### Phase 3: UI/Input Changes
- [ ] Update `tools.py` to include `time_block` parameter
- [ ] Update `llm_utils.py` to parse `time_block` from user input
- [ ] Add `time_block` to confirmation flow
- [ ] Update Trello card description template

### Phase 4: Core Algorithm
- [ ] Create `abu_dhabi_scheduler.py` module
- [ ] Implement location classification functions
- [ ] Implement candidate date generation
- [ ] Implement overlap scoring
- [ ] Implement weekly constraint checking
- [ ] Implement main scheduling function

### Phase 5: Integration
- [ ] Modify `utils.py:calculate_filming_date()` to route Abu Dhabi
- [ ] Update `db_utils.py` to pass location/task_type/time_block
- [ ] Update `assignment.py` Trello card with time_block
- [ ] Test end-to-end flow

### Phase 6: Testing
- [ ] Write unit tests for scheduler logic
- [ ] Write integration tests
- [ ] Run manual test scenarios
- [ ] Test with production-like data
- [ ] Verify non-Abu Dhabi locations unaffected

### Phase 7: Deployment
- [ ] Deploy to staging
- [ ] Run full test suite
- [ ] Monitor for issues
- [ ] Deploy to production
- [ ] Document new workflow

---

## Rollback Plan

If implementation causes issues:

### Immediate Rollback (< 1 hour)
1. Revert code changes to `utils.py`, `assignment.py`
2. System falls back to 2nd/17th logic for ALL locations
3. New schema columns remain (NULL values OK)
4. No data loss

### Partial Rollback (Abu Dhabi only)
1. Add feature flag: `ABU_DHABI_SCHEDULING_ENABLED = False`
2. Wrap routing logic in flag check
3. Keeps new fields but disables algorithm

### Full Rollback (> 1 day)
1. Revert all code changes
2. Drop new schema columns (if needed)
3. Restore to pre-implementation state

---

## Success Metrics

### Functional Metrics
- ✅ Abu Dhabi locations route to new algorithm
- ✅ Non-Abu Dhabi locations unchanged
- ✅ Filming dates only on Tue/Thu/Fri for Abu Dhabi
- ✅ Max 2 shoots per week enforced
- ✅ Campaign overlap maximized
- ✅ No system errors or crashes

### Business Metrics
- Measure: % of Abu Dhabi shoots with 2+ campaigns bundled
- Target: > 70% of shoots have multiple campaigns
- Measure: Average campaigns per Abu Dhabi shoot
- Target: >= 2.0 campaigns per shoot

---

## Next Steps

1. **Review this document** with stakeholders
2. **Answer outstanding questions** (Q1-Q7)
3. **Get location name mappings** from production
4. **Approve schema changes**
5. **Proceed to implementation** following checklist

---

*Document Version: 1.0*
*Last Updated: 2025-01-18*
*Status: PENDING REVIEW - Awaiting answers to Q1-Q7*
