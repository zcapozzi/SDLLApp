# SDLL Web Application - Working Notes

## Summary
This is a Flask web application for managing South Durham Little League schedules, including game scheduling, field management, and team coordination.

## Current Status
Last session: Added game start time recording feature to public team schedule pages. Users can record first pitch time for games on the day of the game. Added `umpire_was_unassigned` field for games mistakenly assigned to partners.

---

## Session: August 26, 2026 (Continued) - Game Start Time Recording

### Overview
Added a feature to public team schedule pages allowing coaches/parents to record the actual first pitch time. This is used to determine when the "no new inning" time window applies.

### Features Implemented

1. **Three-dot Menu**: Game cards on team schedule show a three-dot menu for eligible games
2. **Inline Form**: Mobile-first design with time input (no modal)
3. **Session Tracking**: Records user ID if logged in, or session cookie for anonymous users
4. **Testing Mode**: Add `?allowStartTimeRecord=1` to URL to enable on non-game days

### Files Created

| File | Purpose |
|------|---------|
| `app/models/game_start_record.py` | GameStartRecord model |
| `scripts/migrations/add_game_start_records.sql` | Database migration |

### Files Modified

| File | Changes |
|------|---------|
| `app/models/__init__.py` | Import GameStartRecord |
| `app/public/routes.py` | Added `record_game_start` and `get_game_start` API endpoints |
| `app/templates/public/team_schedule.html` | Added three-dot menu, inline form, CSS, and JavaScript |

### Database Schema

```sql
CREATE TABLE sdll_game_start_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id INT NOT NULL,
    start_time DATETIME NOT NULL,
    user_id INT DEFAULT NULL,
    session_id VARCHAR(64) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_game_id (game_id),
    INDEX idx_session_id (session_id),
    CONSTRAINT fk_game_start_game FOREIGN KEY (game_id) REFERENCES sdll_games(ID) ON DELETE CASCADE,
    CONSTRAINT fk_game_start_user FOREIGN KEY (user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL
);
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/s/api/game-start` | POST | Record/update first pitch time |
| `/s/api/game-start/<game_id>` | GET | Get existing start record for game |

### UI Features

- Three-dot menu only appears for games on day of game (non-practice)
- Time input defaults to current time
- Previously recorded time is displayed as "First pitch: X:XX PM"
- Success message after saving
- Testing mode bypasses date check

### Migration Required
Run `scripts/migrations/add_game_start_records.sql` after deployment.

---

## Session: August 26, 2026 - Umpire Was Unassigned Field

### Overview
Added `umpire_was_unassigned` field to track games that were assigned to a partner in error. These games remain on the partner's schedule with an indicator but are excluded from delegation report counts.

### Files Modified

| File | Changes |
|------|---------|
| `app/models/game.py` | Added `umpire_was_unassigned` column |
| `app/umpires/routes.py` | Added `api_mark_no_umpire_required` endpoint; updated delegation report to exclude unassigned games |
| `app/templates/umpires/calendar.html` | Added "No Umpire Required" context menu option |
| `app/templates/public/partner_schedule.html` | Show "Umpire(s) not required" badge for unassigned games |

### Migration Required
Run `scripts/migrations/add_umpire_was_unassigned.sql` after deployment.

---

## Session: August 26, 2026 - Delegation Proposal Allocation Preview

### Overview
Enhanced the delegation proposal review page to show league context and dynamic allocation previews, allowing umpire coordinators to see how their assignment changes affect allocation percentages in real-time.

### Changes Made

**Route Enhancement** (`app/umpires/routes.py`)
- Added allocation data to `delegation_proposal_review` route:
  - `current_stats`: Counts of existing delegated games by league/partner (games with `umpire_override` set)
  - `proposal_counts`: Counts in the current proposal by league/partner
  - `allocation_rules`: Target percentages from delegation rules by league/partner
  - `leagues_in_proposal`: Sorted list of leagues in the proposal
  - `partners_json`: Partner info (id, code, name) for JavaScript

**Template Enhancement** (`app/templates/umpires/delegation_proposal_review.html`)
- Added league column to game tables with `data-league` attribute for JavaScript
- Added "Game Allocation by League" section showing:
  - Current: games already delegated this season
  - + Proposal: games in this proposal
  - = Projected: total after accepting
  - Target %: from delegation rules
  - Current %: current allocation percentage
  - Projected %: allocation percentage if proposal accepted
  - Deviation: difference from target (color-coded)
- JavaScript for dynamic updates:
  - `updateAllocationTable(league)`: Calculates and displays stats for one league
  - `updateAllAllocationTables()`: Updates all league tables
  - `recalculateProposalCounts()`: Recalculates from dropdown selections when changed
  - Color coding: green (<5%), yellow (5-10%), red (>10%)

### Bug Fixes in Same Session

1. **Card view filter not working** (manage games page)
   - Issue: Inline `style="display: flex;"` on `.game-row` overrode CSS `display: none`
   - Fix: Moved display styles to CSS, added `!important` to filter rules

2. **Jump to date going to week view**
   - Issue: `jumpToDate()` set `week` parameter instead of navigating to day view
   - Fix: Redirect to `games.day_view` route with selected date

3. **Tier II violation display TypeError**
   - Issue: Template used `violation.target` but service returns `violation.target_pct`
   - Fix: Updated template to use correct field names

### Test Results
- All 12 delegation_proposal tests pass
- All tests pass after changes

---

## Session: August 26, 2026 - Remove Deprecated Location Column

### Overview
Removed the deprecated `location` VARCHAR column from `sdll_games` table. Games now exclusively use `field_id` (FK to `sdll_fields`) for field references, eliminating confusion and ensuring referential integrity.

### Changes Made

**Phase 1: Model Updates**
- Removed `location` column definition from `app/models/game.py`
- Updated `__repr__` to use `field_name` property
- Simplified `field` property (removed location string fallback)
- Updated `field_name` property (removed location fallback)
- Updated `copy_to_new_season` to not copy location
- Updated `clear_slot_assignments` to not clear location

**Phase 2: Service Updates**
- `delegation_proposal_service.py`: Changed ORDER BY from location to field_id, updated back-to-back detection to use field_id
- `umpire_delegation_service.py`: Updated is_back_to_back_same_field and get_adjacent_partner_same_field to use field_id
- `game_changes.py`: Removed location string assignments in move_game
- `notification_templates.py`: Use game.field_name instead of game.location
- `weekly_digest_service.py`: Use game.field_name

**Phase 3: Routes Updates**
- `games/routes.py`: ~20 changes to use field_id/field_name instead of location
- `scheduler/routes.py`: Look up field_id from field_name when creating games
- `umpires/routes.py`: Use field_id for ordering, field_name for caching
- `public/routes.py`: Use game.field_name for display
- `main/routes.py`: Use game.field_name for email templates
- `reports/routes.py`: Use game.field_name

**Phase 4: Scheduler Utility**
- `utils/scheduler.py`: Updated all fallback patterns from `elif hasattr(p, 'location')` to `elif hasattr(p, 'field_id')`

**Phase 5: Templates**
- `umpires/delegation_proposal_review.html`: Use game.field_name
- `scheduler/review.html`: Use game.field_name without fallback

**Phase 6: Tests**
- `conftest.py`: game_factory now uses field_id instead of location
- `test_games.py`: Updated to use field_id in form data and assertions
- `test_delegation_proposal.py`: MockGame classes now use field_id
- `test_umpire_delegation.py`: All game creation uses field_id

**Phase 7: Migration Script**
- Created `scripts/migrations/remove_games_location.sql`
- Migrates any remaining games with location but no field_id
- Then drops the location column

### Test Results
- All 12 delegation_proposal tests pass
- All 15 umpire_delegation tests pass
- All 26 games tests pass

### Migration Required
Run `scripts/migrations/remove_games_location.sql` against production database after deployment.

---

## Session: August 26, 2026 - Delegation Proposal System

### Overview
Implemented a complete workflow for reviewing and accepting umpire delegations for new games. The system generates proposals that apply delegation rules to undelegated games, validates Tier I (back-to-back) and Tier II (allocation percentage) constraints, and allows admins to review, modify, and accept proposals.

### Features Implemented

1. **Proposal Generation**: Generate proposals for undelegated games based on delegation rules
2. **Back-to-back Detection**: Automatically groups games at the same field within 30 minutes into sequences
3. **Tier I Validation**: Enforces that back-to-back games use the same partner (hard constraint)
4. **Tier II Validation**: Warns if allocations deviate >10% from target percentages (soft constraint)
5. **Interactive Review**: View games grouped by partner, modify individual assignments
6. **Sequence Updates**: Changing one game in a sequence updates all games in that sequence
7. **Accept/Reject Workflow**: Accept updates all games, reject discards the proposal

### Files Created

| File | Purpose |
|------|---------|
| `scripts/migrations/add_delegation_proposals.sql` | Database migration for proposal tables |
| `app/models/delegation_proposal.py` | DelegationProposal and DelegationProposalGame models |
| `app/services/delegation_proposal_service.py` | Generation, validation, acceptance logic |
| `app/templates/umpires/delegation_proposals.html` | List proposals with status/history |
| `app/templates/umpires/delegation_proposal_review.html` | Review/edit proposal assignments |
| `tests/test_delegation_proposal.py` | 12 comprehensive tests for back-to-back detection, Tier I/II validation |

### Files Modified

| File | Changes |
|------|---------|
| `app/umpires/routes.py` | Added 6 proposal routes (list, generate, review, accept, reject, update-game API) |
| `app/templates/umpires/delegation.html` | Added link to Delegation Proposals |
| `app/models/__init__.py` | Import DelegationProposal, DelegationProposalGame models |

### Database Schema

```sql
CREATE TABLE `sdll_delegation_proposals` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `created_by` BIGINT DEFAULT NULL,
    `year` INT NOT NULL,
    `is_spring` SMALLINT NOT NULL,
    `status` ENUM('pending', 'accepted', 'rejected') NOT NULL DEFAULT 'pending',
    `accepted_at` DATETIME DEFAULT NULL,
    `accepted_by` BIGINT DEFAULT NULL,
    `game_count` INT NOT NULL DEFAULT 0,
    `tier1_violations` INT NOT NULL DEFAULT 0,
    `tier2_violations` INT NOT NULL DEFAULT 0,
    `summary_json` TEXT,
    PRIMARY KEY (`id`)
);

CREATE TABLE `sdll_delegation_proposal_games` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `proposal_id` INT NOT NULL,
    `game_id` BIGINT NOT NULL,
    `suggested_partner_id` INT NOT NULL,
    `final_partner_id` INT DEFAULT NULL,
    `is_back_to_back` TINYINT DEFAULT 0,
    `sequence_id` INT DEFAULT NULL,
    PRIMARY KEY (`id`),
    FOREIGN KEY (`proposal_id`) REFERENCES `sdll_delegation_proposals`(`id`) ON DELETE CASCADE
);
```

### Key Algorithms

**Back-to-back Detection**: Games are back-to-back if:
1. Same field (location)
2. Second game starts within 30 min of first game's expected end (game duration = 2 hours)

**Tier I Validation**: All games in a sequence must have the same assigned partner (final_partner_id or suggested_partner_id).

**Tier II Validation**: For each league with delegation rules, compares:
- Target percentages from allocation rules
- Actual percentages after proposal is applied
- Flags partners with deviation > 10%

### Routes Added

| Route | Method | Purpose |
|-------|--------|---------|
| `/umpires/delegation/proposals` | GET | List proposals for current season |
| `/umpires/delegation/proposals/<year>/<is_spring>` | GET | List proposals for specific season |
| `/umpires/delegation/proposals/generate` | POST | Generate new proposal |
| `/umpires/delegation/proposals/<id>` | GET | Review/view specific proposal |
| `/umpires/delegation/proposals/<id>/accept` | POST | Accept proposal and update games |
| `/umpires/delegation/proposals/<id>/reject` | POST | Reject proposal |
| `/api/delegation-proposals/<id>/update-game` | POST | Update game assignment (JSON) |

### Testing

All 27 delegation tests pass (12 proposal tests + 15 allocation tests):
- Back-to-back detection (5 tests)
- Tier I validation (2 tests)
- Tier II validation (2 tests)
- Proposal acceptance (2 tests)
- Game assignment updates (1 test)

### To Deploy

1. Run migration: `mysql -u root -p sdll_database < scripts/migrations/add_delegation_proposals.sql`
2. Access at: `/umpires/delegation/proposals`

---

## Session: August 25, 2026 - Weekly Umpire Partner Digest System

### Overview
Implemented a comprehensive weekly digest system that generates and sends upcoming game schedules to umpire partner organizations (Diamond, Dynamic, SDLL Academy). The system auto-generates drafts for review, allows admin approval before sending, tracks history, and sends reminders if digests aren't sent by Monday morning.

### Features Implemented

1. **Auto-Generate Drafts**: Cron job runs Sunday 6pm ET to create draft digests for each partner
2. **Review Workflow**: Admin reviews/edits before sending (configurable per partner)
3. **Auto-Send Mode**: Optional per-partner setting to skip review and send immediately
4. **Partner Targeting**: Uses `umpire_override` field on games (DIA, DYN, SDL)
5. **Reminder System**: Monday 8am ET reminder if drafts aren't sent (only in review mode)
6. **History Tracking**: Full history of sent/skipped digests
7. **HTML Format**: Styled email matching existing umpire email format

### Files Created

| File | Purpose |
|------|---------|
| `scripts/migrations/add_weekly_digests.sql` | Database migration (table + column) |
| `app/models/weekly_digest.py` | WeeklyDigest model with status workflow |
| `app/services/weekly_digest_service.py` | Generation, rendering, sending logic |
| `app/templates/umpires/weekly_digests.html` | List view with status badges |
| `app/templates/umpires/digest_preview.html` | Preview/edit/send page |
| `app/templates/umpires/digest_settings.html` | Auto-send configuration per partner |

### Files Modified

| File | Changes |
|------|---------|
| `app/umpires/routes.py` | Added 6 digest routes (list, preview, action, generate, settings) |
| `app/main/routes.py` | Added 2 cron endpoints (generate, reminders) |
| `app/templates/base.html` | Added "Weekly Digests" link to Umpires dropdown |
| `app/models/__init__.py` | Import WeeklyDigest model |
| `app/models/umpire_partner.py` | Added `auto_send_digest` column |

### Database Schema

```sql
CREATE TABLE `sdll_weekly_digests` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `partner_code` VARCHAR(10) NOT NULL,  -- 'DIA', 'DYN', 'SDL'
  `partner_name` VARCHAR(100) NOT NULL,
  `week_start` DATE NOT NULL,  -- Monday of target week
  `year` INT NOT NULL,
  `is_spring` SMALLINT NOT NULL,
  `recipient_emails` TEXT NOT NULL,  -- JSON array
  `subject` VARCHAR(255) NOT NULL,
  `body_html` TEXT NOT NULL,
  `game_count` INT NOT NULL DEFAULT 0,
  `status` ENUM('draft', 'ready', 'sent', 'skipped') NOT NULL DEFAULT 'draft',
  `reviewed_by` BIGINT DEFAULT NULL,
  `reviewed_at` DATETIME DEFAULT NULL,
  `sent_at` DATETIME DEFAULT NULL,
  `sent_by` BIGINT DEFAULT NULL,
  `reminder_sent` TINYINT DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_partner_week` (`partner_code`, `week_start`)
);

ALTER TABLE sdll_umpire_partners ADD COLUMN auto_send_digest TINYINT DEFAULT 0;
```

### Routes Added

| Route | Method | Description |
|-------|--------|-------------|
| `/umpires/<year>/<is_spring>/digests` | GET | List all digests for season |
| `/umpires/<year>/<is_spring>/digests/<id>` | GET | Preview specific digest |
| `/umpires/<year>/<is_spring>/digests/<id>` | POST | Actions: approve, send, skip, regenerate |
| `/umpires/<year>/<is_spring>/digests/generate` | POST | Manually generate for week |
| `/umpires/<year>/<is_spring>/digests/settings` | GET/POST | Configure auto-send per partner |
| `/cron/generate-weekly-digests` | GET | Auto-generate (Sunday 6pm ET) |
| `/cron/digest-reminders` | GET | Send reminders (Monday 8am ET) |

### Status Workflow

```
draft -> ready (admin approval)
draft -> skipped (no games or admin decision)
ready -> sent (email sent successfully)
ready -> draft (admin wants to re-edit)
```

### Cron Setup

Set up in cron-job.org:
```
# Sunday 6pm ET (23:00 UTC)
0 23 * * 0 https://your-app.railway.app/cron/generate-weekly-digests?token=YOUR_CRON_SECRET

# Monday 8am ET (13:00 UTC)
0 13 * * 1 https://your-app.railway.app/cron/digest-reminders?token=YOUR_CRON_SECRET
```

### Access Control

Same as Email Coaches feature:
- `admin`
- `scheduler`
- `SBPlayerAgent`
- `BBPlayerAgent`

### Usage

1. Navigate to Umpires > Weekly Digests
2. Click "Generate This Week" to create drafts
3. Review each partner's digest by clicking "Preview"
4. Click "Send Now" to send email, or "Skip" if not needed
5. For auto-send partners, configure in Settings

### Production Migration Required

Run `scripts/migrations/add_weekly_digests.sql` on Railway MySQL.

---

## Session: August 25, 2026 - Email Blast Feature (Coach + Generic)

### Overview
Implemented a comprehensive email blast system with a coach-focused entry point. Located under "Email Coaches" in the Schedule menu. Supports three send modes, rich text editing, scheduling, and manual recipient entry.

### Features Implemented

1. **League Selection**: Multi-select checkboxes for current season leagues with select all/deselect all controls
2. **Send Modes**:
   - CC (default): All recipients in one email, visible to each other
   - BCC: All recipients in one email, hidden from each other
   - Individual (per team): One email per team with all coaches CC'd together
3. **Reply-To**: Sender's email address (auto-set)
4. **Rich Text**: Quill.js editor for links and formatting
5. **Scheduling**: Optional future send date with Gmail-style split button
6. **Recipient Preview**: Live count with option to expand and see actual emails
7. **Manual Entry**: Optional field to add additional email addresses
8. **One-Time Send**: No retry - notify sender + admins on failure

### Access Control
Users with ANY of these roles can access:
- `admin`
- `scheduler`
- `SBPlayerAgent`
- `BBPlayerAgent`

### Files Created

| File | Purpose |
|------|---------|
| `scripts/migrations/add_scheduled_email.sql` | Database migration |
| `app/models/scheduled_email.py` | ScheduledEmail model with JSON properties for recipients |
| `app/services/email_blast_service.py` | Recipient gathering, send logic, failure notifications |
| `app/templates/scheduler/email_coaches.html` | Compose form with Quill.js editor |
| `app/templates/scheduler/email_history.html` | View sent/scheduled emails history |

### Files Modified

| File | Changes |
|------|---------|
| `app/scheduler/routes.py` | Added `email_coaches`, `email_coaches_history`, `api_coach_email_preview` routes |
| `app/templates/base.html` | Added "Email Coaches" to Schedule dropdown menu |
| `app/main/routes.py` | Added `/cron/process-scheduled-emails` endpoint |
| `app/models/__init__.py` | Import `ScheduledEmail` model |
| `app/models/league_season.py` | Added `get_current_season()` class method |

### Database Schema

```sql
CREATE TABLE `sdll_scheduled_emails` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_by` BIGINT NOT NULL,
  `email_type` VARCHAR(50) NOT NULL DEFAULT 'coach_blast',
  `year` INT DEFAULT NULL,
  `is_spring` SMALLINT DEFAULT NULL,
  `leagues` TEXT DEFAULT NULL,  -- JSON array
  `recipients` TEXT NOT NULL,    -- JSON array of recipient objects
  `manual_recipients` TEXT DEFAULT NULL,  -- JSON array
  `send_mode` ENUM('cc', 'bcc', 'individual') NOT NULL DEFAULT 'cc',
  `subject` VARCHAR(255) NOT NULL,
  `body_html` TEXT NOT NULL,
  `body_text` TEXT NOT NULL,
  `reply_to` VARCHAR(255) NOT NULL,
  `scheduled_for` DATETIME DEFAULT NULL,
  `status` ENUM('pending', 'sending', 'sent', 'partial', 'failed') NOT NULL DEFAULT 'pending',
  `sent_at` DATETIME DEFAULT NULL,
  `attempted_at` DATETIME DEFAULT NULL,
  `recipient_count` INT DEFAULT 0,
  `sent_count` INT DEFAULT 0,
  `failed_count` INT DEFAULT 0,
  `error_message` TEXT,
  `failure_notified` TINYINT DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `idx_status_scheduled` (`status`, `scheduled_for`),
  KEY `idx_attempted` (`attempted_at`),
  CONSTRAINT `fk_scheduled_email_created_by` FOREIGN KEY (`created_by`) REFERENCES `sdll_users` (`ID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Routes Added

| Route | Method | Description |
|-------|--------|-------------|
| `/scheduler/email-coaches` | GET, POST | Compose and send/schedule email |
| `/scheduler/email-coaches/history` | GET | View email history |
| `/scheduler/api/coach-email-preview` | GET | API for recipient count/list |
| `/cron/process-scheduled-emails` | GET | Process scheduled emails (cron) |

### Cron Setup
Set up in cron-job.org every 5 minutes (`*/5 * * * *`):
```
https://your-app.railway.app/cron/process-scheduled-emails?token=YOUR_CRON_SECRET
```

### Usage

1. Navigate to Schedule > Email Coaches
2. Select leagues using checkboxes
3. Optionally add manual recipients
4. Choose send mode (CC/BCC/Individual)
5. Compose email with rich text editor
6. Send immediately or schedule for later

### Verification

```bash
# Test imports
python -c "from app.models.scheduled_email import ScheduledEmail; print('OK')"
python -c "from app.services.email_blast_service import get_coaches_by_leagues; print('OK')"

# Test routes
python -c "from app.scheduler.routes import scheduler_bp; print('OK')"
```

### Production Migration Required
Run `scripts/migrations/add_scheduled_email.sql` on Railway MySQL.

---

## Session: August 24, 2026 (Continued) - Calendar Edit Redirect Fix & Game Change Tracking

### 1. Calendar/Day View Edit Redirect Fix

**Problem:** When editing a game from the calendar or day view, the page would redirect to the manage games page instead of staying on the current view.

**Solution:** Added a hidden `return_to` field to form submissions that redirects back to the originating page.

**Files Modified:**
- `app/games/routes.py` - Check for `return_to` form field and redirect appropriately
- `app/templates/games/calendar.html` - Added `return_to` hidden field with calendar URL (preserves week and league filter)
- `app/templates/games/day_view.html` - Added `return_to` hidden field to edit and create forms (preserves current date)

### 2. Game Change Tracking & "Originally" Display

**Features:**
- Fixed NEW badge to use correct `date_added` column instead of `created_at`
- Track umpire_override changes (only for subsequent assignments, not initial)
- Show "Originally scheduled for..." text on team schedule pages for rescheduled games
- Added `GameChange.get_original_values()` and `GameChange.get_original_display()` methods

**Files Modified:**
- `app/models/game_change.py` - Added methods to reconstruct original game schedule
- `app/services/game_changes.py` - Added `umpire_override` to tracked fields
- `app/public/routes.py` - Fixed NEW badge logic, added game_originals context
- `app/templates/public/team_schedule.html` - Display "Originally..." text
- `app/umpires/routes.py` - Log change when umpire source is reassigned

### 3. Performance Optimizations

Fixed N+1 query issues on umpire schedule pages:
- Added eager loading with `joinedload()` for relationships
- Pre-loaded field and team data into lookup dictionaries
- Cached computed values (`_cached_field_name`, `_cached_umpire_count`)

**Files Modified:**
- `app/public/routes.py` - Optimized partner_schedule and partner_schedule_csv routes
- `app/umpires/routes.py` - Optimized umpire_calendar and umpire_schedule routes

### 4. Standardized Umpire Source Codes

Changed from 'academy'/'SDLL' to consistent 'SDL' everywhere:
- API validation accepts SDL, DIA, DYN (and any active partner short codes)
- CSS classes: `.umpire-SDL`, `.umpire-DIA`, `.umpire-DYN`
- Frontend onclick handlers use SDL

---

## Session: August 24, 2026 - Partner Schedule URLs & Manage Games Improvements

### Overview
Added public schedule URLs for umpire partners (Diamond, Dynamic) and improved the manage games view with client-side filtering and table view option.

### 1. Partner Schedule URLs

External umpire partners can now access their assigned games via a unique token-based URL without logging in.

**Features:**
- Token-based authentication (secure random URL per partner)
- Google Sheets-style table view with columns: Date, Day, Time, League, Matchup, Field, Type, Umps, Rules, Notes
- CSV download option (e.g., `SDLL_Fall2026_Diamond.csv`)
- Season selector and filters (field, league, date)
- Google Maps directions icon for fields with addresses
- NTL (No Time Limit) indicator for 3-hour games
- Rules column linking to division rules documents
- "NEW" badge for games added in the past week

**Files Created:**
- `app/templates/public/partner_schedule.html` - Public schedule view template

**Files Modified:**
- `app/models/umpire_partner.py` - Added `schedule_token` field and generation method
- `app/public/routes.py` - Added `/partner/<token>` and `/partner/<token>/csv` routes
- `app/umpires/routes.py` - Added token generation route
- `app/templates/umpires/partners.html` - Added Copy URL, View, Generate URL buttons

**Database Migration Required:**
```sql
ALTER TABLE sdll_umpire_partners ADD COLUMN schedule_token VARCHAR(32) DEFAULT NULL;
ALTER TABLE sdll_umpire_partners ADD UNIQUE INDEX idx_schedule_token (schedule_token);
```

### 2. Manage Games View Improvements

Enhanced `/games/<year>/<is_spring>/manage` with filtering and view options.

**Features:**
- Games without `game_date` are now hidden
- Toggle between Card view and Table view (Google Sheets style)
- Client-side filtering (no page reload) for:
  - League
  - Game type (all/games/practices)
  - Field
  - Date
  - Team (home or away)
- "Clear Filters" button
- Table view has compact rows with green header

**Files Modified:**
- `app/games/routes.py` - Added filter parameters, field_names context
- `app/templates/games/manage.html` - Added table view, client-side JS filtering, view toggle

### 3. Umpire Calendar Short Code Fix

Fixed umpire source assignment to use consistent short codes.

**Problem:** The umpire calendar was sending lowercase values like 'academy' but the database was using short codes like 'SDLL', 'DIA', 'DYN'.

**Solution:**
- Backend API now dynamically accepts valid short codes from active partners
- Frontend updated to use 'SDLL' instead of 'academy'
- CSS classes updated to match (`.umpire-SDLL`, `.umpire-DIA`, `.umpire-DYN`)

**Files Modified:**
- `app/umpires/routes.py` - Updated `api_set_umpire_source()` to accept partner short codes
- `app/templates/umpires/calendar.html` - Changed all 'academy' references to 'SDLL'

### 4. Umpire Count Override

Added ability to override umpire count per game via right-click menu on umpire calendar.

**Features:**
- Set 0, 1, or 2 umpires per game
- Reset to league default option
- Visual indicator (purple dots) for overridden games

**Database Migration Required:**
```sql
ALTER TABLE sdll_games ADD COLUMN umpire_count_override TINYINT DEFAULT NULL;
```

### Production SQL Summary

Run these on production:
```sql
-- Partner schedule tokens
ALTER TABLE sdll_umpire_partners ADD COLUMN schedule_token VARCHAR(32) DEFAULT NULL;
ALTER TABLE sdll_umpire_partners ADD UNIQUE INDEX idx_schedule_token (schedule_token);

-- Umpire count override per game
ALTER TABLE sdll_games ADD COLUMN umpire_count_override TINYINT DEFAULT NULL;
```

---

---

## Session: August 21, 2026 (Evening) - Missing Umpire Templates Fix

### Problem Diagnosed
Production errors #10, #11, #14 were caused by missing templates in the umpire system.

### Error Analysis
1. **Errors #10 & #11**: Table `sdll_umpire_profiles` error - User confirmed table exists, may have been transient or race condition
2. **Error #14**: `umpires/edit_delegation.html` template not found - Routes referenced templates that were never created

### Fix Applied
Created 9 missing umpire templates:

**Umpire Management (`app/templates/umpires/`)**:
- `edit_delegation.html` - Edit delegation percentages for a league
- `edit.html` - Edit umpire profile
- `partners.html` - List umpire partner organizations
- `add_partner.html` - Add new partner organization
- `edit_partner.html` - Edit partner organization
- `overrides.html` - Manage delegation override keywords
- `schedule.html` - View upcoming games with umpire assignments

**Umpire Portal (`app/templates/umpire_portal/`)**:
- `history.html` - View past completed games
- `pay.html` - View pay history and unpaid balance
- `profile.html` - View own profile (read-only)

### Templates Features
- Consistent styling matching existing templates
- Form validation (e.g., percentages sum to 100%)
- Quick presets for common delegation configurations
- Mobile-responsive design

### Test Results
Quick tests: 23 passed (database-independent tests)

---

## Session: August 21, 2026 (Continued) - Umpire System Navigation & Migration

### Completed
1. **Added Umpire Navigation Menu** (`app/templates/base.html`)
   - Shows "Umpires ▾" dropdown for users with umpire role or umpire management permissions
   - Umpire users see: My Dashboard, Available Games, My Games, Pay History
   - Coordinators/admins see: Manage Umpires, Partners, Delegation Rules
   - Conditional divider when user has both umpire and coordinator roles

2. **Ran Database Migration Successfully**
   - Fixed PRIMARY KEY issue on `sdll_leagues` table
   - Added umpire configuration columns to leagues
   - All 7 new tables created
   - Seeded data: 2 partners (Diamond, Dynamic), delegation rules per league, override keywords

3. **Fixed Test Fixture Cleanup**
   - Added try/except around all factory fixture teardown code
   - Prevents database lock timeout errors from causing test failures
   - Affected fixtures: field_factory, team_factory, game_factory, field_slot_factory,
     umpire_profile_factory, umpire_partner_factory, league_factory

4. **Test Results**: 155 passed, 1 skipped

### Commits Pushed
- `be0839f`: Add Umpires nav menu for umpire role users
- `e1b6278`: Fix test fixture teardown to handle lock timeouts gracefully

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
