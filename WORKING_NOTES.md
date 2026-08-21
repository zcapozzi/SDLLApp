# SDLL Web Application - Working Notes

## Summary
This is a Flask web application for managing South Durham Little League schedules, including game scheduling, field management, and team coordination.

## Current Status
Last session: Implementing Umpire Scheduling & Notification System (Phase 1-2 MVP complete).

---

## Session: August 21, 2026 - Umpire Scheduling System (MVP Foundation)

### Overview
Implemented Phase 1-2 (MVP Data Foundation) of the comprehensive Umpire Scheduling System. The system will manage SDLL umpires, partner organizations (Dynamic, Diamond), allow umpire self-signup, handle replacements, and provide emergency contact views.

### Architecture
```
sdll_users (login/auth)
    ↓ user_id FK
sdll_umpire_profiles (umpire-specific: parent contacts, eligibility)
    ↓ umpire_profile_id FK
sdll_game_umpires (game assignments)
    ↑ partner_id FK
sdll_umpire_partners (Diamond, Dynamic external providers)
    ↓
sdll_umpire_delegation_rules (% allocation by league)
sdll_umpire_delegation_overrides (keyword routing)
```

### Key Features Implemented

1. **User Roles Extended**
   - New roles: `umpire`, `treasurer`, `coach`, `parent`, `partner_contact`, `umpire_coordinator`
   - Role helper methods: `is_umpire()`, `is_treasurer()`, `can_process_payments()`, `can_manage_umpires()`

2. **UmpireProfile Model**
   - Linked to User account for unified login
   - Age calculation from birth_date
   - Parent contact info for minors (encrypted)
   - Kid-pitch eligibility flag

3. **UmpirePartner Model**
   - External umpire providers (Dynamic, Diamond)
   - Contact info, notification preferences
   - Not individuals - just the organization

4. **GameUmpire Assignment Model**
   - Links games to SDLL umpires (via profile) OR partner organizations
   - Status tracking: assigned, confirmed, cancelled
   - Pay tracking with bonus multipliers
   - Cancellation tracking for replacement workflow

5. **Delegation Rules System**
   - Percentage-based allocation per league (e.g., AAA: 33% Academy, 33% Diamond, 34% Dynamic)
   - Season-specific rules with fallback to defaults
   - Keyword overrides (e.g., "Young Umpire" → force Academy assignment)

6. **TIER I Constraint: Back-to-Back Field Continuity**
   - CRITICAL: When partner games are back-to-back at same field, MUST use same partner
   - Allows one umpire to cover multiple games
   - Enforced before percentage balancing

### Files Created

| File | Purpose |
|------|---------|
| `scripts/migrations/add_umpire_system.sql` | Database migration (7 tables) |
| `app/models/umpire_profile.py` | UmpireProfile model |
| `app/models/umpire_partner.py` | UmpirePartner model |
| `app/models/game_umpire.py` | GameUmpire assignment model |
| `app/models/umpire_delegation.py` | Delegation rules and overrides |
| `app/models/umpire_payment.py` | Payment tracking |
| `app/models/coach.py` | Coach contact model |
| `app/services/umpire_delegation_service.py` | Auto-delegation logic |
| `app/umpires/__init__.py` | Umpire management blueprint |
| `app/umpires/routes.py` | Coordinator management routes |
| `app/umpire_portal/__init__.py` | Umpire portal blueprint |
| `app/umpire_portal/routes.py` | Umpire self-service routes |
| `app/templates/umpires/*.html` | Coordinator UI templates |
| `app/templates/umpire_portal/*.html` | Umpire portal templates |
| `tests/test_umpire_profile.py` | Profile and role tests (19 tests) |
| `tests/test_umpire_delegation.py` | Delegation rule tests (15 tests) |

### Files Modified

| File | Changes |
|------|---------|
| `app/models/user.py` | Extended ROLES, added role helpers |
| `app/models/league.py` | Added umpire config fields |
| `app/models/__init__.py` | Added new model imports |
| `app/__init__.py` | Registered new blueprints |
| `tests/conftest.py` | Added league_factory, umpire fixtures |

### Test Results
```
tests/test_umpire_profile.py: 19 passed
tests/test_umpire_delegation.py: 15 passed
Total: 34 tests passing

Critical Tier I tests:
✓ test_back_to_back_same_field_same_partner
✓ test_batch_groups_field_sequences
✓ test_non_adjacent_games_can_differ
✓ test_different_fields_can_differ
```

### Database Tables Created
1. `sdll_umpire_partners` - External umpire companies
2. `sdll_umpire_profiles` - SDLL umpire data
3. `sdll_game_umpires` - Game assignments
4. `sdll_umpire_delegation_rules` - % allocation rules
5. `sdll_umpire_delegation_overrides` - Keyword routing
6. `sdll_coach_seasons` - Coach contacts per season
7. `sdll_umpire_payments` - Payment tracking

### Next Steps (Remaining Phases)

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1-2 | ✅ DONE | Models, migration, core tests |
| Phase 3 | 🔲 TODO | Umpire Portal UI (claim/release games) |
| Phase 4 | 🔲 TODO | Coordinator tools (assignments, replacements) |
| Phase 4.5 | 🔲 TODO | Delegation admin UI, batch delegation |
| Phase 5 | 🔲 TODO | Notifications (email, Telegram) |
| Phase 6 | 🔲 TODO | Payment management |

### Usage

```python
# Create umpire profile
from app.models.user import User
from app.models.umpire_profile import UmpireProfile

user = User.create_user(email='umpire@test.com', password='xxx', role='umpire')
profile = UmpireProfile(user_id=user.ID, is_kid_pitch_eligible=True)
db.session.add(profile)
db.session.commit()

# Auto-delegate a game
from app.services.umpire_delegation_service import apply_single_game_delegation
apply_single_game_delegation(game)

# Check Tier I constraint
from app.services.umpire_delegation_service import get_adjacent_partner_same_field
partner = get_adjacent_partner_same_field(game)  # Returns partner if back-to-back
```

---

## Session: August 21, 2026 - Automated Error Diagnosis System

### Overview
Implemented an automated system that exports production errors for diagnosis by Claude Code locally. When a 500 error occurs, error info is exported to local files that Claude Code can analyze with full codebase context.

### Why Local Claude Code vs API
- **Full codebase context**: All source files, CLAUDE.md, project history
- **No API costs**: Uses local Claude Code installation
- **Can read actual source files** mentioned in tracebacks
- **Understands project patterns** and conventions
- **Can directly make edits** and run tests

### Architecture

```
PRODUCTION (Railway)                    LOCAL (Windows Machine)
────────────────────                    ─────────────────────────

500 Error Occurs
      ↓
log_tier1() captures error
      ↓
Stored in sdll_app_errors ─────────────> Windows Scheduled Task
      ↓                                  polls database every 5 min
Telegram alert sent                            ↓
                                        New undiagnosed error found?
                                               ↓ YES
                                        Export to errors/pending/
                                               ↓
                                        Admin runs Claude Code:
                                        $ claude "Diagnose error 123"
                                               ↓
                                        Claude Code reads error + source
                                        Creates reproducing test
                                        Implements fix, runs tests
                                        Asks for approval, commits
```

### Files Created

| File | Purpose |
|------|---------|
| `errors/.gitignore` | Ignore error files and state files |
| `app/services/error_diagnosis_service.py` | Export errors to markdown/JSON files |
| `scripts/poll_errors.py` | Poll DB, check limits, export new errors |
| `scripts/diagnose_error.py` | Helper to list/show pending errors |
| `scripts/setup_error_poll_task.bat` | Setup Windows Scheduled Task |
| `tests/test_regressions.py` | Template for TDD regression tests |

### Safety Controls (Circuit Breaker)

| Control | Default | Purpose |
|---------|---------|---------|
| Max errors per hour | 5 | Pause if > 5 errors in 1 hour |
| Max diagnosis attempts per error | 2 | Don't keep retrying same error |
| Cool-down between diagnoses | 10 min | Prevent rapid-fire diagnoses |
| Daily diagnosis limit | 10 | Max 10 diagnoses per day |

### Error Filtering
Only diagnose errors that:
- Are Tier I (500 errors)
- Not from bots/crawlers
- Not from skip contexts (tracking, analytics)
- Not from skip paths (/health, /favicon, /static/)

### Emergency Controls

| Action | Command |
|--------|---------|
| PAUSE immediately | `echo "paused" > errors\PAUSED` |
| Resume | `del errors\PAUSED` |
| Check status | `python scripts\poll_errors.py --status` |
| Skip specific error | `echo "skip" > errors\SKIP_123` |

### TDD Workflow for Fixes
1. Read error and source files from traceback
2. Create reproducing test in `tests/test_regressions.py`
3. Run test - MUST FAIL (confirms reproduction)
4. Implement fix with minimal changes
5. Run test - MUST PASS now
6. Run full test suite - no regressions
7. Ask for approval before committing
8. Commit fix AND test together

### Usage

```bash
# One-time setup
scripts\setup_error_poll_task.bat

# Manual poll
python scripts/poll_errors.py

# Check status
python scripts/poll_errors.py --status

# List pending errors
python scripts/diagnose_error.py

# Show specific error
python scripts/diagnose_error.py 123

# Diagnose with Claude Code
claude "Diagnose and fix production error 123"
```

---

## Session: August 21, 2026 - CI/CD Testing Pipeline

### Overview
Implemented a comprehensive three-layer testing pipeline for code quality validation.

### Three-Layer Testing Strategy

| Layer | Name | Speed | Purpose | Command |
|-------|------|-------|---------|---------|
| 1 | Quick | ~5s | TDD development | `python run_tests.py --quick` |
| 2 | Integration | ~60s | Feature verification | `python run_tests.py` |
| 3 | Smoke | 5-15min | Full site coverage | `python run_tests.py --full` |

### Files Created

| File | Purpose |
|------|---------|
| `CI_CD.md` | Comprehensive documentation for testing pipeline |
| `tests/inventory.yaml` | Feature catalog with all testable features and expected behaviors |
| `tests/test_fields.py` | Functional tests for field management |
| `tests/test_games.py` | Functional tests for game management |
| `tests/test_teams.py` | Functional tests for team management |
| `tests/test_scheduler.py` | Functional tests for scheduler and general routing |
| `scripts/smoke_test.py` | Smoke test runner that exercises inventory.yaml |
| `scripts/pre_push_check.py` | Pre-push validation script |
| `.githooks/pre-push` | Git hook to run validation before push |

### Files Modified

| File | Changes |
|------|---------|
| `tests/conftest.py` | Added factory fixtures (field_factory, team_factory, game_factory, field_slot_factory, scheduler_client, admin_client) |
| `run_tests.py` | Enhanced with --quick, --full, --cov, -v, -x, --last-failed options |

### Key Features

**Factory Fixtures** (in `conftest.py`):
- `field_factory(name, **kwargs)` - Create test fields with auto-cleanup
- `team_factory(name, **kwargs)` - Create test teams with auto-cleanup
- `game_factory(home_team, away_team, field)` - Create test games
- `scheduler_client` - Authenticated client with scheduler role
- `admin_client` - Authenticated client with admin role

**Test Markers**:
- `@pytest.mark.quick` - Mark tests that don't need database (Layer 1)

**Pre-Push Hook Setup**:
```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

### Verification Results
- Layer 1 (Quick tests): 23 passed in 0.28s
- Layer 2 (Integration): Requires database connection (expected to fail without test DB)

### Usage

```bash
# Quick TDD tests (no DB needed)
python run_tests.py --quick

# Integration tests (needs DB)
python run_tests.py

# Specific test file
python run_tests.py auth
python run_tests.py fields games

# Full smoke tests
python run_tests.py --full

# Pre-push validation
python scripts/pre_push_check.py
```

---

## Session: August 20, 2026 - Tier I/Tier II Error Reporting System

### Overview
Implemented a comprehensive error handling system that ensures users are never blocked by errors while keeping admins informed of issues.

### Tier System

| Tier | Name | Behavior | Examples |
|------|------|----------|----------|
| **I** | Critical | Immediate Telegram alert | Database connection, auth failures, 500 errors |
| **II** | Digest | Periodic email summary | Analytics tracking, minor validation |

### Key Principles
1. **Never crash user requests**: All error handling is wrapped in try/except with graceful fallbacks
2. **Always log**: Errors go to stderr (Railway) AND database (for reporting)
3. **Separate tracking from content**: Tracking failures never prevent page loads
4. **Tiered alerting**: Critical issues get immediate attention; minor issues are batched

### Implementation

#### 1. Database Model (`app/models/app_error.py`)
- Stores: tier, context, error_type, error_message, traceback
- Request context: method, path, user_agent, user_id
- Status tracking: notified, resolved, resolved_by
- Error hash for grouping similar errors

#### 2. Error Utilities (`app/utils/errors.py`)
- `log_error(context, error, request, tier)`: Main logging function
- `log_tier1()` / `log_tier2()`: Force-log at specific tier
- `safe_tracking` decorator: Wraps tracking functions to fail silently
- `safe_db_operation` context manager: Wraps DB operations with rollback
- `register_global_handler(app)`: Flask error handler registration
- `get_error_digest_html()`: Generates HTML for digest emails

#### 3. Tier I Alerts
- Uses existing `send_message.py` script for Telegram alerts
- Runs asynchronously (subprocess) to not block requests
- Includes: context, error type, message snippet, request info, timestamp

#### 4. Admin Interface (`/admin/errors`)
- Error list with tier/resolved filters
- Error detail view with full traceback
- Mark as resolved functionality
- Digest view with summary statistics

#### 5. Digest Email Service (`app/services/error_digest_service.py`)
- `send_error_digest(hours=24)`: Sends summary email to admins
- Uses existing GmailService for sending
- Marks errors as notified after sending

### Files Created

| File | Description |
|------|-------------|
| `app/models/app_error.py` | AppError model |
| `app/templates/errors/500.html` | User-friendly error page |
| `app/templates/admin/errors.html` | Error list admin page |
| `app/templates/admin/error_detail.html` | Error detail admin page |
| `app/templates/admin/error_digest.html` | Digest summary page |
| `app/services/error_digest_service.py` | Digest email service |
| `scripts/add_app_errors_table.sql` | Database migration |

### Files Modified

| File | Changes |
|------|---------|
| `app/utils/errors.py` | Complete rewrite with Tier I/II support |
| `app/__init__.py` | Updated global error handler |
| `app/main/routes.py` | Added admin error routes |

### SQL Migration Required
Run `scripts/add_app_errors_table.sql` on the database to create:
- `sdll_app_errors` table

### Tier I Contexts (Auto-Critical)
- `database_connection`
- `authentication_failure`
- `payment_processing`
- `schedule_corruption`
- `data_integrity`
- `security_violation`

All other contexts default to Tier II (digest).

### Integration with Existing Code
The `app/public/routes.py` already uses `log_error()` for tracking failures. These will now:
1. Be stored in the database
2. Appear in the admin error digest
3. Never crash the public page

---

## Session: August 20, 2026 - Analytics & Ad System

### Overview
Implemented first-party analytics and self-hosted ad inventory for public schedule pages. No third-party tracking, no PII collection, fully privacy-respecting.

### Privacy Approach (see privacyApproach.md)
- **First-party only**: All data stays in our database
- **No PII**: IP addresses are hashed, session IDs are random UUIDs
- **No cross-site tracking**: Session cookies are same-site only
- **Transparent**: Public privacy page explains our approach

### Database Models (`app/models/analytics.py`)

1. **PageView**: Tracks anonymous page views
   - Hashed IP, device type, viewport, time on page
   - Session ID via anonymous cookie

2. **Ad**: Self-hosted ad/sponsor content
   - Headline, description, image, click URL
   - Optional targeting by league
   - Scheduling (start/end dates)

3. **AdImpression**: Tracks ad displays
   - IAB viewability (50% visible for 1+ sec)
   - Device type, viewport

4. **AdClick**: Tracks validated clicks
   - Time-to-click validation (bot detection)
   - Click position validation
   - Nonce token to prevent replays

### Implementation

**Server-side (routes.py)**:
- `_get_or_create_session_id()`: Anonymous session cookie management
- `/s/<token>`: Logs PageView, gets active Ad, logs AdImpression
- `/s/privacy`: Privacy policy page
- `/s/beacon`: Receives JS beacon data (viewport, time on page)
- `/s/ad/viewability`: Receives viewability data
- `/s/ad/click/<token>`: Validates and logs clicks, redirects to destination

**Client-side (team_schedule.html)**:
- Beacon on page unload (time on page, viewport)
- Intersection Observer for ad viewability
- Click tracking with validation params

### Files Created/Modified

| File | Action |
|------|--------|
| `privacyApproach.md` | CREATE - Privacy principles document |
| `app/models/analytics.py` | CREATE - PageView, Ad, AdImpression, AdClick models |
| `app/templates/public/privacy.html` | CREATE - Public privacy page |
| `app/templates/public/team_schedule.html` | MODIFY - Add ad block and tracking JS |
| `app/public/routes.py` | MODIFY - Add tracking and ad routes |
| `app/models/__init__.py` | MODIFY - Add analytics imports |
| `scripts/add_analytics_tables.sql` | CREATE - Database migration |

### SQL Migration Required
Run `scripts/add_analytics_tables.sql` on the database to create:
- `sdll_page_views`
- `sdll_ads`
- `sdll_ad_impressions`
- `sdll_ad_clicks`

---

## Session: August 20, 2026 - Practice Pairings Feature

### Overview
Added a feature that allows two teams to be permanently paired for shared practices on a specific day of the week. When both teams are scheduled to practice on that day, they automatically share a field.

### Use Case Example
SB Tee Ball Team 1 and SB Tee Ball Team 2 always share a field on Mondays. Both coaches have agreed to do joint practices.

### Requirements
1. **Day-specific**: Pairing only applies on the specified day of week (Monday pairing doesn't affect Thursday practices)
2. **Override field availability**: Paired teams always share, regardless of other field constraints
3. **Process first**: Handle paired practices before regular practice assignment
4. **Skip error detection**: Paired teams exempt from shared-field violations (f1c, f2)
5. **CRUD interface**: Add and delete pairings via dedicated page

### Implementation

#### 1. Database Model (`app/models/practice_pairing.py`)
- New `PracticePairing` model with columns: ID, year, is_spring, team_one_id, team_two_id, day_of_week, notes, active
- Class methods: `get_by_season()`, `get_pairings_for_day()`, `get_paired_team_ids()`, `get_pairing_pairs()`, `add_pairing()`, `are_teams_paired()`
- Relationships to `TeamSeason` for both teams

#### 2. Route (`app/seasons/routes.py`)
- New route: `/<year>/<is_spring>/practice-pairings`
- Actions: `add_pairing`, `delete_pairing`
- Validation: prevents pairing a team with itself, prevents duplicates

#### 3. Template (`app/templates/seasons/practice_pairings.html`)
- Form to add pairings: two team dropdowns (grouped by league), day of week dropdown, optional notes
- Table listing current pairings with remove buttons
- Info cards explaining the feature

#### 4. Scheduler Integration (`app/utils/scheduler.py`)

**Initialization:**
- Load practice pairings: `_practice_pairings`, `_paired_team_ids`, `_paired_team_pairs`
- Track assigned paired practices: `_paired_practice_assigned`

**Paired Practice Scheduling:**
- New method: `_schedule_paired_practices_for_date()`
- Called before regular practice assignment in `_schedule_practices_round_robin()`
- For each pairing on the current day:
  - Check if both teams need practice today
  - Find a field with capacity >= 2
  - Assign both teams to the same field/time
  - Mark both teams as having activity for the day

**Violation Exemptions:**
- **f1c (Cross-league practice sharing)**: Modified `_check_practice_field_capacity()` to skip violation if exactly 2 teams are sharing and they are in a pairing
- **f2 (Unnecessary field sharing)**: Modified `_check_unnecessary_sharing()` to skip violation if all teams sharing a field are paired together

#### 5. Navigation
- Added "Practice Pairings" link to Schedule Settings page
- Added "Practice Pairings" link to Blackout Dates page

### Files Created/Modified

| File | Action |
|------|--------|
| `app/models/practice_pairing.py` | CREATE |
| `app/models/__init__.py` | MODIFY - add import |
| `app/templates/seasons/practice_pairings.html` | CREATE |
| `app/seasons/routes.py` | MODIFY - add route |
| `app/utils/scheduler.py` | MODIFY - add pairing logic |
| `app/templates/seasons/schedule_settings.html` | MODIFY - add nav link |
| `app/templates/seasons/blackout_dates.html` | MODIFY - add nav link |

### Scheduler Flow (Updated)
```
For each practice date:
  1. Check day of week
  2. Get pairings that apply to this day
  3. For each pairing where BOTH teams need practice:
     - Assign them together to a shared field (FIRST)
     - Mark both as practiced
  4. Continue with regular practice assignment for remaining teams
```

### Edge Cases
| Case | Handling |
|------|----------|
| Only one team needs practice that day | Skip pairing, normal assignment |
| No fields available | Report as regular field shortage |
| Team in multiple pairings same day | Process each pairing separately |
| Pairing deleted mid-season | Only affects future schedule generations |
| Cross-league pairing | Allowed - pairings override f1c |

---

## Session: August 19, 2026 - Expected Practice Count Rule (c5)

### Problem
SB Minors wasn't getting any practices scheduled until 9/8, missing the first week (9/1-9/7 except 9/4-9/7 blackouts). Investigation revealed:

1. **League processing order**: Leagues are sorted by `(len(game_days), league_name)`, so SB Minors (2 game days) is processed after SB Tee Ball (1 game day).
2. **Slot consumption**: By the time SB Minors is processed, other leagues (SB Tee Ball, BB AA, BB A, BB Rookie) have already taken the softball-compatible slots on 9/1 and 9/3.
3. **Result**: SB Minors teams only got 6 practices when they should have had 10.

### Solution
Added Tier II rule `c5` (Expected Practice Count) to track and flag practice shortfalls:

**Expected practices per team = A + B where:**
- **A** = practice days from `first_practice_date` to `regular_season_end_date` (excluding blackouts)
- **B** = game days before `opening_day` (used as practices during pre-season)

**Actual practices** = division practices (`is_league_practice`) + scheduled individual practices

If Actual < Expected, a soft violation is reported for that team.

### Example (SB Minors)
- Practice days (Saturdays): 6
- Pre-opening game days (Tue/Thu before 9/15): 4
- Expected: 10 practices
- Actual: 6 practices per team
- Shortfall: 4 (flagged as c5 violation)

### Files Modified
- `app/utils/scheduler.py`: Added `_check_expected_practice_count()` method
- `howToSchedule.md`: Documented rule c5

### Next Steps
The c5 rule provides visibility into the problem. To fix it, the scheduler needs to:
1. Reserve slots proportionally for each league based on their needs
2. Or process leagues in round-robin fashion to ensure fair slot access
3. Or prioritize leagues with limited field options (e.g., softball leagues)

---

## Session: August 19, 2026 - Late Game Balance Between Teams (b2 Fix)

### Problem
The scheduler was fully deterministic - teams sorted by `team_ID` consistently got the same time slots:
- First eligible matchup always got the first available slot (earliest time)
- Teams with lower IDs got early slots, higher IDs got late slots
- `late_counts` were tracked but **never used** during slot assignment

**Example:** BB Juniors - Team Morris: 0 late games. Team Crispell: 4 late games.

### Understanding the Requirement
The goal is NOT to balance early/late WITHIN each team. The goal is to ensure all teams in a league have roughly the SAME NUMBER of late games. Teams should get early slots whenever possible, but when late slots must be used, they should be distributed evenly among all teams.

### Solution
1. **Updated validation** (`_check_time_balance`): Now checks if all teams have similar late game counts, flagging teams that are at the min or max of the range when diff > 2.

2. **Updated scheduling in 3 locations** (key insight: preserve slot order, just change which matchups get which slots):
   - **`_find_complete_round`**: After finding valid matchups, identifies which slot positions are late, then assigns matchups so teams with fewer late games get those late slot positions.
   - **Greedy slot assignment (2 locations)**: Process slots in original order. For each slot, pick the best matchup: for late slots prefer teams with fewer late games; for early slots prefer teams with more late games.

3. **Key principle**: The total number of late games is unchanged - we're just redistributing WHICH teams get them.

### Results
- **b2 violations reduced from 24 to 0** ✓
- **Same late game totals**: BB AA still has 24 early, 8 late (unchanged)
- **Better distribution**: BB AA range 1-3 (was 0-4), all teams within 2 games of each other

### Files Modified
- `app/utils/scheduler.py`:
  - Updated `_check_time_balance()` validation to check between-team balance
  - Added `_get_late_need_score()` helper method
  - Modified `_find_complete_round()` to accept `late_counts` and assign slots with balance awareness
  - Modified greedy slot assignment (2 locations) with improved sorting
  - Modified catch-up pass

---

---

## Session: August 19, 2026 - Division Practices in All Views

### Problem
Division practices (manually created via "Add Division-Practice" with `is_league_practice=True`) were not showing up in:
- Schedule review page
- Calendar view
- Day view

This was because these views pulled data from the `ScheduleProposal` which doesn't include manually-created league practices.

### Solution
Modified all relevant views to also query `sdll_games` for records where `is_league_practice=True` and merge them with the proposal data.

### Changes Made

1. **Scheduler Review** (`app/scheduler/routes.py`):
   - Added query for league practices from database
   - Converted them to proposal-style dict format
   - Added to the games list being displayed

2. **Calendar View** (`app/games/routes.py:calendar`):
   - Added query for league practices when a proposal exists
   - Converted to proposal-style dict and added to `proposed_games_by_date`
   - Added `is_league_practice` attribute to ProposedGame objects

3. **Day View** (`app/games/routes.py:day_view`):
   - Added query for league practices on the viewed date
   - Created ProposedGame objects with `display_type='div-practice'`

4. **CSS Styling**:
   - Added `.game-card.div-practice` (pink: #fce4ec, border: #c2185b) to calendar.html
   - Added `.game-slot.div-practice` (same colors) to day_view.html

### Visual Distinction
- Regular practices: Purple background
- Division practices: Pink background with "div-practice" badge and "(all teams)" label

### Commits
- `a5959c3` - Include division practices in schedule review and calendar views
- `43c9c76` - Add admin preview of proposed schedules on public team pages

---

## Session: August 19, 2026 - Public Schedule View with Proposals

### Overview
Enhanced the public team schedule view (`/s/<token>`) to show proposed schedules to admins when the schedule hasn't been locked yet. Non-admins see a "schedule not released" message.

### Changes Made

1. **Public Routes** (`app/public/routes.py`):
   - Added check for schedule locked status using `LeagueSeason.is_season_locked()`
   - Added check for `ScheduleProposal.get_for_season()`
   - For unlocked schedules with a proposal:
     - Admins (`current_user.can_edit_schedule()`) see the proposed schedule
     - Non-admins see a "Schedule Not Yet Released" message
   - Created `ProposalGameWrapper` class to make proposal dicts behave like Game objects
   - Created `_build_game_object_from_proposal()` helper for converting proposal data

2. **Public Template** (`app/templates/public/team_schedule.html`):
   - Added "Proposed Schedule (Admin View)" badge in header when viewing proposals
   - Added "Schedule Not Yet Released" message block for non-admins
   - Added "Div. Practice" badge for league practices (`is_league_practice=True`)

### Template Changes
- Both upcoming and past game sections now distinguish between:
  - `Div. Practice` - League-wide practices (`game.game_type == 'practice' and game.is_league_practice`)
  - `Practice` - Individual team practices (`game.game_type == 'practice'`)

### Behavior
| Schedule Status | User Type | Shows |
|-----------------|-----------|-------|
| Locked | Anyone | Saved games from database |
| Unlocked + No proposal | Anyone | Empty schedule |
| Unlocked + Has proposal | Admin | Proposed schedule with "Admin View" badge |
| Unlocked + Has proposal | Non-admin | "Schedule Not Yet Released" message |

### Files Modified
- `app/public/routes.py` - Added proposal display logic
- `app/templates/public/team_schedule.html` - Added badges and messages

---

## Session: August 19, 2026 - Rule f2 Implementation & Validation Fixes

### Overview
Implemented Rule f2 (Unnecessary Field Sharing) as a Tier II rule. Teams should prefer solo practice at any eligible field over sharing their preferred field with another team.

### Changes Made

1. **Assignment Logic (Two-Pass Approach)**:
   - First pass: Look for completely EMPTY fields (no other teams)
   - Second pass: If no empty fields, allow sharing within same league only
   - Teams are processed in order of practice count (fewest first) for balance

2. **f2 Validation Rule**:
   - Detects when teams share a field while another eligible field was empty at the same time
   - Checks fields by (day_of_week, hour, minute) to match slot allocation logic
   - Considers all activities across ALL leagues when checking for "empty"
   - Uses proper duration (game or practice) for overlap detection
   - Verifies field availability on specific date (start date, blackouts)

3. **Performance Optimizations Applied Earlier**:
   - Strategy 1: Cache League objects (eliminate N+1 queries)
   - Strategy 2: Binary search for field time availability checks
   - Result: 21% faster generation (2.44s → 1.92s)

4. **Copy Schedule Link Button**:
   - Added "Copy Sched Link" button on manage teams page
   - Copies public schedule URL to clipboard
   - Reduced table font size for better fit

### Test Results (Fall 2026)
```
Generation: ~6 seconds
Total violations: 71
f2 violations: 0 (correctly detecting no unnecessary sharing)
```

### Commits
- `ff80a31` - Copy Sched Link button on manage teams page
- `2de2864` - Fix f2 validation to accurately detect unnecessary sharing

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
