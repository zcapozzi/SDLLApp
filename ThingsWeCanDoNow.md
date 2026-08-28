# SDLL Site Capabilities

This document enumerates every capability available in the South Durham Little League web application. Each feature is tagged with the required access level and includes navigation instructions.

## Access Levels

| Role | Description |
|------|-------------|
| `public` | No login required |
| `authenticated` | Any logged-in user |
| `coach` | Users with coach role (may have limited access to their own teams) |
| `umpire` | Users with umpire role |
| `umpire_coordinator` | Users who manage umpire assignments |
| `scheduler` | Users who can edit schedules and league settings |
| `admin` | Full administrative access |
| `treasurer` | Financial/pay-related access |

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
- **Actions:**
  - View all fields (owned and away)
  - See field properties (lights, irrigation, parking)
  - Quick edit field details
  - Add new field
  - Deactivate/reactivate fields
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
- **URL Args:** `?date=YYYY-MM-DD` to jump to a specific date, `?league=` to filter
- **Actions:**
  - View all games for a single day with full details
  - Filter by league (client-side)
  - Right-click games to assign umpire source (SDL, DIA, DYN)
  - Right-click to set umpire count override
  - Date picker to jump to any date
  - "Today" button for quick access
- **Navigation:** Umpire Calendar → "Day View" button, or click day header in week view

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

### 8.4 Umpire Pay Management
- **Access:** `umpire_coordinator`, `treasurer`, `admin`
- **Path:** `/umpires/pay`
- **Actions:**
  - View games worked by umpires
  - See pay amounts per game
  - Mark games as paid
  - Export pay reports
- **Navigation:** Umpires → "Pay Management"

### 8.5 Umpire Availability Report
- **Access:** `umpire_coordinator`, `scheduler`, `admin`
- **Path:** `/umpires/availability`
- **Actions:**
  - View umpire availability by date
  - See patterns (e.g., who works Saturdays)
  - Identify scheduling gaps
- **Navigation:** Umpires → "Availability Report"

### 8.6 Partner Schedule Management
- **Access:** `umpire_coordinator`, `scheduler`, `admin`
- **Path:** `/umpires/partners`
- **Actions:**
  - View partner organization schedule links
  - Generate/regenerate partner tokens
  - Copy schedule URLs
- **Navigation:** Umpires → "Partner Schedules"

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
- **Actions:**
  - View schedule designed for partner organizations
  - Filter by league, field, date
  - See umpire requirements per game
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
| Notifications | Scheduler+ | Dashboard → "Notifications" |
| League Settings | Scheduler+ | Dashboard → "Leagues" |

---

## Feature Matrix by Role

| Feature | Public | Coach | Umpire | Ump Coord | Scheduler | Admin |
|---------|--------|-------|--------|-----------|-----------|-------|
| View Team Schedule | ✓* | ✓* | - | - | ✓ | ✓ |
| View Division Schedule | ✓** | ✓*** | - | ✓ | ✓ | ✓ |
| Umpire Portal | - | - | ✓ | - | - | - |
| Manage Umpire Assignments | - | - | - | ✓ | ✓ | ✓ |
| Edit Games | - | - | - | - | ✓ | ✓ |
| Generate Schedule | - | - | - | - | ✓ | ✓ |
| Manage Teams | - | - | - | - | ✓ | ✓ |
| Manage Fields | - | - | - | - | ✓ | ✓ |
| Manage Users | - | - | - | - | - | ✓ |
| Send Notifications | - | - | - | - | ✓ | ✓ |
| View Reports | - | - | - | - | ✓ | ✓ |

\* With valid token
\** Landing page only
\*** If coach in that division

---

## Maintaining This Document

When adding new routes or features:
1. Add entry to appropriate section
2. Include access level, path, actions, and navigation
3. Update feature matrix if needed
4. Update quick reference navigation paths

Last updated: August 2026
