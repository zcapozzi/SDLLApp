# SDLL Scheduling Rules & Principles

This document defines the rules and principles that any schedule generator must follow when creating game schedules for South Durham Little League. Rules are categorized as **HARD** (cannot be violated) or **SOFT** (should be avoided unless necessary to satisfy a hard rule).

---

## Table of Contents

1. [Scheduling Workflow](#scheduling-workflow)
2. [Hard Rules (MUST NOT violate)](#hard-rules-must-not-violate)
3. [Soft Rules (SHOULD avoid)](#soft-rules-should-avoid)
4. [Field Restrictions](#field-restrictions)
5. [Time Restrictions](#time-restrictions)
6. [Season Configuration](#season-configuration)
7. [Rule Codes Reference](#rule-codes-reference)

---

## Scheduling Workflow

The schedule generation follows a **three-phase workflow**:

### Phase 1: Setup
- Empty game slots are created via `Game.generate_game_slots()`
- Field allocations are configured (which fields are available on which days/times)
- Teams are assigned to leagues
- Schedule settings are configured (game days, practice days, dates)

### Phase 2: Draft
- The `ScheduleGenerator` fills in matchups, dates, and fields for existing slots
- Multiple proposals can be generated and compared
- Violations are reported for review
- Changes can be made and regenerated

### Phase 3: Locked
- Schedule is accepted and locked (per league via `LeagueSeason.lock_schedule()`)
- Regeneration is blocked for locked leagues
- Manual edits only (via game management UI)
- Can be unlocked if regeneration is needed

---

## Hard Rules (MUST NOT violate)

These rules represent fundamental fairness requirements. A schedule that violates any hard rule is **invalid** and must be regenerated.

### Rule a1: Play Everyone / Matchup Balance

**Description:** Every team must play every other team at least once, and the number of times any two teams play should differ by no more than 1.

**Why it matters:** Ensures competitive fairness - no team gets an "easy" schedule by avoiding certain opponents.

**Validation logic:**
- Count games between each pair of teams
- All pairs must have count >= 1
- `max(count) - min(count)` must be <= 1

**Example violation:**
- Team A plays Team B 3 times, but Team A plays Team C only 1 time (difference > 1)

---

### Rule b1: Home/Away Balance

**Description:** Each team's home games and away games must differ by no more than 1.

**Why it matters:** Ensures no team has a significant home-field advantage or disadvantage.

**Validation logic:**
- Count home games per team
- Count away games per team
- For each team: `|home - away|` must be <= 1

**Example violation:**
- Team A has 6 home games and 4 away games (difference = 2)

---

### Rule gap: No games at the same time on the same field

**Description:** Each field can only have a single game at a time; there cannot be two games scheduled on the same slot at the same field

**Why it matters:** One game at a time

**Validation logic:**
- Confirm that each slot only has a single game

**Example violation:**
- Week 1: Team A vs Team B play 5:30 at Herndon 1
- Week 2: Team C vs Team D also play 5:30 at Herndon 1

---

## Soft Rules (SHOULD avoid)

Soft rules represent preferences for schedule quality. Violating these is acceptable when necessary to satisfy hard rules, but the generator should minimize violations.

### Rule a2: Home/Away Balance vs Specific Opponent

**Description:** When two teams play multiple times, they should alternate who is home and who is away.

**Why it matters:** Prevents scenarios where one team is always "home" against a specific rival.

**Validation logic:**
- Track home games per team against each specific opponent
- Flag if team is home 2+ times vs same opponent with 0 away games

**Example violation:**
- Team A is home against Team B in both of their matchups, and never away

---

### Rule b2: Early/Late Time Balance

**Description:** Each team should have a balanced distribution of early games (before 6:00 PM) and late games (6:00 PM or later).

**Why it matters:** Late games can be harder for younger players; fairness requires sharing the burden.

**Threshold:** Difference of more than 2 is flagged.

**Validation logic:**
- Count early games (start time < 18:00) per team
- Count late games (start time >= 18:00) per team
- Flag if `|early - late|` > 2

**Example violation:**
- Team A has 8 early games and 2 late games (difference = 6)

---

### Rule c2: Practice Field Balance

**Description:** Each team's practice locations should be evenly distributed across available practice fields.

**Why it matters:** Some fields may be more desirable (better maintained, better parking, etc.). Sharing ensures fairness.

**Threshold:** Difference of more than 2 per field is flagged.

**Validation logic:**
- Count practices per team at each field
- Flag if `max(field_count) - min(field_count)` > 2

---

### Rule c3: Solo Practice Balance

**Description:** Each team should have an equal number of practices where they're the only team at the field.

**Why it matters:** Solo practices allow for more focused coaching and use of the entire field. Teams should share this benefit equally.

**Threshold:** Difference of more than 1 solo practice between teams is flagged.

**Validation logic:**
- Count solo practices (no other teams at field/time) per team
- Compare across all teams in the league
- Flag if `max(solo_count) - min(solo_count)` > 1

---

## Field Restrictions

Leagues can have field restrictions that must be respected:

### Allowed Game Fields
- Configured via `League.allowed_game_fields`
- Empty/NULL = any field with `allows_games=True` is allowed
- If set, games can ONLY be scheduled at the listed fields

### Allowed Practice Fields
- Configured via `League.allowed_practice_fields`
- Empty/NULL = any field with `allows_practices=True` is allowed
- If set, practices can ONLY be scheduled at the listed fields

### Preferred Fields
- Configured via `League.preferred_fields`
- Ordered list of field IDs in preference order
- Generator should try to use preferred fields first when multiple options exist

### Non-Preferred Fields Priority
- If a field is in `allowed_game_fields` or `allowed_practice_fields` but NOT in `preferred_fields`, it has lowest priority
- These fields are used only when preferred fields are at capacity
- Order of preference:
  1. Fields in `preferred_fields` (in order listed)
  2. Fields in allowed list but not in preferred (lowest priority)
  3. Fields not in allowed list are never used

### Field Capacities
- Fields have `practice_capacity_early` and `practice_capacity_late` settings
- Multiple teams can share a practice slot up to the capacity limit
- Games always require exclusive field use (capacity = 1)

---

## Time Restrictions

### Field Allocations versus Practice & Game Slots
- A field allocation can support multiple games or practices; you can't have two games at 5:30 on the same field, but if the allocation is from 5:30 to 9:30, then you can have two games scheduled on that day, one at 5:30pm and one at 7:30pm
- All regular season games should be scheduled for 2 hours and all practices should be scheduled for 90 minutes

### No Time Limit Games
- Games can be flagged with `no_time_limit = 1` in the database
- No-time-limit games are allocated 3 hours instead of 2 hours
- This flag is displayed to umpires so they know the game format
- Typically used for: championship games, playoff finals, tiebreakers
- Set via the game edit modal (checkbox: "No Time Limit (3 hrs)")

### League Time Restrictions
- Configured via `League.earliest_start_time` and `League.latest_start_time`
- NULL = no restriction
- Generator must only assign games/practices within allowed times

**Common use cases:**
- Younger leagues (Tee Ball) may be restricted to early slots only
- Older leagues (Majors) may be restricted to later slots

### Field Time Restrictions
- Configured via `FieldTimeRestriction` model
- League-specific time windows per field
- Overrides default field hours for specific leagues

---

## Season Configuration

### Required Settings (per league)
Before generating a schedule, each league must have:

1. **First Practice Date** - When practices begin
2. **Opening Day Date** - When games begin
3. **Regular Season End Date** - All regular season games must be completed by this date
4. **Season End Date** - All playoff games must be completed by this date
5. **Game Days** - Which days of the week have games (e.g., Tue, Thu)
6. **Practice Days** - Which days of the week have practices (e.g., Mon, Wed)
7. **Regular Season Games** - Number of games per team (default: 10)
8. **Playoff Format** - Single elimination, double elimination, or round robin + knockout
9. **Playoff Teams** - Number of teams that qualify (0 = all teams)

### Date Ordering Requirement
Dates must be in chronological order:
```
First Practice Date < Opening Day Date < Regular Season End Date < Season End Date
```

### Pre-Opening Day Period
- First practice to day before opening day
- Activities scheduled on practice days AND game days
- Last activity day before opening = scrimmage day
- All other days = practice days

### Post-Opening Day Period
- Games scheduled on game days only
- Practices scheduled on practice days only
- Scrimmages can be scheduled as needed

---

## Rule Codes Reference

| Code | Name | Severity | Description |
|------|------|----------|-------------|
| `a1` | Play everyone / Matchup balance | HARD | All pairs play, max diff of 1 |
| `b1` | Home/away balance | HARD | Per team, home/away diff <= 1 |
| `gap` | Same team gap | HARD | No back-to-back vs same opponent |
| `slot` | Field double-booked | HARD | No two games at same time on same field |
| `a2` | Home/away vs opponent | SOFT | Alternate home/away when playing same team |
| `b2` | Early/late time balance | SOFT | Balance game start times per team |
| `c2` | Practice field balance | SOFT | Distribute practice locations evenly |
| `c3` | Solo practice balance | SOFT | Equal solo practice opportunities per team |

---

## Validation Process

When validating a schedule (existing or proposed):

1. Group games by league
2. Extract actual games (exclude practices)
3. Identify all teams from game records
4. Run each validation rule
5. Collect all violations with severity
6. Return violations list for review

### Violation Structure
```python
{
    'rule_code': 'a1',
    'rule_name': 'Matchup balance',
    'severity': 'hard',  # or 'soft'
    'message': 'AA: Teams X and Y have not played each other',
    'game_ids': [123, 456]  # affected games if applicable
}
```

---

## Implementation Notes

### Round-Robin Generation
The generator creates round-robin matchups:
1. Calculate total games needed: `(games_per_team * team_count) / 2`
2. Calculate games per pair: `games_per_team / (team_count - 1)`
3. Generate base matchups, alternating home/away each round
4. Shuffle to avoid predictable patterns
5. Trim to exact count needed

### Slot Assignment
When assigning games to field slots:
1. Check field restrictions for league
2. Check time restrictions for league
3. Track home/away counts to maintain balance
4. Track early/late counts to maintain balance
5. Prefer unused slots over reusing capacity

### Scrimmage Generation
For scrimmages (pre-season only):
1. Shuffle teams randomly
2. Pair teams sequentially
3. Assign to available slots
4. Odd team out gets no scrimmage partner (warning issued)

---

## Manual Editing (Post-Lock)

After a schedule is locked, manual edits are made through the game management UI:

### Allowed Actions
- Change game date/time
- Change game field
- Change home/away teams
- Convert game to practice (remove away team)
- Convert practice to game (add away team)
- Change game status (scheduled, completed, postponed, cancelled)
- Add scrimmage flag

### Rainout Handling
1. Select date with affected games
2. Bulk "Postpone All" - marks all as postponed status
3. Individual reschedule to practice dates
4. Custom reschedule to any date/time

### External Teams
- External organizations (Bull City, Morrisville, etc.) can be added
- External teams can be assigned to away (or home) slot
- Used for inter-league games

---

## Future Enhancements

Consider adding these rules in future versions:

1. **Bye week balance** - For leagues with odd team counts
2. **Travel partner awareness** - Minimize consecutive away games for teams with long travel
3. **Weather makeup preferences** - Suggest best makeup dates based on team availability
4. **Umpire availability** - Consider umpire assignments when scheduling
5. **Rivalry game placement** - Place important matchups at optimal times
