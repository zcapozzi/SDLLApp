# SDLL Scheduling System Architecture

This document describes the backend architecture for the South Durham Little League scheduling system.

---

## Table of Contents

1. [Overview](#overview)
2. [Three-Phase Workflow](#three-phase-workflow)
3. [Time-Based Scheduling](#time-based-scheduling)
4. [Data Models](#data-models)
5. [Scheduling Logic](#scheduling-logic)
6. [Validation Rules](#validation-rules)
7. [Key Routes](#key-routes)
8. [Configuration](#configuration)

---

## Overview

The scheduling system generates and manages game schedules for multiple leagues within a season. It handles:

- **Regular season games** (2-hour duration)
- **Practices** (90-minute duration, can share fields)
- **Scrimmages** (pre-season, 2-hour duration)
- **Playoff games** (2-hour or 3-hour for no-time-limit)

The system uses a **three-phase workflow** to separate slot creation from schedule generation, allowing for iterative refinement before locking.

---

## Three-Phase Workflow

### Phase 1: Setup
Empty game slots are created before any scheduling occurs.

```
LeagueSeason config → Game.generate_game_slots() → Empty Game records
```

**What happens:**
- Calculate total games needed: `(teams × games_per_team) / 2`
- Create empty `Game` records with only metadata (year, is_spring, league, game_type)
- No teams, dates, or fields assigned yet

**Trigger:** "Create Game Slots" button per league, or "Create All Game Slots" for all ready leagues

### Phase 2: Draft
The `ScheduleGenerator` fills empty slots with matchups, dates, and fields.

```
Empty slots + Field allocations + Teams → ScheduleGenerator.generate() → Proposed schedule
```

**What happens:**
- **Games First**: Schedule all games for ALL leagues before any practices
  - This ensures games (mandatory) get priority over practices (flexible)
  - Prevents later leagues from losing field slots to earlier leagues' practices
- Generate round-robin matchups ensuring balance
- Assign dates within the configured season window
- Assign fields based on preference and availability
- Calculate time offsets for multiple games per slot
- **Practices Second**: Schedule practices for all leagues after games
- Validate against hard and soft rules
- Store proposal in session for review

**Can be repeated:** Users can regenerate until satisfied

### Phase 3: Locked
Schedule is accepted and protected from regeneration.

```
Proposed schedule → Save & Lock → LeagueSeason.schedule_locked = True
```

**What happens:**
- Assignments written to Game records
- `schedule_locked` flag set on LeagueSeason
- Regeneration blocked (requires admin unlock)
- Manual edits still allowed via game management UI

---

## Time-Based Scheduling

### Activity Durations

| Activity Type | Duration | Constant |
|--------------|----------|----------|
| Regular Game | 120 min (2 hrs) | `GAME_DURATION_MINUTES` |
| No-Time-Limit Game | 180 min (3 hrs) | `GAME_NO_LIMIT_DURATION_MINUTES` |
| Practice | 90 min | `PRACTICE_DURATION_MINUTES` |

### Slot Capacity Calculation

A field slot's capacity depends on its duration:

```python
# Games: sequential only
game_capacity = slot_duration_minutes // 120

# Practices: sequential × sharing
time_slots = slot_duration_minutes // 90
practice_capacity = time_slots × field.practice_capacity
```

**Example:** A 4-hour slot (5:30 PM - 9:30 PM) = 240 minutes
- Games: `240 // 120 = 2` sequential games (5:30 PM, 7:30 PM)
- Practices: `240 // 90 = 2` time blocks × 2 teams/field = 4 practices

### Time Offset Calculation

When multiple activities share a slot, start times are offset:

```python
# For the Nth game in a slot:
time_offset = N * GAME_DURATION_MINUTES  # 0, 120, 240...

# For the Nth practice in a slot:
time_block = N // field.practice_capacity
time_offset = time_block * PRACTICE_DURATION_MINUTES
```

---

## Data Models

### Core Models

```
LeagueSeason
├── year, is_spring
├── league (FK → League)
├── first_practice_date
├── opening_day_date
├── regular_season_end_date    ← Games/practices scheduled until this date
├── season_end_date            ← Playoffs scheduled until this date
├── practice_days (bitmask)
├── game_days (bitmask)
├── regular_season_games
├── playoff_format
└── schedule_locked

Game
├── year, is_spring, league
├── game_type ('regular', 'playoff', 'practice')
├── home_ID, away_ID (FK → TeamSeason)
├── game_date (datetime)
├── location (field name)
├── status ('scheduled', 'completed', 'postponed', 'cancelled')
├── is_scrimmage
├── no_time_limit              ← 3-hour game flag
└── duration_minutes (computed property)

FieldSlot
├── field_ID (FK → Field)
├── year, is_spring
├── day_of_week (0-6)
├── start_time, end_time       ← Duration determines capacity
├── league (optional restriction)
└── is_owned

Field
├── location_title
├── usage_type ('both', 'games_only', 'practice_only')
├── practice_capacity          ← Teams that can share simultaneously
├── practice_capacity_late     ← Different capacity for late slots
└── allowed/preferred by League
```

### Relationships

```
League
├── allowed_game_fields[]
├── allowed_practice_fields[]
├── preferred_fields[]         ← Ordered by preference
├── earliest_start_time
└── latest_start_time

TeamSeason
├── team_ID, year, is_spring
├── league
├── display_name
└── is_external (for inter-league games)
```

---

## Scheduling Logic

### Field Selection Priority

Fields are selected in this order:

1. **Preferred fields** (in order listed in `League.preferred_fields`)
2. **Allowed but non-preferred fields** (lowest priority)
3. **Fields not in allowed list** (never used)

```python
def slot_preference_key(slot):
    if field_id in preferred_ids:
        return (preferred_ids.index(field_id),)  # 0, 1, 2...
    else:
        return (len(preferred_ids) + 1, field_id)  # After all preferred
```

### Date Constraints

Scheduling respects configured date boundaries:

| Activity | Start Date | End Date |
|----------|------------|----------|
| Pre-season practices | `first_practice_date` | `opening_day_date - 1` |
| Scrimmages | Last day before opening | Same day |
| Regular games | `opening_day_date` | `regular_season_end_date` |
| Post-opening practices | `opening_day_date` | `regular_season_end_date` |
| Playoff games | After regular season | `season_end_date` |

### Round-Robin Generation

```python
total_games = (teams × games_per_team) // 2
games_per_pair = games_per_team // (team_count - 1)

# Alternate home/away each round
for round in range(games_per_pair):
    for each pair:
        if (round + i + j) % 2 == 0:
            matchups.append((team_i, team_j))
        else:
            matchups.append((team_j, team_i))

shuffle(matchups)  # Avoid predictable patterns
```

---

## Validation Rules

### Hard Rules (MUST NOT violate)

| Code | Rule | Description |
|------|------|-------------|
| `a1` | Play everyone | All team pairs must play; max difference of 1 game between pairs |
| `b1` | Home/away balance | Each team's home/away games differ by at most 1 |
| `d1` | One activity per day | Each team can have at most one game or practice per day |
| `e1` | Minimum games | Each team must play at least the configured number of regular season games |
| `gap` | Same team gap | Teams can't play back-to-back against same opponent |
| `slot` | Field double-booked | No two games at same time on same field |

### Soft Rules (SHOULD avoid)

| Code | Rule | Description |
|------|------|-------------|
| `a2` | Home/away vs opponent | Alternate home/away when teams play multiple times |
| `b2` | Early/late balance | Balance games 4-6 PM vs 6 PM+ (games before 4 PM excluded, diff > 2 flagged) |
| `c2` | Practice field balance | Distribute practice locations evenly |
| `c3` | Solo practice balance | Equal solo practice opportunities per team |
| `e2` | Game day balance | All teams should play on the same game days (no team sits out while others play) |

---

## Key Routes

### Scheduler Routes (`/scheduler/`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/<year>/<is_spring>` | GET | Scheduler overview with prerequisites |
| `/<year>/<is_spring>/create-slots` | POST | Create empty slots for one league |
| `/<year>/<is_spring>/create-all-slots` | POST | Create empty slots for all ready leagues |
| `/<year>/<is_spring>/generate` | POST | Generate proposed schedule |
| `/<year>/<is_spring>/review` | GET | Review proposed schedule |
| `/<year>/<is_spring>/save` | POST | Save and optionally lock schedule |
| `/<year>/<is_spring>/start-fresh` | POST | Clear assignments and regenerate |
| `/<year>/<is_spring>/unlock` | POST | Admin unlock for regeneration |
| `/<year>/<is_spring>/validate` | POST | Validate existing schedule |

### Game Routes (`/games/`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/<year>/<is_spring>/calendar` | GET | Week view with CSS filters |
| `/<year>/<is_spring>/day/<date>` | GET | Single day grid view (field × time) |
| `/<year>/<is_spring>/manage` | GET/POST | List view with inline editing |
| `/<year>/<is_spring>/rainout` | GET/POST | Bulk postpone/reschedule |

---

## Configuration

### Schedule Settings (per league)

Required before generating:

- **First Practice Date** - When practices begin
- **Opening Day Date** - When games begin
- **Regular Season End Date** - All regular games must complete by this date
- **Season End Date** - All playoff games must complete by this date
- **Practice Days** - Days of week for practices (bitmask)
- **Game Days** - Days of week for games (bitmask)
- **Regular Season Games** - Games per team (default: 10)
- **Playoff Format** - single_elim, double_elim, round_robin

### Field Properties

- **Usage Type** - games_only, practice_only, or both
- **Practice Capacity** - Teams that can share (1-4)
- **Late Slot Capacity** - Different capacity for 7:30+ PM slots

### League Field Rules

- **Allowed Game Fields** - Which fields can host games
- **Allowed Practice Fields** - Which fields can host practices
- **Preferred Fields** - Ordered list for scheduling priority
- **Time Restrictions** - Earliest/latest start times

---

## File Locations

```
app/
├── utils/
│   └── scheduler.py          # ScheduleGenerator, ScheduleValidator
├── models/
│   ├── game.py               # Game model with duration_minutes
│   ├── league_season.py      # LeagueSeason config
│   ├── field_slot.py         # FieldSlot (time allocations)
│   └── field.py              # Field properties
├── scheduler/
│   └── routes.py             # Scheduler routes
├── games/
│   └── routes.py             # Game management routes
└── templates/
    ├── scheduler/            # Scheduler UI
    └── games/                # Calendar, day view, manage
```

---

## Database Schema Additions

Recent additions to support new features:

```sql
-- No-time-limit flag for games
ALTER TABLE sdll_games
ADD COLUMN no_time_limit TINYINT DEFAULT 0 AFTER is_scrimmage;
```

---

## Summary

The scheduling system:

1. **Separates concerns** - Slot creation, schedule generation, and locking are distinct phases
2. **Respects time** - Uses activity durations to calculate real slot capacity
3. **Prioritizes fairness** - Validates schedules against balance rules
4. **Supports flexibility** - Multiple generation attempts before locking
5. **Enables manual control** - Edits allowed even after locking
