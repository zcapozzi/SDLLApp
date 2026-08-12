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

### Rule gap: No Back-to-Back Against Same Opponent

**Description:** The same two teams cannot play each other in consecutive games without at least one game against a different opponent in between.

**Why it matters:** Prevents repetitive matchups that feel unfair and reduces the variety of competition.

**Validation logic:**
- Sort games by date for each league
- Track last game index for each matchup
- If consecutive games involve the same pair, flag violation

**Example violation:**
- Week 1: Team A vs Team B
- Week 2: Team A vs Team B (same matchup back-to-back)

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

### Field Capacities
- Fields have `practice_capacity_early` and `practice_capacity_late` settings
- Multiple teams can share a practice slot up to the capacity limit
- Games always require exclusive field use (capacity = 1)

---

## Time Restrictions

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
3. **Game Days** - Which days of the week have games (e.g., Tue, Thu)
4. **Practice Days** - Which days of the week have practices (e.g., Mon, Wed)
5. **Regular Season Games** - Number of games per team (default: 10)
6. **Playoff Format** - Single elimination, double elimination, or round robin + knockout
7. **Playoff Teams** - Number of teams that qualify (0 = all teams)

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
| `a2` | Home/away vs opponent | SOFT | Alternate home/away when playing same team |
| `b2` | Early/late time balance | SOFT | Balance game start times per team |
| `c2` | Practice field balance | SOFT | Distribute practice locations evenly |

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
