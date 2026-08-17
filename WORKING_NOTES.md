# SDLL Web Application - Working Notes

## Summary
This is a Flask web application for managing South Durham Little League schedules, including game scheduling, field management, and team coordination.

## Current Status
Last session: Made scheduler deterministic and fixed Tier I/III compliance. All tests passing.

---

## Session: August 17, 2026 (Continued) - Deterministic Scheduling Fix

### Problem
After implementing the three-tier hierarchy, the scheduler had non-deterministic results due to `random.shuffle` and `random.choice` calls. Some runs would pass (0 e1 violations) while others would fail (teams getting fewer games than required).

Additionally:
- BB Tee Ball intermittently had teams with 5/6 games
- SB Seniors Team 3 consistently had 6/7 games (mathematically impossible configuration)

### Root Causes
1. **Non-determinism**: Random calls in round-robin generation and scrimmage pairing caused different results each run
2. **Skipped partial dates**: First pass skipped dates with fewer slots than needed for a "full round", leaving too much for catch-up pass
3. **SB Seniors config**: 3 teams × 7 games = 21 slots (odd) → mathematically impossible for all teams to get 7 games

### Fixes Applied

1. **Removed all randomness** (`app/utils/scheduler.py`):
   - Replaced `random.shuffle(candidate_pairs)` with deterministic sort by team IDs
   - Replaced `random.choice(neediest_teams)` with taking first element (already sorted)
   - Replaced `random.shuffle(shuffled)` in scrimmage generation with sorted teams
   - Replaced `random.choice(top_candidates)` in matchup selection with first candidate

2. **Greedy scheduling for partial dates**:
   - Previously: Dates with < n/2 slots were skipped entirely
   - Now: Uses greedy scheduling to fill available slots on all dates
   - This distributes games better and reduces catch-up pass overload

3. **Added impossibility warning**:
   - Detects when `n_teams × games_per_team` is odd
   - Warns that one team will be short

4. **Configuration change**:
   - SB Seniors: Changed from 7 to 6 games per team
   - With 3 teams, 6 games works perfectly (9 total games, 3 per pair)

### Test Results
```
Run 1: Tier I=0, Tier III(e1)=0, Tier II=179 - PASS
Run 2: Tier I=0, Tier III(e1)=0, Tier II=179 - PASS
Run 3: Tier I=0, Tier III(e1)=0, Tier II=179 - PASS
Run 4: Tier I=0, Tier III(e1)=0, Tier II=179 - PASS
Run 5: Tier I=0, Tier III(e1)=0, Tier II=179 - PASS
```

All runs are now deterministic (same Tier II count) and pass Tier I and III requirements.

### Commit
`3f12bac` - Make scheduler deterministic and satisfy Tier I/III rules

---

## Session: August 17, 2026 - Three-Tier Rule Hierarchy

### Problem
The previous commit (b7f9343) tried to fix e1 violations (minimum games) by allowing double-booking (2 games/day for a team), which violated rule d1. It also didn't respect team-specific practice days.

### Solution
Reverted the problematic commit and implemented a proper three-tier rule hierarchy:

| Tier | Name | Behavior | Examples |
|------|------|----------|----------|
| **I** | NEVER | Absolute constraints - never violated, even if e1 fails | d1, slot, f1, f1c |
| **II** | AVOID | Soft rules - can be violated to achieve Tier III goals | a1, b1, a2, b2, c2, c3, e2, f1a, f1b, gap |
| **III** | GOAL | Primary objectives - other rules sacrificed for this | e1 (minimum games) |

### Key Principle
The scheduler will progressively relax Tier II constraints to achieve Tier III goals, but will **never** violate Tier I constraints. If e1 cannot be achieved without violating Tier I, the shortfall is accepted.

### Changes Made

1. **Reverted commit b7f9343** - Removed the flawed "last-resort double-booking" approach

2. **Updated `ScheduleViolation` class** (`app/utils/scheduler.py`):
   - Added three severity constants: `NEVER`, `AVOID`, `GOAL`
   - Legacy aliases: `HARD = NEVER`, `SOFT = AVOID`

3. **Reclassified rules**:
   - Tier I (NEVER): d1, slot, f1, f1c
   - Tier II (AVOID): a1, b1, a2, b2, c2, c3, e2, f1a, f1b, gap
   - Tier III (GOAL): e1

4. **Updated `howToSchedule.md`**:
   - Reorganized into Tier I/II/III sections
   - Updated Rule Codes Reference table
   - Documented scheduler behavior for each tier

5. **Updated proposal summary**:
   - Added `never_violations`, `avoid_violations`, `goal_violations` counts
   - Kept `hard_violations`, `soft_violations` for backwards compatibility

### Verified Issues
Before reverting, confirmed the problems in the current proposal:
- **4 d1 violations**: BB Tee Ball teams with 2 games on same day
- **9 practice day violations**: BB Rookie teams practicing on wrong days

### Next Steps
Implement proper e1 handling that:
1. First attempts to satisfy all rules
2. If e1 fails, progressively relaxes Tier II rules
3. Never violates Tier I rules
4. Reports any remaining e1 shortfall as a configuration issue

---

## Session: August 16, 2026 - Same-League Practice Sharing Constraint

### Feature
Two teams can share a practice field at the same time ONLY if they are in the same league. This prevents cross-league practice conflicts.

### Implementation

1. **New Tracker** (`app/utils/scheduler.py`):
   - Added `_practice_slot_leagues` dictionary to track which league is using each practice slot
   - Key: `(field_id, datetime_iso)` → league name

2. **Scheduler Changes** (`_assign_practices_for_date`):
   - When checking slot capacity, also verifies the slot is either empty or used by the same league
   - If slot is used by a different league, it's treated as unavailable (even if capacity allows)
   - When assigning a practice, records the league in `_practice_slot_leagues`

3. **Validator Changes** (`_check_practice_field_capacity`):
   - Added new rule **f1c: Cross-league practice sharing**
   - Groups practices by field/time slot
   - Checks if multiple leagues are sharing the same slot
   - Reports HARD violation if different leagues share a practice slot
   - Added `_get_league()` helper method to extract league from game objects

### Rule Codes
- **f1**: Practice field capacity (existing) - too many teams for field's capacity
- **f1c**: Cross-league practice sharing (new) - different leagues sharing same practice slot

### Files Modified
- `app/utils/scheduler.py`:
  - Added `_practice_slot_leagues` tracker
  - Updated `_assign_practices_for_date()` to check and track league
  - Updated `_check_practice_field_capacity()` to validate same-league sharing
  - Added `_get_league()` helper method

---

## Session: August 16, 2026 - Weekly Activity Limits for P/G Leagues

### Feature
For leagues that have P/G (both) days configured, teams should play exactly 2 games and have 1 practice per week starting from opening day.

### Implementation

1. **Weekly Trackers** (`app/utils/scheduler.py`):
   - Added `_team_week_practices` and `_team_week_games` dictionaries to track activity counts
   - Key: `(team_id, week_num)` → count
   - Week numbers are calculated relative to opening day using `_get_week_number()`

2. **Practice Limit** (1 per week for P/G leagues):
   - Modified `_generate_post_opening_practices()` to pass `max_practices_per_week=1` for P/G leagues
   - Modified `_assign_practices_for_date()` to accept and enforce `max_practices_per_week` parameter
   - Checks weekly limit before assigning practices, updates counter after assignment

3. **Game Limit** (2 per week for P/G leagues):
   - Modified `_assign_games_to_slots()` to accept `max_games_per_week` parameter
   - Calculates week number relative to opening day for each game date
   - In team availability check, also verifies teams haven't hit weekly game limit
   - Updates `_team_week_games` counter when games are assigned
   - Both first pass (full rounds) and catch-up pass respect weekly limits

### Key Code Changes

```python
# In _assign_games_to_slots signature:
def _assign_games_to_slots(self, config, matchups, slots_by_date, league,
                           existing_game_records=None, start_fresh=False,
                           max_games_per_week=None):

# Weekly limit check for team availability:
if max_games_per_week and week_num is not None:
    team_week_key = (team_id, week_num)
    if self._team_week_games[team_week_key] >= max_games_per_week:
        unavailable_teams.append(f'Team {team_id} hit weekly limit')
        continue

# Update counter when game assigned:
if max_games_per_week and week_num is not None:
    self._team_week_games[(home.team_ID, week_num)] += 1
    self._team_week_games[(away.team_ID, week_num)] += 1
```

### Behavior

- Week 0 starts on opening day
- Each team can play max 2 games per week (if P/G league)
- Each team can have max 1 practice per week (if P/G league)
- Weekly limits only apply AFTER opening day (pre-opening practices are unlimited)
- Non-P/G leagues are unaffected (no weekly limits)

### Files Modified
- `app/utils/scheduler.py` - Added weekly limit logic to game and practice assignment

---

## Session: August 15, 2026 - AA/AAA Practice Scheduling Fix

### Issue
BB AA and BB AAA leagues were not showing practices on Aug 31 and Sept 7 (both Mondays) during the pre-opening period.

### Root Causes Found

1. **Database values were swapped**: The `first_practice_date` and `opening_day_date` values were reversed in the database.
   - BB AAA had: `opening_day_date`=Aug 31, `first_practice_date`=Sept 14
   - Should be: `first_practice_date`=Aug 31, `opening_day_date`=Sept 14

2. **Scheduler logic bug**: The `_assign_practices_for_date` function only scheduled practices on practice days, even during the pre-opening period when practices should be scheduled on ALL activity days (game + practice days).

### Fixes Applied

1. **Database fix**: Updated `railway_backup.sql` and live database to swap the dates:
   - BB AAA: `first_practice_date`=2026-08-31, `opening_day_date`=2026-09-14
   - BB AA: `first_practice_date`=2026-09-01, `opening_day_date`=2026-09-17

2. **Scheduler fix** (`app/utils/scheduler.py`):
   - Added `is_pre_opening` parameter to `_assign_practices_for_date()` function
   - Pre-opening practices now skip the practice-day-only filter
   - Pre-opening logic passes `is_pre_opening=True` when calling the function

3. **Post-opening fix**: Also added logic to respect `first_practice_date` for post-opening practices (uses `max(opening_day, first_practice)` as start date).

### Semantic Clarification
- `first_practice_date`: Date when practices can BEGIN (earliest practice date)
- `opening_day_date`: Date when GAMES can start being scheduled

Before opening day, practices are scheduled on ALL activity days (game days + practice days).
After opening day, games are scheduled on game days and practices only on practice days.

### Files Modified
- `app/utils/scheduler.py` - Added `is_pre_opening` parameter and logic
- `railway_backup.sql` - Swapped date values for BB AAA and BB AA

### Testing
Verified that practices now generate correctly:
- BB AAA: Aug 31 (Mon), Sept 2 (Wed), Sept 4 (Fri), Sept 7 (Mon), Sept 9 (Wed), then scrimmage on Sept 11
- BB AA: Sept 1 (Tue), Sept 3 (Thu), Sept 5 (Sat), Sept 8 (Tue), etc.

---

## Session: August 15, 2026 - P/G Days and Day-of-Week Balance

### New Features

1. **P/G Days (Both Practice and Game)**: Days can now be configured as 'both' (P/G), meaning they can have either practices or games scheduled.
   - Click days in schedule settings to cycle: - → P → G → P/G → -
   - P/G days are included in both `practice_days` and `game_days` properties
   - Scheduler prioritizes games first (Phase 1), then fills remaining slots with practices (Phase 2)

2. **Day-of-Week Game Balance Rule (f1)**: For leagues with P/G days, validates that game distribution across days of week is balanced.
   - **Soft violation (f1a)**: Teams differ by 2+ games on a given day of week
   - **Hard violation (f1b)**: Teams differ by 3+ games on a given day of week

### Files Modified
- `app/models/league_season.py`:
  - Added `DAY_TYPE_BOTH = 'both'` constant
  - Updated `practice_days` and `game_days` to include 'both' days
  - Added `both_days`, `has_pg_days`, `practice_only_days`, `game_only_days` properties
  - Updated `schedule_ready` to check for 'both' type
  - Updated display properties to mark P/G days with asterisk

- `app/utils/scheduler.py`:
  - Added `_check_day_of_week_game_balance()` validation method
  - Validates game distribution on P/G days only

- `app/templates/seasons/schedule_settings.html`:
  - Added CSS for `.day-cell.both` with gradient background
  - Updated legend to include P/G option
  - Updated JavaScript cycling to include 'both' option
  - Updated template to display 'P/G' for both days
