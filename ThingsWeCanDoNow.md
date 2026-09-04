# SDLL Site Capabilities

This document enumerates every capability available in the South Durham Little League web application. Each feature is tagged with the required access level and includes navigation instructions.

## Access Levels

| Role | Description |
|------|-------------|
| `public` | No login required |
| `authenticated` | Any logged-in user |
| `admin` | Full administrative access |
| `BoardExec` | President and President-elect |
| `BB_VP` | Baseball Vice President (on-field operations leader) |
| `SB_VP` | Softball Vice President (on-field operations leader) |
| `scheduler` | Users who can edit schedules and league settings |
| `umpire_coordinator` | Users who manage umpire assignments |
| `treasurer` | Financial/pay-related access |
| `BBPlayerAgent` | Baseball player agent (draft/player management) |
| `SBPlayerAgent` | Softball player agent (draft/player management) |
| `coaching_coordinator` | Coaching coordination functions |
| `facilities` | Board member responsible for fields/structures |
| `fieldCaptain` | Users responsible for specific fields |
| `umpire` | Users with umpire role |
| `coach` | Users with coach role (may have limited access to their own teams) |
| `parent` | Parent/family member (minimal access) |
| `partner_contact` | Contact for partner umpire organizations |
| `viewer` | Default role - basic authenticated access |
| `product_admin` | Site owner(s) with full analytics access (via PRODUCT_ADMIN_EMAILS env var) |

Roles can be combined (e.g., `admin|scheduler`). Access checks use `has_role()` which supports pipe-delimited role strings.

---

## 1. Authentication

### 1.1 Login
- **Access:** `public`
- **Path:** `/auth/login`
- **Actions:**
  - Enter email and password to log in
  - "Remember Me" checkbox for persistent session
  - Link to password reset
- **Navigation:** Click "Login" in top navigation bar

### 1.2 Logout
- **Access:** `authenticated`
- **Path:** `/auth/logout`
- **Actions:** Logs out the current user
- **Navigation:** Click username in top nav → "Logout"

### 1.3 Password Reset Request
- **Access:** `public`
- **Path:** `/auth/forgot-password`
- **Actions:**
  - Enter email address
  - System sends password reset link (valid 1 hour)
- **Navigation:** Login page → "Forgot Password?"

### 1.4 Password Reset (Token)
- **Access:** `public` (with valid token)
- **Path:** `/auth/reset-password/<token>`
- **Actions:**
  - Enter new password
  - Confirm new password
- **Navigation:** Click link in password reset email

---

## 2. Dashboard & Main Pages

### 2.1 Dashboard
- **Access:** `authenticated`
- **Path:** `/` or `/dashboard`
- **Actions:**
  - View quick stats for current season
  - Access quick links to common tasks
  - See recent activity (for schedulers/admins)
- **Navigation:** Click "SDLL" logo or "Dashboard" link

### 2.2 Season Selector
- **Access:** `authenticated`
- **Path:** Dropdown in navigation
- **Actions:**
  - Switch between Spring/Fall seasons
  - Switch between years
- **Navigation:** Season dropdown in top navigation

### 2.3 Master Schedule (Board View)
- **Access:** `admin`, `BoardExec`, `BB_VP`, `SB_VP`, `scheduler`, `umpire_coordinator`, `treasurer`, `BBPlayerAgent`, `SBPlayerAgent`, `coaching_coordinator`, `facilities`
- **Path:** `/master-schedule`
- **URL Args:** `?start_date=YYYY-MM-DD`, `?end_date=YYYY-MM-DD`, `?league=`, `?field=`, `?show_cancelled=1`
- **Actions:**
  - View all games/practices/scrimmages in current season
  - Filter by date range (start date defaults to today)
  - Filter by division (league)
  - Filter by field
  - Toggle cancelled events visibility
  - View season progress indicator (% complete, days remaining)
- **Access Control:**
  - Not logged in: Landing page with login link
  - Logged in without permission: Request access page
  - Logged in with permission: Full schedule view
- **Navigation:** "Master Schedule" link in top navigation (visible to authorized roles)

---

## 3. Season Management

### 3.1 Season Overview
- **Access:** `scheduler`, `admin`
- **Path:** `/seasons/<year>/<is_spring>`
- **Actions:**
  - View all leagues in the season
  - See team counts per league
  - Access schedule settings, teams, fields
- **Navigation:** Dashboard → Select season → "Season Overview"

### 3.2 Manage Leagues
- **Access:** `scheduler`, `admin`
- **Path:** `/seasons/<year>/<is_spring>/leagues`
- **Actions:**
  - Add new league to season
  - Remove league from season (soft delete)
  - Set playoff format (single/double elimination, round robin, none)
  - Set number of playoff teams (0 = all qualify)
  - Set regular season games per team
  - Toggle scrimmages on/off per league
- **Navigation:** Season Overview → "Manage Leagues"

### 3.3 Schedule Settings
- **Access:** `scheduler`, `admin`
- **Path:** `/seasons/<year>/<is_spring>/schedule-settings`
- **Actions:**
  - Set practice days (Mon-Sun) per league
  - Set game days per league
  - Set P/G days (can have either practice or game)
  - Set first practice date
  - Set opening day date
  - Set regular season end date
  - Set season end date (playoffs)
- **Navigation:** Season Overview → "Schedule Settings"

### 3.4 Manage Teams
- **Access:** `scheduler`, `admin`
- **Path:** `/seasons/<year>/<is_spring>/teams`
- **Actions:**
  - Add new team to a league
  - Edit team name/color
  - Assign head coach to team
  - Assign assistant coaches
  - Set team as placeholder (for scheduling)
  - Deactivate/reactivate teams
  - Copy teams from previous season
- **Navigation:** Season Overview → "Manage Teams"

### 3.5 Team Setup Page
- **Access:** `scheduler`, `admin`
- **Path:** `/seasons/<year>/<is_spring>/team-setup`
- **Actions:**
  - View all teams grouped by league
  - Edit team details (async save)
  - Assign coaches via dropdown
  - Quick bulk editing
- **Navigation:** Season Overview → "Team Setup"

### 3.6 Manage Playoffs
- **Access:** `scheduler`, `admin`
- **Path:** `/seasons/<year>/<is_spring>/playoffs/<league>`
- **Actions:**
  - Set playoff seeds (drag-and-drop or manual)
  - Generate playoff bracket
  - View/edit bracket structure
  - Assign teams to placeholder spots
  - Set playoff game dates/times
- **Navigation:** Season Overview → "Playoffs" → Select league

### 3.7 Create New Season
- **Access:** `admin`
- **Path:** `/seasons/create`
- **Actions:**
  - Create Spring or Fall season for a year
  - Option to copy leagues from previous season
  - Option to copy teams from previous season
  - Option to copy field allocations
- **Navigation:** Dashboard → "Create Season" or season dropdown → "Create New"

### 3.8 Set Current Season
- **Access:** `admin`
- **Path:** `/seasons/<year>/<is_spring>/set-current`
- **Actions:**
  - Mark a season as the current/active season
  - Affects navbar display and default season
- **Navigation:** Season Overview → "Set as Current Season"

---

## 4. Field Management

### 4.1 Fields Index
- **Access:** `scheduler`, `admin`
- **Path:** `/fields/`
- **URL Args:** `?show_inactive=1` to include inactive fields
- **Actions:**
  - View all active fields (owned and away)
  - See field properties (usage type, practice capacity)
  - Toggle ownership (SDLL vs Away)
  - Add new field
  - Deactivate fields (removes from calendars and dropdowns)
  - Toggle "Show Inactive Fields" to view and reactivate deactivated fields
- **Navigation:** Dashboard → "Fields" → "Manage Fields"

### 4.2 Add Field
- **Access:** `scheduler`, `admin`
- **Path:** `/fields/add`
- **Actions:**
  - Set field name and location
  - Set address (for maps)
  - Set field properties (size, surface, lights, etc.)
  - Mark as owned vs. away field
  - Set number of backstops/diamonds
- **Navigation:** Fields Index → "Add Field"

### 4.3 Edit Field
- **Access:** `scheduler`, `admin`
- **Path:** `/fields/<id>/edit`
- **Actions:**
  - Update all field properties
  - Change ownership status
  - Update address/location
- **Navigation:** Fields Index → Click field name

### 4.4 Field Properties (Bulk)
- **Access:** `scheduler`, `admin`
- **Path:** `/fields/properties`
- **Actions:**
  - Quick toggle for all field properties across all fields
  - Properties: lights, irrigation, parking, restrooms, concessions
  - Batch save
- **Navigation:** Fields → "Field Properties"

### 4.5 Field Time Restrictions
- **Access:** `scheduler`, `admin`
- **Path:** `/fields/time-restrictions`
- **Actions:**
  - Set earliest game start time per field per day
  - Set latest game start time per field per day
  - Set time restrictions (e.g., no games before 5pm on weekdays)
- **Navigation:** Fields → "Time Restrictions"

### 4.6 Field Allocations
- **Access:** `scheduler`, `admin`
- **Path:** `/fields/allocations/<year>/<is_spring>`
- **Actions:**
  - View allocation summary per league
  - See hours allocated per field per league
- **Navigation:** Fields → "Allocations" → Select season

### 4.7 Manage Field Allocations
- **Access:** `scheduler`, `admin`
- **Path:** `/fields/allocations/<year>/<is_spring>/manage`
- **Actions:**
  - Allocate specific time slots to leagues
  - Set practice vs. game allocations
  - Set day-of-week patterns
  - Copy allocations from previous season
- **Navigation:** Field Allocations → "Manage"

### 4.8 Field Blackout Dates
- **Access:** `scheduler`, `admin`
- **Path:** `/fields/blackouts`
- **Actions:**
  - Add blackout dates (field unavailable)
  - Set reason (weather, maintenance, event)
  - Remove blackout dates
- **Navigation:** Fields → "Blackout Dates"

### 4.9 Specific-Date Field Allocations
- **Access:** `scheduler`, `admin`
- **Path:** `/fields/allocations/<year>/<is_spring>/manage`
- **Actions:**
  - Create one-off field allocations for specific dates (inverse of blackouts)
  - Use for tournaments, make-up games, special events
  - Override normal weekly allocation patterns for a single date
  - Set league, time slot, and date for specific allocation
- **Navigation:** Field Allocations → "Manage" → "Specific Date Allocations" section

---

## 5. Game Management

### 5.1 Games Calendar
- **Access:** `scheduler`, `admin`
- **Path:** `/games/calendar`
- **Actions:**
  - View all games in calendar format
  - Filter by league, field, team
  - Click game to view/edit details
- **Navigation:** Dashboard → "Games" → "Calendar"

### 5.2 Games List
- **Access:** `scheduler`, `admin`
- **Path:** `/games/`
- **Actions:**
  - View all games in table format
  - Filter by date range, league, field, team, game type
  - Sort by various columns
  - Bulk actions (cancel, reschedule)
- **Navigation:** Dashboard → "Games" → "All Games"

### 5.3 Add Game
- **Access:** `scheduler`, `admin`
- **Path:** `/games/add`
- **Actions:**
  - Create new game/practice/scrimmage
  - Set date, time, field
  - Assign home and away teams
  - Set game type (regular, playoff, scrimmage, practice)
- **Navigation:** Games → "Add Game"

### 5.4 Edit Game
- **Access:** `scheduler`, `admin`
- **Path:** `/games/<id>/edit`
- **Actions:**
  - Change date/time
  - Change field
  - Change teams
  - Cancel game (with reason)
  - Add notes
  - Record final score
- **Navigation:** Games list/calendar → Click game

### 5.5 Reschedule Game
- **Access:** `scheduler`, `admin`
- **Path:** `/games/<id>/reschedule`
- **Actions:**
  - Find new time slot
  - View field availability
  - Check team conflicts
  - Send notifications to affected parties
- **Navigation:** Game detail → "Reschedule"

### 5.6 Cancel Game
- **Access:** `scheduler`, `admin`
- **Path:** POST `/games/<id>/cancel`
- **Actions:**
  - Mark game as cancelled
  - Set cancellation reason
  - Trigger notifications
- **Navigation:** Game detail → "Cancel Game"

### 5.7 Record Game Score
- **Access:** `scheduler`, `admin`
- **Path:** POST `/games/<id>/score`
- **Actions:**
  - Enter final score
  - Mark game as complete
- **Navigation:** Game detail → "Record Score"

---

## 6. Schedule Generation

### 6.1 Schedule Overview
- **Access:** `scheduler`, `admin`
- **Path:** `/scheduler/`
- **Actions:**
  - View schedule generation status
  - See which leagues have generated schedules
  - Access generation and review tools
- **Navigation:** Dashboard → "Scheduler"

### 6.2 Generate Schedule
- **Access:** `scheduler`, `admin`
- **Path:** `/scheduler/generate`
- **Actions:**
  - Select leagues to generate
  - Set generation parameters
  - Run schedule generation algorithm
  - View generation progress
- **Navigation:** Scheduler → "Generate Schedule"

### 6.3 Review Proposal
- **Access:** `scheduler`, `admin`
- **Path:** `/scheduler/<year>/<is_spring>/proposal`
- **Actions:**
  - View proposed schedule before accepting
  - See conflicts and warnings
  - Filter by league, team, field
  - Approve individual games
  - Reject and modify games
- **Navigation:** Scheduler → "Review Proposal"

### 6.4 Accept Schedule
- **Access:** `scheduler`, `admin`
- **Path:** POST `/scheduler/<year>/<is_spring>/accept`
- **Actions:**
  - Accept proposed schedule (moves to live games)
  - Lock schedule from regeneration
  - Trigger coach notifications
- **Navigation:** Review Proposal → "Accept Schedule"

### 6.5 Regenerate Schedule
- **Access:** `scheduler`, `admin`
- **Path:** POST `/scheduler/<year>/<is_spring>/regenerate`
- **Actions:**
  - Clear current proposal
  - Re-run generation with updated parameters
- **Navigation:** Review Proposal → "Regenerate"

### 6.6 Lock/Unlock Schedule
- **Access:** `scheduler`, `admin`
- **Path:** POST `/scheduler/<year>/<is_spring>/lock` or `/unlock`
- **Actions:**
  - Lock: Prevent accidental regeneration
  - Unlock: Allow regeneration (warning displayed)
- **Navigation:** Scheduler → "Lock Schedule" / "Unlock Schedule"

---

## 7. League Settings

### 7.1 Leagues Index
- **Access:** `authenticated`
- **Path:** `/leagues/`
- **Actions:**
  - View all active leagues
  - See league properties
- **Navigation:** Dashboard → "Leagues"

### 7.2 Pitch Types
- **Access:** `scheduler`, `admin`
- **Path:** `/leagues/pitch-types`
- **Actions:**
  - Set pitch type per league (coach pitch, machine pitch, player pitch)
  - Affects scheduling rules and game duration
- **Navigation:** Leagues → "Pitch Types"

### 7.3 Seasonal Names
- **Access:** `scheduler`, `admin`
- **Path:** `/leagues/seasonal-names`
- **Actions:**
  - Set fall display name for leagues
  - Used when fall league names differ from spring
- **Navigation:** Leagues → "Seasonal Names"

### 7.4 Time Restrictions
- **Access:** `scheduler`, `admin`
- **Path:** `/leagues/time-restrictions`
- **Actions:**
  - Set earliest game start time per league
  - Set latest game start time per league
  - E.g., younger leagues can't play after 6pm
- **Navigation:** Leagues → "Time Restrictions"

### 7.5 Field Rules
- **Access:** `scheduler`, `admin`
- **Path:** `/leagues/field-rules`
- **Actions:**
  - Set allowed game fields per league
  - Set allowed practice fields per league
  - Set preferred fields (prioritized in scheduling)
  - Save individual league or bulk save all
- **Navigation:** Leagues → "Field Rules"

### 7.6 Umpire Patterns
- **Access:** `scheduler`, `admin`
- **Path:** `/leagues/umpire-patterns`
- **Actions:**
  - Set number of umpires required per league
  - Set playoff umpire count (if different)
  - 0 = no umpires required (tee ball, etc.)
- **Navigation:** Leagues → "Umpire Patterns"

### 7.7 League Rules URLs
- **Access:** `scheduler`, `admin`
- **Path:** `/leagues/rules`
- **Actions:**
  - Set URL to rules document per league
  - Displayed on public schedule pages
  - Save individual or bulk save all
- **Navigation:** Leagues → "Rules Documents"

---

## 8. Umpire Coordinator Functions

### 8.1 Umpire Calendar (Week View)
- **Access:** `umpire_coordinator`, `scheduler`, `admin`
- **Path:** `/umpires/<year>/<is_spring>/calendar`
- **URL Args:** `?week=YYYY-WW` to jump to a specific week, `?league=` to filter
- **Actions:**
  - View all games needing umpires by week
  - See assignment status (filled, partial, open)
  - Filter by league (client-side)
  - Right-click games to assign umpire source (SDL, DIA, DYN)
  - Right-click to set umpire count override
  - Click day header to navigate to day view
- **Navigation:** Dashboard → "Umpires" → "Calendar"

### 8.1b Umpire Calendar (Day View)
- **Access:** `umpire_coordinator`, `scheduler`, `admin`
- **Path:** `/umpires/<year>/<is_spring>/day/<date>` or `/umpires/<year>/<is_spring>/day?date=YYYY-MM-DD`
- **URL Args:** `?date=YYYY-MM-DD` to jump to a specific date, `?league=` to filter, `?game=ID` to highlight specific game
- **Actions:**
  - View all games for a single day with full details
  - Filter by league (client-side)
  - Right-click games to assign umpire source (SDL, DIA, DYN)
  - Right-click to set umpire count override
  - Date picker to jump to any date
  - "Today" button for quick access
- **Navigation:** Umpire Calendar → "Day View" button, or click day header in week view, or via umpire assignment email links

### 8.2 Manage Umpires
- **Access:** `umpire_coordinator`, `scheduler`, `admin`
- **Path:** `/umpires/manage`
- **Actions:**
  - View all registered umpires
  - See umpire availability
  - View umpire stats (games worked)
  - Activate/deactivate umpires
- **Navigation:** Umpires → "Manage Umpires"

### 8.3 Assign Umpires
- **Access:** `umpire_coordinator`, `scheduler`, `admin`
- **Path:** `/umpires/game/<game_id>/assign`
- **Actions:**
  - View available umpires for a game
  - Assign primary umpire
  - Assign secondary umpire (if required)
  - Remove assignments
  - Send assignment notifications
- **Navigation:** Umpire Calendar → Click game → "Assign"

### 8.4 Partner Schedule Management
- **Access:** `umpire_coordinator`, `scheduler`, `admin`
- **Path:** `/umpires/partners`
- **Actions:**
  - View partner organization schedule links
  - Generate/regenerate partner tokens
  - Copy schedule URLs
- **Navigation:** Umpires → "Partner Schedules"

### 8.5 Add Managed Umpire
- **Access:** `umpire_coordinator`, `admin`
- **Path:** `/umpires/add-managed`
- **Actions:**
  - Create umpire profile for youth without their own email
  - Link to a parent/guardian account who manages them
  - Set first name, last name, birth date
  - Set baseball/softball eligibility levels
  - Specify guardian relationship (parent, guardian, other)
- **Navigation:** Umpires → "Add Managed"

### 8.6 Hive Off Managed Umpire
- **Access:** `umpire_coordinator`, `admin`
- **Path:** `/umpires/<id>/hive-off`
- **Actions:**
  - Convert managed umpire to independent account
  - Create new user account with their own email
  - Transfer profile to new account (preserves history)
  - Option to send welcome email with password setup
- **Navigation:** Umpire Profile → "Create Independent Account"

### 8.7 Umpire Guardian Management
- **Access:** `umpire_coordinator`, `admin`
- **Path:** Via umpire edit page
- **Actions:**
  - View guardians linked to managed umpires
  - Parents can manage multiple children's umpire profiles
  - Switch between managed profiles in umpire portal
- **Navigation:** Umpire Profile → Edit → Guardian section

### 8.8 Assignr Integration Dashboard
- **Access:** `umpire_coordinator`, `admin`
- **Path:** `/umpires/assignr/`
- **URL Args:** `?start=YYYY-MM-DD`, `?end=YYYY-MM-DD`
- **Actions:**
  - View games from Assignr API with umpire assignments
  - See summary stats for SDL-managed games only (total, assigned, unassigned, active umpires)
  - View delegated games summary (games assigned to partners with unpublished count)
  - View games by league breakdown (SDL-managed only)
  - View top umpires with game counts
  - Urgent games section (within 2 weeks, need umpires, unassigned, SDL-managed only)
  - Set umpire source (SDL, DIA, DYN) directly from page
  - Set umpire count override
  - Games linked to local database highlighted
  - **Assignr Publish/Unpublish Integration:**
    - Changing source TO SDL automatically publishes game in Assignr (officials can see/claim)
    - Changing source FROM SDL automatically unpublishes game in Assignr (officials cannot see)
    - Confirmation dialog warns when removing from SDL about unpublishing
- **Navigation:** Dashboard → "Umpires" → "Assignr"

### 8.9 Assignr Games List
- **Access:** `umpire_coordinator`, `admin`
- **Path:** `/umpires/assignr/games`
- **URL Args:** `?start=YYYY-MM-DD`, `?end=YYYY-MM-DD`, `?league=`
- **Actions:**
  - View all Assignr games in date range
  - Filter by league (client-side)
  - Filter by assignment status (assigned/unassigned)
  - See accepted umpire names from Assignr
  - Set umpire source and count directly
  - Red highlighting for games needing umpires but unassigned
  - Link to local game edit page for synced games
- **Navigation:** Assignr Dashboard → "View All Games"

### 8.10 Assignr Sync Status
- **Access:** `umpire_coordinator`, `admin`
- **Path:** `/umpires/assignr/sync-status`
- **Actions:**
  - See which games are synced between Assignr and local database
  - Identify games in Assignr but not linked locally
  - Identify local games not in Assignr
  - Troubleshoot sync issues
- **Navigation:** Assignr Dashboard → "Sync Status"

### 8.11 Missing Umpire Lookup
- **Access:** `umpire_coordinator`, `admin`
- **Path:** `/umpires/missing-umpire` or `/umpires/missing-umpire/<date>`
- **Actions:**
  - Quick lookup for when a field reports missing umpire
  - See all games for a given day
  - View umpire source assignment for each game
  - One-click copy of partner contact info for SMS
  - Filter by field and league (client-side)
  - Mobile-friendly with expandable rows
  - Red highlighting for games needing umpires
- **Navigation:** Dashboard → "Umpires" → "Missing Umpire"

### 8.12 Delegation Rules
- **Access:** `umpire_coordinator`, `admin`
- **Path:** `/umpires/delegation`
- **Actions:**
  - Set rules for automatic umpire partner assignment
  - Configure percentage allocations per partner per league
  - Set priority order for partners
- **Navigation:** Dashboard → "Umpires" → "Delegation Rules"

### 8.13 Delegation Report
- **Access:** `umpire_coordinator`, `admin`
- **Path:** `/umpires/delegation/report`
- **Actions:**
  - View game counts by partner and league
  - See cost estimates based on umpire counts
  - Track actual vs. allocated assignments
- **Navigation:** Dashboard → "Umpires" → "Delegation Report"

### 8.14 Weekly Digests
- **Access:** `umpire_coordinator`, `admin`
- **Path:** `/umpires/<year>/<is_spring>/digests`
- **Actions:**
  - View weekly digest emails for umpire partners
  - Preview digest content before sending
  - Send weekly assignment summaries
- **Navigation:** Dashboard → "Umpires" → "Weekly Digests"

---

## 9. Umpire Portal (Self-Service)

### 9.1 Umpire Dashboard
- **Access:** `umpire`
- **Path:** `/umpire-portal/`
- **Actions:**
  - View upcoming assigned games
  - See games available to claim
  - Quick access to all portal functions
- **Navigation:** Dashboard → "Umpire Portal" (visible only to umpires)

### 9.2 Available Games
- **Access:** `umpire`
- **Path:** `/umpire-portal/available`
- **Actions:**
  - View all open game slots
  - Filter by date, league
  - Claim available games
- **Navigation:** Umpire Portal → "Available Games"

### 9.3 My Games
- **Access:** `umpire`
- **Path:** `/umpire-portal/my-games`
- **Actions:**
  - View all claimed/assigned games
  - See game details (date, time, field, teams)
  - Release games (with restrictions)
- **Navigation:** Umpire Portal → "My Games"

### 9.4 Claim Game
- **Access:** `umpire`
- **Path:** POST `/umpire-portal/claim/<game_id>`
- **Actions:**
  - Claim an open umpire slot
  - Receive confirmation
- **Navigation:** Available Games → "Claim"

### 9.5 Release Game
- **Access:** `umpire`
- **Path:** POST `/umpire-portal/release/<game_id>`
- **Actions:**
  - Release a claimed game
  - **Restriction:** Cannot release within 24 hours of game time
- **Navigation:** My Games → "Release"

### 9.6 Umpire History
- **Access:** `umpire`
- **Path:** `/umpire-portal/history`
- **Actions:**
  - View past games worked
  - See game details and pay status
- **Navigation:** Umpire Portal → "History"

### 9.7 Umpire Pay
- **Access:** `umpire`
- **Path:** `/umpire-portal/pay`
- **Actions:**
  - View pay history
  - See pending payments
  - View total earnings
- **Navigation:** Umpire Portal → "Pay"

### 9.8 Umpire Profile
- **Access:** `umpire`
- **Path:** `/umpire-portal/profile`
- **Actions:**
  - View profile information
  - Update availability preferences
- **Navigation:** Umpire Portal → "Profile"

---

## 10. Public Schedules

### 10.1 Team Schedule (Public)
- **Access:** `public` (with token)
- **Path:** `/s/team/<token>`
- **Actions:**
  - View team's full schedule (games and practices)
  - See game details (date, time, field, opponent)
  - Color-coded by game type
  - Link to field directions
- **Navigation:** Shared via URL/link from coach

### 10.2 Division Schedule (Tiered Access)
- **Access:** Tiered (see below)
- **Path:** `/s/division/<token>`
- **Actions by Access Level:**
  - **Not logged in:** Landing page with login link
  - **Coach in division:** Full schedule view, logout-only menu
  - **Admin/Scheduler/Umpire Coordinator:** Full schedule view, full menu
  - **Other logged-in users:** "Request Access" form
- **Features:**
  - View all games and practices in division
  - Filter by team, field, date, game type (client-side)
- **Navigation:** Shared via URL from league coordinator

### 10.3 Division Landing (Not Logged In)
- **Access:** `public` (with token)
- **Path:** `/s/division/<token>` (when not authenticated)
- **Actions:**
  - See league/division name
  - Click to login (redirects back after)
  - Link to password reset
- **Navigation:** Direct URL access

### 10.4 Division Request Access
- **Access:** `authenticated` (without division access)
- **Path:** `/s/division/<token>/request-access`
- **Actions:**
  - Submit access request with message
  - Request sent to scheduling coordinator
- **Navigation:** Division Schedule → "Request Access" (if not authorized)

### 10.5 GameChanger Manager
- **Access:** Coach in division, `scheduler`, `admin`
- **Path:** `/s/division/<token>/gamechanger`
- **Actions:**
  - View GameChanger setup instructions
  - Copy schedule URL for GameChanger import
  - Download CSV for manual import
- **Navigation:** Division Schedule → "GameChanger"

### 10.6 GameChanger CSV Download
- **Access:** Coach in division, `scheduler`, `admin`
- **Path:** `/s/division/<token>/gamechanger.csv`
- **Actions:**
  - Download schedule in GameChanger-compatible format
  - Includes all games and scrimmages (not practices)
- **Navigation:** GameChanger Manager → "Download CSV"

### 10.7 Partner Schedule (Umpire Orgs)
- **Access:** `public` (with token)
- **Path:** `/s/partner/<token>`
- **URL Args:** `?changes_since=YYYY-MM-DD` to filter by recent changes
- **Actions:**
  - View schedule designed for partner organizations
  - Filter by league, field, date (client-side)
  - Filter by "changes since" date (server-side) - shows only games modified after specified date
  - See umpire requirements per game
  - Displays banner showing count of changes when filter active
- **Navigation:** Shared via URL from umpire coordinator

### 10.8 Record Game Start Time
- **Access:** API endpoint
- **Path:** POST `/s/record-start`
- **Actions:**
  - Record actual game start time
  - Used for GameChanger integration
- **Navigation:** Called programmatically

---

## 11. Reports

### 11.1 Reports Index
- **Access:** `authenticated`
- **Path:** `/reports/`
- **Actions:**
  - Access all available reports
- **Navigation:** Dashboard → "Reports"

### 11.2 Recent Changes
- **Access:** `authenticated`
- **Path:** `/reports/recent-changes`
- **Actions:**
  - View game changes in past N days
  - Filter by league, change type, user
  - See what was changed and by whom
- **Navigation:** Reports → "Recent Changes"

### 11.3 Game History
- **Access:** `authenticated`
- **Path:** `/reports/game/<game_id>/history`
- **Actions:**
  - View complete change log for a specific game
  - See all modifications with timestamps
- **Navigation:** Game detail → "View History"

### 11.4 Umpire Changes Report
- **Access:** `scheduler`, `admin`
- **Path:** `/reports/umpire-changes`
- **Actions:**
  - View changes affecting games assigned to specific umpire
  - Filter by umpire and date range
  - Useful for notifying umpires of schedule changes
- **Navigation:** Reports → "Umpire Changes"

### 11.5 My Changes
- **Access:** `authenticated`
- **Path:** `/reports/my-changes`
- **Actions:**
  - View changes made by current user
  - Personal audit trail
- **Navigation:** Reports → "My Changes"

### 11.6 Schedule Downloads
- **Access:** `authenticated`
- **Path:** `/reports/schedule-downloads`
- **Actions:**
  - Download league schedules as CSV
  - Select season and league
  - Includes games and scrimmages (not practices)
- **Navigation:** Reports → "Schedule Downloads"

### 11.7 Download League Schedule CSV
- **Access:** `authenticated`
- **Path:** `/reports/schedule-download/<year>/<is_spring>/<league>`
- **Actions:**
  - Download CSV file for specific league
  - Columns: Date, Day, Time, Type, Field, Home Team, Away Team
- **Navigation:** Schedule Downloads → Click league → "Download"

---

## 12. Admin & User Management

### 12.1 User List
- **Access:** `admin`
- **Path:** `/admin/users`
- **Actions:**
  - View all users
  - Filter by role, status
  - Search by name/email
- **Navigation:** Dashboard → "Admin" → "Users"

### 12.2 Add User
- **Access:** `admin`
- **Path:** `/admin/users/add`
- **Actions:**
  - Create new user account
  - Set name, email, phone
  - Set initial role(s)
  - Option to send welcome email with password link
- **Navigation:** Users → "Add User"

### 12.3 Edit User
- **Access:** `admin`
- **Path:** POST `/admin/users` (action=edit)
- **Actions:**
  - Change user email
  - Change user name
  - Change user phone
  - Change user roles (except your own)
- **Navigation:** Users → Click user → Edit form

### 12.4 Send Password Reset
- **Access:** `admin`
- **Path:** POST `/admin/users` (action=send_reset)
- **Actions:**
  - Send password reset email to user
  - User receives link to set new password
- **Navigation:** Users → Click user → "Send Reset"

### 12.5 Activate/Deactivate User
- **Access:** `admin`
- **Path:** POST `/admin/users` (action=toggle_active)
- **Actions:**
  - Deactivate user (prevents login)
  - Reactivate user
  - Cannot deactivate yourself
- **Navigation:** Users → Click user → "Deactivate" / "Activate"

### 12.6 Add Coach Role
- **Access:** `admin`
- **Path:** POST `/admin/users` (action=add_coach)
- **Actions:**
  - Add user to coaches table
  - Set sport (baseball, softball, both)
  - Enables coach functionality
- **Navigation:** Users → Click user → "Add as Coach"

### 12.7 Bulk Import Users
- **Access:** `admin`
- **Path:** `/admin/users/import`
- **Actions:**
  - Paste data from spreadsheet (tab or comma separated)
  - Preview parsed data before import
  - Edit roles for all or individual users
  - Set default role for batch (e.g., umpire, coach)
  - Validates email uniqueness (case-insensitive)
  - Creates accounts and optionally sends welcome emails
- **Navigation:** Users → "Import Users"

---

## 13. Notification Queue

### 13.1 Notification Queue
- **Access:** `scheduler`, `admin`
- **Path:** `/notifications/queue`
- **Actions:**
  - View pending notifications
  - See notification type and recipients
  - Preview notification content
- **Navigation:** Dashboard → "Notifications" → "Queue"

### 13.2 Send Notifications
- **Access:** `scheduler`, `admin`
- **Path:** POST `/notifications/send`
- **Actions:**
  - Send all pending notifications
  - Send specific notification types
  - Send individual notifications
- **Navigation:** Queue → "Send All" / "Send"

### 13.3 Preview Notification
- **Access:** `scheduler`, `admin`
- **Path:** `/notifications/preview/<id>`
- **Actions:**
  - View notification content before sending
  - See recipient list
- **Navigation:** Queue → "Preview"

### 13.4 Skip Notification
- **Access:** `scheduler`, `admin`
- **Path:** POST `/notifications/skip/<id>`
- **Actions:**
  - Mark notification as skipped (won't be sent)
- **Navigation:** Queue → "Skip"

---

## 14. Coach Functions

### 14.1 Team Schedule (Authenticated)
- **Access:** `coach` (for their teams)
- **Path:** `/s/team/<token>` (when logged in)
- **Actions:**
  - Full schedule view
  - May have additional team management features
- **Navigation:** Dashboard → Team card → "Schedule"

### 14.2 Coach Assignment
- **Access:** Via team management
- **Path:** Managed through `/seasons/.../teams`
- **Actions:**
  - Coaches are assigned by schedulers/admins
  - Coach role enables team schedule access
- **Navigation:** N/A (managed by admin)

---

## 15. Facilities Management

### 15.1 Facilities Dashboard
- **Access:** `facilities`, `fieldCaptain`, `admin`
- **Path:** `/facilities/`
- **Actions:**
  - View facilities overview
  - Access field schedules and captain management
  - Field captains see their assigned fields
- **Navigation:** Dashboard → "Facilities"

### 15.2 Field Schedules
- **Access:** `facilities`, `fieldCaptain`, `admin`
- **Path:** `/facilities/field-schedules`
- **Actions:**
  - View field usage schedules (placeholder)
- **Navigation:** Facilities → "Field Schedules"

### 15.3 Manage Field Captains
- **Access:** `facilities`, `admin`
- **Path:** `/facilities/captains`
- **Actions:**
  - View all fields with assigned captains
  - See which fields don't have captains (highlighted)
  - Search for users to assign as captains
  - Auto-add fieldCaptain role when assigning
  - Remove captain assignments
- **Navigation:** Facilities → "Field Captains"

### 15.4 Assign Field Captain
- **Access:** `facilities`, `admin`
- **Path:** POST `/facilities/captains/assign`
- **Actions:**
  - Assign a user as captain of a specific field
  - Automatically adds fieldCaptain role if user doesn't have it
  - Multiple captains can be assigned to one field
- **Navigation:** Field Captains → Search user → "Assign"

### 15.5 Remove Field Captain
- **Access:** `facilities`, `admin`
- **Path:** POST `/facilities/captains/remove`
- **Actions:**
  - Remove a captain from a field
  - Does not remove the fieldCaptain role from user
- **Navigation:** Field Captains → Click × next to captain name

### 15.6 Field Schedules View
- **Access:** `facilities`, `fieldCaptain`, `admin`
- **Path:** `/facilities/field-schedules`
- **Actions:**
  - View games and practices scheduled at assigned fields
  - Filter by date range (start date, optional end date)
  - Filter by specific fields (client-side checkboxes)
  - Toggle "Show Cancellations" to see cancelled games (hidden by default)
  - Report field issues (sends email to scheduler + facilities coordinator)
- **Navigation:** Facilities → "Field Schedules"

### 15.7 Report Field Issue
- **Access:** `facilities`, `fieldCaptain`, `admin`
- **Path:** POST `/facilities/field-schedules/report-issue`
- **Actions:**
  - Submit field condition report (standing water, equipment damage, etc.)
  - Sends email to both scheduling@sdll.org and facilities@sdll.org
  - Includes reporter info and field details
- **Navigation:** Field Schedules → "Report Issue" button on field card

---

## 16. Product Admin Analytics

### 16.1 Analytics Dashboard
- **Access:** `product_admin` (via PRODUCT_ADMIN_EMAILS environment variable)
- **Path:** `/analytics/`
- **Actions:**
  - View usage analytics summary cards:
    - Total page views (last 30 days) with % change vs prior period
    - Unique sessions with % change
    - Active authenticated users with % change
    - Average time on page
  - View daily traffic trend chart (7/30/90 day options)
  - Filter by route/page type
  - View top routes table with views, sessions, avg time
  - View top authenticated users table
  - View device breakdown (mobile/tablet/desktop)
  - Product admin views are excluded from counts
- **Navigation:** Direct URL access `/analytics/` (no menu link - product admin only)

---

## Quick Reference: Navigation Paths

| Feature | Role | Navigation Path |
|---------|------|-----------------|
| Dashboard | Any | Click logo or "Dashboard" |
| Season Settings | Scheduler+ | Dashboard → Season dropdown → "Season Overview" |
| Manage Teams | Scheduler+ | Season Overview → "Manage Teams" |
| Field Management | Scheduler+ | Dashboard → "Fields" |
| Game Calendar | Scheduler+ | Dashboard → "Games" → "Calendar" |
| Generate Schedule | Scheduler+ | Dashboard → "Scheduler" → "Generate" |
| Umpire Calendar | Ump Coord+ | Dashboard → "Umpires" |
| Umpire Portal | Umpire | Dashboard → "Umpire Portal" |
| Reports | Any | Dashboard → "Reports" |
| User Management | Admin | Dashboard → "Admin" → "Users" |
| Bulk Import Users | Admin | Dashboard → "Admin" → "Users" → "Import Users" |
| Notifications | Scheduler+ | Dashboard → "Notifications" |
| League Settings | Scheduler+ | Dashboard → "Leagues" |
| Facilities | Facilities/FieldCaptain | Dashboard → "Facilities" |
| Field Captains | Facilities/Admin | Facilities → "Field Captains" |
| Field Schedules | Facilities/FieldCaptain | Facilities → "Field Schedules" |
| Master Schedule | Board/Coordinators | "Master Schedule" in top nav |
| Managed Umpires | Ump Coord+ | Umpires → "Add Managed" |
| Analytics Dashboard | Product Admin | Direct URL `/analytics/` |

---

## Feature Matrix by Role

| Feature | Public | Coach | Umpire | Ump Coord | Scheduler | Facilities | FieldCaptain | Admin |
|---------|--------|-------|--------|-----------|-----------|------------|--------------|-------|
| View Team Schedule | ✓* | ✓* | - | - | ✓ | - | - | ✓ |
| View Division Schedule | ✓** | ✓*** | - | ✓ | ✓ | - | - | ✓ |
| Umpire Portal | - | - | ✓ | - | - | - | - | - |
| Manage Umpire Assignments | - | - | - | ✓ | ✓ | - | - | ✓ |
| Manage Managed Umpires | - | - | - | ✓ | - | - | - | ✓ |
| Edit Games | - | - | - | - | ✓ | - | - | ✓ |
| Generate Schedule | - | - | - | - | ✓ | - | - | ✓ |
| Manage Teams | - | - | - | - | ✓ | - | - | ✓ |
| Manage Fields | - | - | - | - | ✓ | - | - | ✓ |
| Manage Users | - | - | - | - | - | - | - | ✓ |
| Bulk Import Users | - | - | - | - | - | - | - | ✓ |
| Send Notifications | - | - | - | - | ✓ | - | - | ✓ |
| View Reports | - | - | - | - | ✓ | - | - | ✓ |
| Facilities Dashboard | - | - | - | - | - | ✓ | ✓ | ✓ |
| Manage Field Captains | - | - | - | - | - | ✓ | - | ✓ |
| View Field Schedules | - | - | - | - | - | ✓ | ✓ | ✓ |
| Master Schedule | - | - | - | ✓ | ✓ | ✓ | - | ✓***** |
| Analytics Dashboard | - | - | - | - | - | - | - | ✓**** |

\* With valid token
\** Landing page only
\*** If coach in that division
\**** Requires email in PRODUCT_ADMIN_EMAILS env var
\***** Also available to BoardExec, BB_VP, SB_VP, BBPlayerAgent, SBPlayerAgent, coaching_coordinator, treasurer

---

## Maintaining This Document

When adding new routes or features:
1. Add entry to appropriate section
2. Include access level, path, actions, and navigation
3. Update feature matrix if needed
4. Update quick reference navigation paths

Last updated: September 4, 2026
