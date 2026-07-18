# SDLL Web Application - Progress Report

**Last Updated:** July 8, 2026
**Status:** Phase 2 Complete - Season Setup, Teams, Field Allocations, League Settings, Playoff Placeholders, Game Generation & Field Restrictions

---

## What Was Built

### Project Structure
```
SDLLApp/
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── config.py             # Dev/Test/Prod configurations
│   ├── extensions.py         # SQLAlchemy, Flask-Login, Limiter, CSRF
│   ├── models/
│   │   ├── user.py           # User model with PII encryption (Fernet)
│   │   ├── team.py           # TeamSeason -> sdll_team_seasons
│   │   ├── game.py           # Game -> sdll_games
│   │   ├── field.py          # Field -> sdll_fields
│   │   ├── field_slot.py     # FieldSlot -> sdll_field_slots
│   │   ├── league.py         # League -> sdll_leagues
│   │   └── league_season.py  # LeagueSeason -> sdll_league_seasons
│   ├── auth/routes.py        # Login, logout, password reset
│   ├── main/routes.py        # Dashboard
│   ├── seasons/routes.py     # Season setup, teams, copy wizard
│   ├── games/routes.py       # Game list, view, upcoming
│   ├── fields/routes.py      # Field allocations management
│   ├── utils/
│   │   ├── encryption.py     # Fernet encryption for PII
│   │   └── logging.py        # Configurable logging (OFF/ON/EXTREME)
│   ├── static/css/           # LR_*.css + sdll_theme.css (green/orange)
│   └── templates/            # Jinja2 templates for all views
├── tests/
├── scripts/
│   ├── create_users_table.sql       # SQL migration for users
│   ├── add_team_name_column.sql     # SQL migration for team_name
│   ├── create_field_slots_table.sql # SQL migration for field slots
│   ├── create_league_seasons_table.sql # SQL migration for league settings
│   ├── seed_users.py                # Create test users
│   ├── revert_season.py             # Delete teams from a season
│   └── derive_field_slots.py        # Create field slots from game data
├── requirements.txt
├── run.py                    # Dev server (port 8084)
└── PROGRESS.md               # This file
```

### Database
- **Database name:** `sdllapp`
- **DB User:** `lrp_master`
- **Tables:** sdll_games, sdll_team_seasons, sdll_fields, sdll_leagues, sdll_users, etc.
- **Migrations applied:**
  - `create_users_table.sql` - sdll_users table with encrypted PII
  - `add_team_name_column.sql` - team_name column on sdll_team_seasons
  - `create_field_slots_table.sql` - sdll_field_slots table for allocations
  - `add_field_slot_ownership.sql` - is_owned column for slot ownership
  - `create_league_seasons_table.sql` - sdll_league_seasons for playoff formats
  - `add_playoff_columns.sql` - playoff_teams, seed_number, bracket_position, resolved_team_id
  - `add_game_type_columns.sql` - game_type on games, regular_season_games on league_seasons
  - `add_field_restrictions.sql` - restriction_type and restricted_leagues on sdll_fields
  - `add_league_time_restrictions.sql` - earliest/latest_start_time on sdll_leagues

---

## Features Implemented

### 1. User Authentication ✅
- Login/logout with session management (3-month expiry)
- Password hashing (Werkzeug scrypt)
- PII encryption at rest (Fernet) for email, name, phone
- Rate limiting on login (5/minute)
- Role-based access: admin, scheduler, umpire_coordinator, viewer

### 2. Navigation ✅
- Dropdown menu structure supporting long-term vision
- Schedule, Seasons, Umpires, People, Admin sections
- Role-based menu items (schedulers see edit options)

### 3. Dashboard ✅
- Upcoming games display
- Seasons overview with team counts
- Quick actions for schedulers

### 4. Season Management ✅ (NEW)
- **Season Setup** (`/seasons/setup`)
  - Create new empty season
  - View all existing seasons
  - Link to copy wizard
- **Season View** (`/seasons/<year>/<is_spring>`)
  - Teams grouped by league
  - Games list with home/away teams
  - "Manage Teams" button for schedulers
- **Team Management** (`/seasons/<year>/<is_spring>/teams`)
  - Add single team with custom name
  - Add multiple teams at once (auto-numbered)
  - Add playoff placeholders (e.g., "Seed 1", "Winner Game 3")
  - Set team names (separate from placeholder names)
  - Remove teams (soft delete)
  - Status badges: Playoff (gray), Named (green), Pending (yellow)
- **Copy Season** (`/seasons/copy`)
  - Select source season
  - Preview teams/games to copy
  - Copy teams only OR teams + games
  - Game dates adjusted by year difference

### 5. Games Browsing ✅
- Filter by year, season, league, status
- View game details
- Upcoming games view

### 6. Field Allocations ✅ (NEW)
- **Field Allocations Overview** (`/fields/allocations`)
  - View seasons with configured allocations
  - See slot counts and field counts per season
- **View Allocations** (`/fields/allocations/<year>/<is_spring>`)
  - Slots grouped by field
  - Shows day, time range, and league restrictions
- **Manage Allocations** (`/fields/allocations/<year>/<is_spring>/manage`)
  - Add new time slots (field, day, start/end time, league)
  - Edit existing slots
  - Remove slots (soft delete)
- **Copy Allocations** (`/fields/allocations/copy`)
  - Copy all slots from one season to another
- **Derive from Game Data** (script)
  - Analyze existing games to derive field availability patterns
  - Creates initial allocations based on actual usage
- **Slot Ownership**
  - Mark slots as SDLL-owned or Away (other league's home)
  - Filter view by ownership status
  - Bulk toggle ownership for entire field

### 7. League Settings ✅ (NEW)
- **League Settings** (`/seasons/<year>/<is_spring>/leagues`)
  - Configure playoff format per league per season
  - Formats: Single Elimination, Double Elimination, Round Robin + Knockout
  - Set number of teams qualifying for playoffs (2, 4, 6, or 8)
  - Auto-syncs leagues from teams in the season
  - Copied when copying a season to a new year

### 8. Season Reset ✅ (NEW)
- **Reset Season** (`/seasons/<year>/<is_spring>/reset`)
  - Delete games only
  - Delete field slots only
  - Delete playoff placeholders only
  - Delete all teams (cascades to delete games)
  - Delete entire season (cascades to delete everything)
- **Smart Cascading**
  - Deleting teams also deletes games (games reference teams)
  - Deleting season deletes teams, games, slots, and league configs
- **Delete Modes**
  - Soft delete (default): Records marked inactive, recoverable via database
  - Hard delete: Permanent removal, cannot be undone

### 9. Game Slot Generation ✅ (NEW)
- **Regular Season Games** - Configure games per team, generate matchups
- **Playoff Games** - Auto-calculated based on format (single elim = n-1, etc.)
- **Game Types** - `game_type` column: 'regular', 'playoff', 'practice'
- **League Settings** (`/seasons/<year>/<is_spring>/leagues`)
  - Set games per team (6, 8, 10, 12, 14, 16)
  - View expected vs actual game counts
  - Generate regular season games (round-robin matchups)
  - Generate playoff games (using seed placeholders)
- **Practices** - Single-team games (away_ID null)

### 10. Playoff Placeholders ✅
- **Automatic Generation on Season Copy**
  - League settings (format, qualifying teams, notes) copied from source season
  - Seed placeholders (Seed 1, Seed 2, etc.) auto-created based on copied playoff_teams setting
- **Manage Playoffs** (`/seasons/<year>/<is_spring>/playoffs/<league>`)
  - View all seed and bracket placeholders
  - Resolve seeds to actual teams (assign Seed 1 = "Thunderbolts")
  - Resolve bracket positions as games are played (Winner Game 1 = actual team)
  - Regenerate seeds or brackets if format changes
- **Placeholder Types**
  - Seeds: "Seed 1", "Seed 2", etc. - assigned based on regular season standings
  - Brackets: "Winner Game 1", "Loser Game 2", etc. - filled as playoff games complete
- **Resolution Workflow**
  1. Schedule playoff games using placeholders (Seed 1 vs Seed 4)
  2. After regular season, resolve seeds to actual teams
  3. As playoff games complete, resolve bracket positions to winners/losers

### 11. Field League Restrictions ✅ (NEW)
- **Restriction Types**
  - **Anyone**: No restrictions, any league can use the field
  - **Exclude**: Anyone EXCEPT specified leagues can use the field
  - **Only**: ONLY specified leagues can use the field
- **Manage Restrictions** (`/fields/restrictions`)
  - View all fields with current restrictions
  - Shows ownership (SDLL vs Away) for each field
  - Edit restrictions via modal dialog
  - Multi-select leagues for exclude/only lists
- **Use in Scheduling**
  - `field.can_league_use(league_name)` - check if a league can be scheduled at a field
  - Useful for auto-scheduling to avoid incompatible field assignments

### 12. League Time Restrictions ✅ (NEW)
- **Time Windows**
  - **Earliest Start Time**: Games cannot start before this time
  - **Latest Start Time**: Games cannot start after this time
  - Both are optional (NULL = no restriction)
- **Manage Restrictions** (`/leagues/time-restrictions`)
  - View all leagues with current time restrictions
  - Edit via modal dialog with preset buttons
  - Presets: Any Time, Before 5:30 PM, Before 6:00 PM, After 5:00 PM
- **Use in Scheduling**
  - `league.can_play_at_time(start_time)` - check if a game can be scheduled at this time
  - Prevents late games for younger leagues (Tee Ball, Rookie, BB A)

---

## Test Users

| Name | Email | Role | Password |
|------|-------|------|----------|
| Janna Price | schedule.sdll@gmail.com | scheduler | changeme123 |
| Zack Capozzi | sdll.umpires@gmail.com | umpire_coordinator | changeme123 |

---

## How to Use Season Setup

### Create a New Season (From Scratch)
1. Go to **Seasons → Season Setup**
2. Enter year and select Fall/Spring
3. Click "Create Season"
4. Add teams manually on the Team Management page

### Copy from Existing Season (Recommended)
1. Go to **Seasons → Copy Season**
2. Select source season (e.g., Fall 2025)
3. Enter target year (e.g., 2026) and season (Fall)
4. Choose whether to copy games
5. Click "Copy Season"
6. Review and edit teams as needed

**What gets copied:**
- Teams (with placeholder names reset)
- Games (optional, dates adjusted by year difference)
- League settings (playoff format, qualifying teams)
- Seed placeholders (Seed 1, Seed 2, etc. auto-generated)

### Manage Teams
1. Go to **Seasons → All Seasons**
2. Click "Manage Teams" on any season
3. Add/rename/remove teams as needed

### Team Naming Logic
Teams have two name fields:
- **display_name**: Placeholder (e.g., "BB Majors Team 1") - auto-generated
- **team_name**: Chosen name (e.g., "Thunderbolts") - set manually

Display priority:
1. If `team_name` is set → show team_name
2. If coach assigned (future) → show "Team [Coach Last Name]"
3. Otherwise → show placeholder (display_name)

### Revert a Season (Delete Data)
**Web Interface (Recommended):**
1. Go to **Seasons → [select season] → Reset** button
2. Choose what to delete (games, slots, placeholders, teams, or entire season)
3. Optionally check "Permanent delete" for hard delete
4. Confirm deletion

**Command Line (Alternative):**
```bash
# Preview what would be deleted
python scripts/revert_season.py --year 2026 --season fall --dry-run

# Soft delete (can be recovered)
python scripts/revert_season.py --year 2026 --season fall

# Also delete games
python scripts/revert_season.py --year 2026 --season fall --include-games

# Permanent delete
python scripts/revert_season.py --year 2026 --season fall --hard-delete
```

---

## How to Use Field Allocations

Field allocations represent the time slots available at each field, as provided by Durham Parks and Rec.

### Derive from Existing Games (First Time Setup)
Analyze past games to create initial allocations:
```bash
# Preview what would be created
python scripts/derive_field_slots.py --year 2025 --season fall --dry-run

# Create slots for same season
python scripts/derive_field_slots.py --year 2025 --season fall

# Create slots for a different season
python scripts/derive_field_slots.py --year 2025 --season fall --target-year 2026
```

### Copy from Previous Season
1. Go to **Seasons → Copy Allocations**
2. Select source season (e.g., Fall 2025)
3. Enter target year/season
4. Click "Copy Allocations"

### Manage Allocations
1. Go to **Seasons → Field Allocations**
2. Click "Manage" on a season
3. Add/edit/remove time slots as needed

### What Gets Tracked
Each slot stores:
- **Field**: Which field (e.g., Herndon 1, Parkwood)
- **Day**: Day of week (Monday-Sunday)
- **Time**: Start and end time (e.g., 5:30 PM - 7:00 PM)
- **League**: Optional restriction (e.g., "BB Majors only")
- **Notes**: Optional notes (e.g., "Parks & Rec allocation")

---

## How to Use Playoff Placeholders

### During Season Setup
When you copy a season:
1. **League settings are copied** - playoff format, qualifying teams, and notes carry over from the source season
2. **Seed placeholders are auto-generated** - Seed 1, Seed 2, etc. based on the `playoff_teams` setting

Example: If Fall 2025 "BB Majors" had Double Elimination with 6 qualifying teams, Fall 2026 will have the same settings plus Seed 1-6 placeholders ready to go.

### Managing Playoffs
1. Go to **Seasons → All Seasons** → select a season → **League Settings**
2. Click **Playoffs** button on any league
3. You'll see:
   - **Seed placeholders** (Seed 1, Seed 2, etc.)
   - **Bracket placeholders** (Winner Game 1, etc.) if generated

### Assigning Seeds
After the regular season ends:
1. Go to the Playoffs page for the league
2. Use the dropdown to assign each seed to the actual team
3. Click **Set** to save

### Regenerating Placeholders
- If you change the number of qualifying teams, click **Regenerate Seeds**
- If you change the playoff format, click **Regenerate Brackets**
- Only unresolved placeholders are deleted; already-assigned ones are preserved

### Scheduling with Placeholders
When creating playoff games, you can schedule "Seed 1 vs Seed 4" before knowing which teams will play. Once you resolve the seeds to actual teams, the game display updates automatically.

---

## New Season Setup Cookbook

This is a complete walkthrough for setting up a new season (e.g., Fall 2026 from Fall 2025).

### Prerequisites
- [ ] Previous season exists with teams configured (e.g., Fall 2025)
- [ ] Field allocations set up for previous season
- [ ] League settings configured in previous season

### Phase 1: Copy the Season Structure

**Step 1: Copy Season**
1. Go to **Seasons → Copy Season**
2. Select source: **Fall 2025**
3. Enter target: **2026**, **Fall**
4. Leave "Copy games" unchecked (we'll generate fresh game slots)
5. Click **Copy Season**

**What happens automatically:**
- Teams copied with placeholder names (e.g., "BB Majors Team 1")
- League settings copied (games/team, playoff format, qualifying teams)
- Seed placeholders generated (Seed 1, Seed 2, etc. per league)

**Step 2: Copy Field Allocations**
1. Go to **Seasons → Copy Allocations**
2. Select source: **Fall 2025**
3. Enter target: **Fall 2026**
4. Click **Copy Allocations**

**Step 3: Verify the Copy**
1. Go to **Seasons → All Seasons → Fall 2026**
2. Confirm team counts match previous year
3. Go to **League Settings** and verify each league has correct settings

---

### Phase 2: Adjust Teams (if needed)

**If team count changed:**
1. Go to **Seasons → Fall 2026 → Manage Teams**
2. Add teams: Select league → Enter count → Click "Add Teams"
3. Remove teams: Click X next to team → Confirm

**If you need to start over:**
1. Go to **Seasons → Fall 2026 → Reset**
2. Click "Delete Teams" (cascades to delete games too)
3. Start fresh with team setup

---

### Phase 3: Configure League Settings

**Step 1: Set Games Per Team**
1. Go to **Seasons → Fall 2026 → League Settings**
2. For each league, click **Edit**
3. Set "Games Per Team" (typically 10-12 for regular season)
4. Verify playoff format and qualifying teams
5. Click **Save**

**Step 2: Verify Seed Placeholders**
1. In League Settings, check "Placeholders" column
2. If showing "None", click **Generate Placeholders** for that league
3. Or go to **Playoffs** to manage individually

---

### Phase 4: Generate Game Slots

**Step 1: Generate Regular Season Games**
1. Go to **League Settings**
2. Scroll to "Generate Game Slots" section
3. For each league, click **+ Regular Games**
4. Verify "Current Games" matches "Expected Games"

**Step 2: Generate Playoff Games** (optional - can do later)
1. Ensure seed placeholders exist (check "Placeholders" column)
2. Click **+ Playoff Games** for each league
3. Playoff games use Seed 1 vs Seed 4, etc.

**What you now have:**
- Game slots with teams assigned (Team 1 vs Team 2, etc.)
- No dates/times/locations yet - just the matchups

---

### Phase 5: Schedule Games into Field Slots

*(Coming soon - Game scheduling feature)*

The next step will be to:
1. View available field slots for each day
2. Drag/assign games to slots
3. Balance early vs late game times per team

---

### Phase 6: As Season Progresses

**When team names are finalized:**
1. Go to **Manage Teams**
2. Click team row → Enter team name (e.g., "Thunderbolts")
3. Games will display the real name instead of placeholder

**When regular season ends:**
1. Go to **League Settings → Playoffs**
2. Assign actual teams to seeds based on standings
3. Seed 1 = 1st place team, Seed 2 = 2nd place, etc.

**As playoff games complete:**
1. Go to **Playoffs** for the league
2. Resolve bracket positions (Winner Game 1 = actual team)

---

### Quick Reference: Season Setup Checklist

```
□ Phase 1: Copy Structure
  □ Copy season (teams + league settings)
  □ Copy field allocations
  □ Verify copy

□ Phase 2: Adjust Teams
  □ Add/remove teams if count changed
  □ Reset if needed

□ Phase 3: Configure Leagues
  □ Set games per team for each league
  □ Verify playoff settings
  □ Generate seed placeholders

□ Phase 4: Generate Games
  □ Generate regular season games
  □ Generate playoff games (optional)

□ Phase 5: Schedule
  □ Assign games to field slots
  □ Balance game times

□ Phase 6: During Season
  □ Set team names as finalized
  □ Resolve seeds after regular season
  □ Resolve brackets as playoffs progress
```

---

## Next Steps (MVP Remaining)

| Priority | Capability | Description |
|----------|------------|-------------|
| **HIGH** | M5: Edit Games | Change date/time/location of games |
| **HIGH** | M7: Game Status | Mark postponed/cancelled/completed |
| **MED** | M8: Action Queue | Generate notification list on changes |
| **MED** | M9: Notifications | Send email/text from the app |
| **LOW** | M6: Add Games | Create new game records |

---

## URLs

| Page | URL |
|------|-----|
| Dashboard | http://localhost:8084/ |
| Season Setup | http://localhost:8084/seasons/setup |
| Copy Season | http://localhost:8084/seasons/copy |
| All Seasons | http://localhost:8084/seasons/ |
| All Games | http://localhost:8084/games/ |
| Field Allocations | http://localhost:8084/fields/allocations |
| Copy Allocations | http://localhost:8084/fields/allocations/copy |
| All Fields | http://localhost:8084/fields/ |
| Field Restrictions | http://localhost:8084/fields/restrictions |
| All Leagues | http://localhost:8084/leagues/ |
| League Time Restrictions | http://localhost:8084/leagues/time-restrictions |
| League Settings | http://localhost:8084/seasons/2026/0/leagues |
| Playoffs (per league) | http://localhost:8084/seasons/2026/0/playoffs/BB%20Majors |
| Reset Season | http://localhost:8084/seasons/2026/0/reset |

---

## Quick Start (for new developer)

```bash
# 1. Set up environment
cp .env.example .env
# Edit .env with MySQL credentials

# 2. Import database (user: lrp_master)
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p < Dump20260702.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/create_users_table.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_team_name_column.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/create_field_slots_table.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_field_slot_ownership.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/create_league_seasons_table.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_playoff_columns.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_game_type_columns.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_field_restrictions.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_league_time_restrictions.sql

# 3. Seed users
python scripts/seed_users.py

# 4. Run app
python run.py
# Visit http://localhost:8084
```

---

## Design Decisions & Defaults

This section captures key design decisions made during development.

### Season & Team Management

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Team names on copy | Reset to placeholders | When copying a season, team names reset (e.g., "BB Majors Team 1") because rosters change year-to-year; structure (# of teams per league) stays the same |
| Team display priority | 1) team_name, 2) "Team [Coach]", 3) placeholder | Allows gradual refinement as season details are finalized |
| Team status badges | Playoff (gray), Named (green), Pending (yellow) | Visual indicator of setup progress |
| Soft delete default | Yes (active=0) | Allows recovery; hard delete available via script |

### Field Allocations

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Slot ownership | SDLL-owned vs Away | Some fields are reserved by other leagues where SDLL is away team; helps avoid scheduling home games at slots we don't control |
| Default ownership | SDLL-owned (is_owned=1) | Most slots are ours; manually mark exceptions |
| Group by options | Field OR Day of Week | Different views useful for different tasks (field-centric vs schedule-centric) |
| Ownership filter | All / SDLL / Away | Quick filtering to see only relevant slots |
| Bulk ownership toggle | Per-field buttons | Entire fields (e.g., BCLL Field #2) are often owned by another league |
| Delete confirmation | HTML modal (not browser alert) | Cleaner UX, consistent with rest of app |
| Buttons layout | Horizontal (Edit + X) | Better use of table width |

### League Settings

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Playoff formats | Single Elim, Double Elim, Round Robin + Knockout | Covers standard tournament formats used in youth baseball/softball |
| Default format | Single Elimination | Most common format |
| Default playoff teams | 4 | Common bracket size |
| Auto-sync leagues | From teams in season | Leagues are created automatically when teams exist |
| Copy with season | Yes | Playoff formats typically stay consistent year-to-year |

### Game Slot Generation

| Decision | Choice | Rationale |
|----------|--------|-----------|
| game_type column | 'regular', 'playoff', 'practice' | Clear distinction for filtering and reporting |
| Teams always assigned | Yes | Enables balancing (5:30 vs 7:30 slots) before scheduling |
| Practice = single team | away_ID null | Same table, different type; still needs scheduling |
| Regular season matchups | Round-robin algorithm | Balanced schedule where each team plays others evenly |
| Playoff game count | Auto-calculated from format | Single elim = n-1, double elim = 2n-2, etc. |
| Default games/team | 10 | Typical regular season length |
| Generate adds to existing | Yes | Can generate more games if needed without clearing |

### Season Reset

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Cascading deletes | Teams → Games | Games reference teams; can't have orphaned game records |
| Full season delete | Removes all related data | Clean slate; season won't appear in lists |
| Default soft delete | Yes | Safety net; can recover via database if mistake |
| Hard delete option | Checkbox opt-in | Available for permanent cleanup but not default |
| Placeholders separate | Can delete independently | May want to regenerate without touching regular teams |
| Visual warnings | Red styling for dangerous ops | Clear indication of cascading/destructive actions |

### Playoff Placeholders

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Copy league settings on season copy | Yes | Playoff formats typically stay consistent year-to-year |
| Auto-generate seeds on copy | Yes | Always need Seed 1-N to schedule tournament games ahead of time |
| Seeds vs Brackets | Separate types | Seeds filled from standings; brackets filled from game results |
| seed_number column | Integer (1, 2, 3, etc.) | Simple ordering and lookup |
| bracket_position column | String ("W1", "L1", etc.) | Flexible for different tournament formats |
| resolved_team_id | Nullable FK | Points to actual team once determined |
| Regeneration | Delete unresolved only | Preserves already-resolved placeholders |
| Display when resolved | Show actual team name | Resolving updates what's displayed in schedules |
| MySQL NULLS LAST workaround | CASE expression | MySQL doesn't support NULLS LAST; use CASE to sort nulls last |

### Field League Restrictions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Restriction types | Anyone / Exclude / Only | Covers all common scenarios: unrestricted, blacklist, whitelist |
| Storage format | Comma-separated string | Simple, no extra table needed; leagues list is short |
| Field-level not slot-level | Yes | Restrictions typically apply to entire field, not individual time slots |
| can_league_use() method | On Field model | Easy check during scheduling: `field.can_league_use('BB Majors')` |
| Default restriction | 'anyone' | Most fields have no restrictions; opt-in to limit |
| UI | Modal dialog | Quick edits without leaving the page; multi-select for leagues |

### UI/UX Patterns

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Color scheme | Forest Green (#228B22) + Orange (#FF8C00) | SDLL brand colors |
| Season badges | Green for Spring, Orange for Fall | Visual distinction |
| Dropdown nav links | Dark text (#333) on white background | Readability; white text reserved for top-level nav on green bar |
| Modal dialogs | For edit/delete actions | Keeps user on same page; Escape key to close |
| Form actions | POST with hidden action field | RESTful-ish pattern without requiring separate endpoints |

### Data Model

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Field slots separate from games | Yes | Slots = available windows; Games = actual scheduled events |
| League settings per season | Yes (sdll_league_seasons table) | Playoff format may vary by season |
| No foreign key on field_slots | Application-level integrity | sdll_fields.ID lacked primary key index |

---

## Session Log (July 3-8, 2026)

### What Was Accomplished

1. **Foundation** - Flask app with SQLAlchemy, authentication, role-based access
2. **Season Management** - Create, copy, view seasons; manage teams with naming workflow
3. **Field Allocations** - Time slots per field, derived from game history, ownership tracking
4. **League Settings** - Playoff format configuration per league per season
5. **Copy Workflow** - Copy season now includes teams, games (optional), field allocations, league settings, and seed placeholders
6. **Playoff Placeholders** - Automatic seed generation, bracket position tracking, resolution workflow
7. **Season Reset** - Web UI for deleting season data with cascading logic and soft/hard delete options
8. **Game Slot Generation** - Regular season round-robin matchups, playoff games from seed placeholders, game_type tracking
9. **Season Setup Cookbook** - Complete walkthrough documentation for setting up a new season
10. **Field League Restrictions** - Specify which leagues can/cannot use each field (Anyone / Exclude / Only)

### Key Files Created/Modified

- `app/models/field_slot.py` - New model for field time slots
- `app/models/league_season.py` - New model for league settings
- `app/models/team.py` - Extended with playoff placeholder methods
- `app/fields/routes.py` - New blueprint for field management
- `app/seasons/routes.py` - Added playoff management routes
- `app/templates/fields/*.html` - Field allocation templates
- `app/templates/seasons/manage_leagues.html` - League settings template
- `app/templates/seasons/manage_playoffs.html` - Playoff placeholder management
- `app/templates/seasons/reset.html` - Season reset with cascading options
- `app/models/game.py` - Extended with game generation methods
- `scripts/derive_field_slots.py` - Script to create slots from game data
- `scripts/add_game_type_columns.sql` - Migration for game_type and regular_season_games
- `scripts/create_field_slots_table.sql` - Migration for field slots
- `scripts/create_league_seasons_table.sql` - Migration for league settings
- `scripts/add_playoff_columns.sql` - Migration for playoff placeholder columns
- `scripts/add_field_restrictions.sql` - Migration for field league restrictions
- `app/templates/fields/restrictions.html` - Field restrictions management UI

### Pending Migrations

If starting fresh, run all migrations in order:
```bash
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/create_users_table.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_team_name_column.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/create_field_slots_table.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_field_slot_ownership.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/create_league_seasons_table.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_playoff_columns.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_game_type_columns.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_field_restrictions.sql
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u lrp_master -p sdllapp < scripts/add_league_time_restrictions.sql
```
