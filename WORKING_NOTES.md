# SDLL Web Application - Working Notes

## Summary
This is a Flask web application for managing South Durham Little League schedules, including game scheduling, field management, and team coordination.

## Current Status
Last session: Implemented weekly activity limits for P/G leagues (2 games + 1 practice per week).

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
