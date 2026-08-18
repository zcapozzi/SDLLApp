# SDLL Scheduling Rules & Principles

This document defines the rules and principles that any schedule generator must follow when creating game schedules for South Durham Little League.

## Rule Hierarchy (Three Tiers)

Rules are organized into three tiers that define how the scheduler handles conflicts:

| Tier | Name | Behavior | When Violated |
|------|------|----------|---------------|
| **I** | NEVER | Absolute constraints that cannot be violated under any circumstances | Schedule is invalid |
| **II** | AVOID | Preferences that should be satisfied, but can be violated to achieve Tier III goals | Logged as soft violation |
| **III** | GOAL | Objectives that other rules can be sacrificed to achieve | Tier II rules relaxed |

**Key principle:** The scheduler will progressively relax Tier II constraints to achieve Tier III goals, but will **never** violate Tier I constraints. If a Tier III goal cannot be achieved without violating Tier I, the shortfall is accepted.

---

## Table of Contents

1. [Scheduling Workflow](#scheduling-workflow)
2. [Tier I: NEVER Violate](#tier-i-never-violate)
3. [Tier II: AVOID (Soft Rules)](#tier-ii-avoid-soft-rules)
4. [Tier III: GOAL (Objectives)](#tier-iii-goal-objectives)
5. [Field Restrictions](#field-restrictions)
6. [Time Restrictions](#time-restrictions)
7. [Season Configuration](#season-configuration)
8. [Rule Codes Reference](#rule-codes-reference)

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

## Tier I: NEVER Violate

These are absolute constraints. The scheduler will **never** violate these, even if it means Tier III goals cannot be fully achieved. A schedule violating any Tier I rule is invalid.

### Rule d1: One Activity Per Day

**Description:** Each team can have at most one game or practice per day. A team cannot have both a game and a practice on the same day, nor two games on the same day.

**Why it matters:** Prevents over-scheduling teams and ensures players have adequate rest between activities.

**Validation logic:**
- Group all activities (games, practices, scrimmages) by (team, date)
- Flag any team with more than one activity on the same day

**Example violation:**
- Team A has a game at 5:30 PM and a practice at 7:30 PM on the same day

---

### Rule slot: Field Double-Booking

**Description:** Each field can only have a single game at a time; there cannot be two games scheduled on the same slot at the same field; there cannot be a game and a practice at the same field at the same time

**Why it matters:** Physical impossibility - one game at a time per field. You also can't have a practice going on at a field where they are playing a game.

**Validation logic:**
- Confirm that each slot only has a single game

**Example violation:**
- Team A vs Team B at 5:30 at Herndon 1
- Team C vs Team D also at 5:30 at Herndon 1

---

### Rule f1: Practice Field Capacity

**Description:** Each field has a `practice_capacity` setting in the database that defines how many teams can practice simultaneously. The scheduler enforces this limit. If not set, defaults to 1.

**Why it matters:** Fields have varying sizes and configurations. Some can accommodate multiple teams practicing at once (e.g., Cresset=2, Pearsontown=3), while others can only support one team at a time.

**Database fields:**
- `practice_capacity`: Teams that can practice simultaneously (default: 1)
- `practice_capacity_late`: Capacity for late slots like 7:30 PM (NULL = same as regular capacity)

**Validation logic:**
- Group all practices by (field, date, start_time)
- Look up field's `practice_capacity` from database
- For late slots (7 PM+), use `practice_capacity_late` if set
- Flag any slot where teams exceed the field's capacity

**Example violation:**
- Alston Ridge has 3 teams practicing at 5:30 PM (field capacity: 1)

---

### Rule f1c: Same-League Practice Sharing

**Description:** Two teams can share a practice field at the same time ONLY if they are in the same league.

**Why it matters:** Cross-league practice sharing creates conflicts with different age groups and coaching styles.

**Validation logic:**
- Group practices by (field, date, start_time)
- Check if all teams in each slot are from the same league
- Flag any slot with teams from different leagues

---

### Rule gap: Same Team Gap

**Description:** Teams cannot play back-to-back games against the same opponent (no "rematches" on consecutive game dates).

**Why it matters:** Competitive balance - teams need variety in opponents.

**Validation logic:**
- Sort games by date for each team
- Check if consecutive games are against the same opponent
- Flag if two consecutive games are the same matchup

---

### Rule g1: Time Restrictions

**Description:** No games or practices can be scheduled before a league's `earliest_start_time` or after a league's `latest_start_time`. These settings are configured per league in `sdll_leagues`.

**Why it matters:** Younger players (Tee Ball, Rookie) should not have late evening games. Time restrictions ensure age-appropriate scheduling.

**Common settings:**
- Tee Ball leagues: `latest_start_time = 17:30` (no games after 5:30 PM)
- Machine pitch leagues: `latest_start_time = 17:30`
- Older leagues: No restrictions (NULL values)

**Validation logic:**
- Get league's `earliest_start_time` and `latest_start_time` from database
- Check each game/practice start time against these limits
- Flag any activities outside the allowed window

**Example violation:**
- SB Rookie practice at 7:00 PM when `latest_start_time = 17:30`

**Generator behavior:**
- When building practice options, time blocks outside the allowed window are excluded
- Games are only assigned to slots within the allowed time range

---

### Implicit Tier I Constraints

These are enforced during scheduling but don't have explicit rule codes:

- **Team Practice Days**: If a team has specific practice days configured, practices can only be scheduled on those days
- **Field Restrictions**: League-specific field restrictions (allowed/excluded fields) must be respected
- **Field Allocations**: Games/practices can only be scheduled in allocated time slots

---

## Tier II: AVOID (Soft Rules)

Soft rules represent preferences for schedule quality. The scheduler should satisfy these when possible, but **can violate them to achieve Tier III goals** (e1: minimum games). The scheduler should minimize violations.

### Rule a1: Play Everyone / Matchup Balance

**Description:** Every team should play every other team at least once, and the number of times any two teams play should differ by no more than 1.

**Why it matters:** Ensures competitive fairness - no team gets an "easy" schedule by avoiding certain opponents.

**Validation logic:**
- Count games between each pair of teams
- All pairs should have count >= 1
- `max(count) - min(count)` should be <= 1

**Note:** With some configurations (e.g., 8 teams × 6 games = 24 games but 28 pairs), not all pairs can play. This is a configuration limitation, not a scheduler failure.

---

### Rule b1: Home/Away Balance

**Description:** Each team's home games and away games should differ by no more than 1.

**Why it matters:** Ensures no team has a significant home-field advantage or disadvantage.

**Validation logic:**
- Count home games per team
- Count away games per team
- For each team: `|home - away|` should be <= 1

---

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

**Description:** Each team should have a balanced distribution of early games (4:00 PM to before 6:00 PM) and late games (6:00 PM or later). Games before 4:00 PM do not count toward this balance.

**Why it matters:** Late games can be harder for younger players; fairness requires sharing the burden.

**Threshold:** Difference of more than 2 is flagged.

**Validation logic:**
- Skip games starting before 4:00 PM (16:00)
- Count early games (4:00 PM <= start time < 6:00 PM) per team
- Count late games (start time >= 6:00 PM) per team
- Flag if `|early - late|` > 2

**Example violation:**
- Team A has 8 early games (4-6pm) and 2 late games (6pm+) (difference = 6)

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

### Rule c4: Practice Count Balance

**Description:** No team in a league should have 2 or more practices than any other team in the same league.

**Why it matters:** Ensures fair practice opportunities across all teams. If slots are limited, they should be distributed evenly.

**Threshold:** Difference of 2 or more practices between any two teams is flagged.

**Validation logic:**
- Count total practices per team in the league
- Flag if `max(practice_count) - min(practice_count)` >= 2

**Example violation:**
- BB Rookie Team 1 has 8 practices, Team 3 has 4 practices (diff: 4)

**Common causes of violations:**
- Two teams share the same practice day with limited slots (e.g., both want Wednesday)
- League restricted to a single practice field with low capacity
- Team-specific practice days limiting available slots

**Generator behavior:**
- Teams are sorted by practice count before assignment each day
- Teams with fewer practices get priority for available slots
- This ensures fair distribution even when slots are limited

---

### Rule e2: Game Day Balance

**Description:** All teams in a league should play on the same game days. When games are scheduled on a particular date, all teams should be playing - no team should sit out while others play.

**Why it matters:** Ensures fairness and competitive balance. If some teams get extra rest days while others play, it creates an uneven playing field. It also makes scheduling easier for families when they know game days are consistent.

**Validation logic:**
- Group games by date
- For each game date, identify which teams are playing
- Flag any date where some teams play and others don't

**Example violation:**
- On April 15th, 4 of 6 teams in the Minors league play (2 games), but Cardinals and Blue Jays have no game that day

**Generator behavior:**
- The scheduler tries to schedule full rounds (all teams playing) on each game day
- Only uses a date if there's enough field capacity for n/2 games (where n = team count)
- Falls back to partial scheduling only when necessary to meet minimum games requirement

---

## Tier III: GOAL (Objectives)

These are the primary objectives of the scheduler. Tier II rules can be relaxed to achieve these goals, but Tier I rules are never violated.

### Rule e1: Minimum Games

**Description:** Each team must play at least the configured number of regular season games (default: 10 games per team).

**Why it matters:** Ensures all teams get their fair share of playing time. A team shouldn't be short-changed due to scheduling constraints.

**What counts:**
- Regular season games: YES
- Playoff games: YES
- Scrimmages: NO (pre-season practice games don't count toward minimum)
- Practices: NO

**Validation logic:**
- Get the minimum games requirement from the league configuration
- Count regular and playoff games per team (scrimmages excluded)
- Flag any team with fewer counting games than the minimum

**Example violation:**
- Team A has only 8 regular/playoff games when the league requires 10 games per team

**Scheduler behavior:**
1. First attempt: Schedule respecting all Tier I and Tier II rules
2. If e1 fails: Progressively relax Tier II rules (home/away balance, time balance, etc.)
3. If e1 still fails: Accept the shortfall rather than violate Tier I rules
4. Report any teams that couldn't reach minimum games

**Important:** If a league's configuration makes e1 mathematically impossible (e.g., insufficient field slots), this is a configuration issue, not a scheduler failure. The scheduler will report it but cannot solve it.

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

## Scheduling Optimization Principles

These are not rules (violations) but **optimization preferences** that guide the scheduler when choosing between multiple valid options.

### Practice Slot Selection (Weekdays)
**Principle: Earlier time > Preferred field**

For weekday practices, families prefer earlier times over better fields:
- A 5:30pm slot at a less-preferred field beats a 7:30pm slot at the most-preferred field
- This reflects that getting kids home earlier on school nights is more valuable than field quality

**Sort order for weekday practice options:**
1. Time (earlier first: 5:30 > 6:00 > 6:30 > 7:00 > 7:30)
2. Field preference (from `League.preferred_fields`)

### Practice Slot Selection (Weekends)
**Principle: Preferred field > Time**

For weekend practices, field preference takes priority since bedtime is less of a concern.

**Sort order for weekend practice options:**
1. Field preference (from `League.preferred_fields`)
2. Time (earlier first)

### Game Slot Selection
**Principle: Fill both time slots at preferred fields first (umpire efficiency)**

For games, we want to use BOTH the 5:30pm and 7:30pm slots at preferred fields before moving to less-preferred fields. This allows:
- Same umpire to work both games (doubleheader)
- Reduced umpire travel/logistics
- Better utilization of premium fields

**Sort order for game options:**
1. Field preference (from `League.preferred_fields`)
2. Time slot (to fill both slots at same field)

**Example:** If Field A is preferred and Field B is allowed:
- Good: Game 1 at Field A 5:30pm, Game 2 at Field A 7:30pm
- Avoid: Game 1 at Field A 5:30pm, Game 2 at Field B 5:30pm

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

### Game & Practice Durations

Each league can have custom game and practice durations stored in `sdll_leagues`:

| Setting | Column | Default | Description |
|---------|--------|---------|-------------|
| Game Duration | `game_duration_minutes` | 120 (2 hrs) | Time allocated per game |
| Practice Duration | `practice_duration_minutes` | 90 | Time allocated per practice |

**Special Cases:**
- **No-time-limit games** (playoffs): 180 minutes (3 hours) - not configurable per league
- **Tee Ball leagues**: 75 minutes for both games and practices

**How it affects scheduling:**
- Field slot capacity is calculated using the league's duration
- Example: A 7-hour Saturday slot (420 min) at Pearsontown
  - Standard league (120 min games): 3 games capacity
  - Tee Ball (75 min games): 5 games capacity

---

## Rule Codes Reference

### Tier I: NEVER Violate
| Code | Name | Description |
|------|------|-------------|
| `d1` | One activity per day | Max one game or practice per team per day |
| `slot` | Field double-booked | No two games/scrimmages/practices at same time on same field |
| `f1` | Practice field capacity | Enforces field's `practice_capacity` setting from DB (default: 1) |
| `f1c` | Cross-league practice sharing | Teams sharing practice slot must be same league |
| `g1` | Time restrictions | No games/practices before earliest or after latest start time |

### Tier II: AVOID (Soft Rules)
| Code | Name | Description |
|------|------|-------------|
| `a1` | Play everyone / Matchup balance | All pairs play, max diff of 1 |
| `b1` | Home/away balance | Per team, home/away diff <= 1 |
| `a2` | Home/away vs opponent | Alternate home/away when playing same team |
| `b2` | Early/late time balance | Balance 4-6 PM vs 6 PM+ games (before 4 PM excluded) |
| `c2` | Practice field balance | Distribute practice locations evenly |
| `c3` | Solo practice balance | Equal solo practice opportunities per team |
| `c4` | Practice count balance | No team has 2+ more practices than another in same league |
| `e2` | Game day balance | All teams should play on the same game days (no team sits out) |
| `f1a` | Day of week game balance (soft) | Teams differ by 2+ games on a day of week |
| `f1b` | Day of week game balance (hard threshold) | Teams differ by 3+ games on a day of week |
| `gap` | Same team gap | No back-to-back vs same opponent |

### Tier III: GOAL (Objectives)
| Code | Name | Description |
|------|------|-------------|
| `e1` | Minimum games | Each team must play at least the configured number of regular season games (scrimmages don't count) |

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
