# SDLL Web Application - Specification v2

**Version:** 2.0
**Last Updated:** July 15, 2026
**Status:** Phase 2 Complete - Season Setup, Teams, Field Allocations, League Settings, Playoff Placeholders, Game Generation & Field Restrictions

---

## Overview

Our little league uses Google Sheets to manage games and locations. This is fine to start, but once the year starts and changes have to be made (i.e. rainouts), the system becomes very unwieldy. This is for two reasons. First, a change made to the Google Sheet does not easily turn into a notification for all the other stakeholders that need to know about the game change (umpires, coaches, parents). Second (and maybe related), a change to a Google Sheet does not have the capacity for any additional logic (i.e. you have two games scheduled at the same time at the same field).

This web application allows the various stakeholders to better manage the process of in-season game changes. In particular, when a change needs to be made, the site:

1. Allows an approved scheduler to see options for a re-schedule
2. Triggers a series of alerts and other actions to notify other stakeholders of the change

We are currently using Assignr for the umpire communication and assignment part of this; they have an API, so I think it's reasonable to plan on using this system to keep Assignr up to date. Long-term, this may be able to replace Assignr.

---

## Stakeholders

There are several core stakeholders from the SDLL Board of Directors who would actually use the system. There are a bunch of other stakeholders who would get notified as a downstream result of a change made in the site or who may have read-access to the site.

**Scheduler** - This is the person who is responsible for actually making changes to the schedule

**Umpire Coordinator** - The Scheduler is the person responsible for deciding what changes will be made; the Umpire Coordinator is responsible for making sure that the umpires know about the changes

**Coaching Coordinator** - Similar to the Umpire Coordinator, the Coaching coordinator needs to make sure that the coaches are notified of the change so that they can notify their teams

**Other SDLL Board Member** - Down the road, I could imagine other SDLL board members having read access to the site, but this is not important to start

**Coaches** - Coaches probably wouldn't have access to the site, at least if it's just being used for scheduling changes, but they absolutely need to know when a change is made

**Umpires** - Similar to the coaches, they need to be notified when a change is made

**Umpire Organizations** - We manage a pool of umpires (i.e. we know who is going to which game), but we also contract with other organizations that provide umpires (i.e. we do not know which specific umpire they are sending); we may eventually give them a log in to see which games they have coming up

### User Roles (Implemented)

| Role | Permissions |
|------|-------------|
| `admin` | Full access to all features |
| `scheduler` | Create/edit seasons, teams, games, field allocations |
| `umpire_coordinator` | View schedules, manage umpire assignments |
| `viewer` | Read-only access to schedules and games |

---

## Data Model

### Implemented Tables

| Table | Description | Status |
|-------|-------------|--------|
| `sdll_users` | Application users with encrypted PII (Fernet encryption for name, email, phone) | Implemented |
| `sdll_team_seasons` | Teams per season with placeholder support (Seed 1, Winner Game 3, etc.) | Implemented |
| `sdll_games` | Game records with home/away teams, date/time/location, game_type (regular/playoff/practice) | Implemented |
| `sdll_fields` | Field locations with league restrictions (Anyone/Exclude/Only) | Implemented |
| `sdll_field_slots` | Available time slots per field per season with ownership (SDLL vs Away) | Implemented |
| `sdll_leagues` | League definitions with time restrictions (earliest/latest start times) | Implemented |
| `sdll_league_seasons` | Per-season league settings (games/team, playoff format, qualifying teams) | Implemented |

### Planned Tables (Not Yet Implemented)

| Table | Description |
|-------|-------------|
| `sdll_umpires` | Individual umpires who may work our games |
| `sdll_umpire_games` | Umpire-to-game assignments (many-to-many) |
| `sdll_coaches` | Coach records (people) |
| `sdll_coach_seasons` | Coach-to-team-season assignments |
| `sdll_organizations` | Multi-organization support |

### Key Data Model Decisions

**Teams:**
- Teams have two name fields: `display_name` (placeholder like "BB Majors Team 1") and `team_name` (actual name like "Thunderbolts")
- Display priority: team_name > "Team [Coach Last Name]" > placeholder
- Playoff placeholders are special team records: Seeds (Seed 1, Seed 2) and Brackets (Winner Game 1, Loser Game 2)
- `seed_number` column for ordering seeds; `bracket_position` for tournament tracking
- `resolved_team_id` links placeholder to actual team once determined

**Games:**
- `game_type` column: 'regular', 'playoff', 'practice'
- Practice games have `away_ID = null` (single team)
- `home_ID` and `away_ID` are optional - games can exist as slots before teams are assigned
- Games align more closely with field permits than team combinations

**Fields & Slots:**
- Field slots represent available windows (separate from actual scheduled games)
- Slots have ownership: SDLL-owned vs Away (another league's home field)
- Fields have restriction types: Anyone, Exclude (blacklist), Only (whitelist)

---

## Scheduling Workflow

There are four stages to scheduling:

### Stage 1: Teams
Prior to the draft, we identify the number of teams based on the number of registered players. Those teams have head coaches and contact information, but no names. We just name them based on the league and a number (i.e. BB - A Team 1).

**Implemented:**
- Create teams with placeholder names (auto-numbered)
- Add playoff placeholders (Seed 1, Seed 2, etc.)
- Set actual team names once finalized
- Copy teams from previous season (names reset to placeholders)
- Inter-league game support via team records

### Stage 2: Fields
Around the same time, we get our field allocations from Durham Parks and Rec. We combine that with our other fields and set the times that we have permits.

**Implemented:**
- Field slots per day/time with league restrictions
- Derive slots from historical game data
- Copy allocations from previous season
- Ownership tracking (SDLL vs Away)
- Field league restrictions (Anyone/Exclude/Only)
- League time restrictions (earliest/latest start times for younger leagues)

### Stage 3: Games
We specify a number of games per team per league and whether or not we are going to have playoffs. We need to specify the format of the playoffs to determine the number of games.

**Implemented:**
- Configure games per team (6, 8, 10, 12, 14, 16)
- Generate round-robin regular season matchups
- Playoff format configuration (Single Elimination, Double Elimination, Round Robin + Knockout)
- Auto-generate playoff games using seed placeholders
- Game types: regular, playoff, practice

**Not Yet Implemented:**
- Assign games to specific field slots (date/time/location)
- Balance early vs late game times per team
- Conflict detection (overlapping games at same field)

### Stage 4: In-Season Changes
Throughout the season, reschedules happen due to rain and other stuff. When that happens, the game record remains, but we need to change the date/time/location.

**Game Statuses (Planned):**
- `scheduled` - Game is on the calendar
- `completed` - Game was played
- `postponed` - Rescheduling needed, date TBD
- `cancelled` - Game will not be played

---

## Implicit Knowledge: Scheduler

*This section contains the tribal or implicit knowledge that the scheduler has developed from the day-to-day management of their role.*

### Game Durations

Games can have different set durations (playoff games are going to be longer because they do not have time limits in some divisions). The league specifies ahead of time whether games are no time-limit or a specific time limit; it's ok if a game goes long, but it's not OK to schedule two playoff games in a 5:30 and 7:30 slot if the 5:30 game has no time limit.

### Field Priority Notes

AA/AAA/Majors play all games at Herndon. Each division plays 2 days a week. AA always on Saturday. Others can change.
Intermediate can only play at Cedar Falls 1, Hillside, Parkwood, Pineywood, and Cresset.
Juniors can only play at Githens Baseball and Lowe's Grove Baseball
All other divisions can play anywhere/anytime but there are preferred fields.
Practice only at Shepard if possible.
Cresset can easily hold 2 teams for a practice.
Parkwood can easily hold 2 teams for a practice at 5:30, but not at 7:30.
Githens softball can hold 2 teams for a practice.
Southern Boundaries 1 is a practice only field for everyone due to base path distances.
Any kid pitch team CAN practice at Lowe's Grove baseball or Githens baseball, but they don't prefer it.
Softball Majors prefers to play at Parkwood but we share the space among any division that doesn't use Herndon.
Baseball tee ball only plays at Pearsontown.

**Top Fields:**
Parkwood, Pineywood, Herndon, Southern Boundaries, Hillside

**Mid Range Fields:**
Githens Softball, Alston Ridge, Ephesus, Cedar Falls

**Least Preferred Fields:**
Cresset, Lowe's Grove Softball, Shepard

### Time Restrictions by League (Implemented)

| Leagues | Allowed Times | Implementation |
|---------|---------------|----------------|
| AA, AAA, Majors, Intermediate, SB Minor, SB Major | 5:30 OR 7:30 | No restriction |
| Tee Ball, Rookie SB, Rookie BB, BB A | 5:30 only | `latest_start_time = 17:30` |
| Juniors | 5:30 only | Fields don't have lights |

These restrictions are enforced via `league.can_play_at_time(start_time)` method.

### Setting up a new Season

**Answer (Implemented):** The system supports copying a previous season as a template:
- Field allocations are generally the same (copy allocations feature)
- Number of teams per division varies (adjust after copy)
- Days of the week per league typically stay consistent
- League settings (playoff format, games/team) copy forward
- Seed placeholders auto-generate based on playoff configuration

---

## Implicit Knowledge: Umpire Coordinator

*This section contains the tribal or implicit knowledge that the umpire coordinator has developed from the day-to-day management of their role.*

If we are past the start of the game, we should be calling Marti (Diamond) or Vance (Dynamic) if their umpire has not arrived; they'll need to know which field at which location we are talking about because that's how they look it up in their system.

Umpires don't really care which teams are playing as long as they know the division. It's helpful to communicate the teams and the coach names to the umpire, but if the teams change for their game, that doesn't require an update notification.

---

## Notification System

We don't send a ton of emails, so we use our google email with SMTP and we shouldn't ever hit our daily sending limit. This is primarily for communicating with our umpire partner organizations. For our own umpires that we manage, we use Assignr, and they have an API that can send messages.

We should be able to plug in a Twilio (or an alternative) API key and send text messages as needed. This is better for a last minute message to coaches about an umpire situation or to ask about some sort of scheduling question.

Long-term, we should enable AWS for emails since this could eventually be used to email parents and individual players.

**Status:** Not yet implemented. Part of MVP remaining work.

---

## Technical Implementation

### Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask (Python) |
| Database | MySQL (`sdllapp` database, `lrp_master` user) |
| ORM | SQLAlchemy |
| Authentication | Flask-Login with Werkzeug scrypt hashing |
| PII Encryption | Fernet (at-rest encryption for name, email, phone) |
| Rate Limiting | Flask-Limiter (5 login attempts/minute) |
| CSRF Protection | Flask-WTF |
| Templating | Jinja2 |
| CSS | Custom theme (LR_*.css + sdll_theme.css) |

### Configuration

- **Development:** localhost:8084
- **Sessions:** 3-month expiry, multi-device login allowed
- **Logging:** Configurable via JSON (OFF/ON/EXTREME per action type)
- **Secrets:** `client_secrets.json` with local/web configurations
- **Environment:** `.env` file for database credentials and encryption keys

### Project Structure

```
SDLLApp/
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── config.py             # Dev/Test/Prod configurations
│   ├── extensions.py         # SQLAlchemy, Flask-Login, Limiter, CSRF
│   ├── models/
│   │   ├── user.py           # User model with PII encryption
│   │   ├── team.py           # TeamSeason with playoff placeholders
│   │   ├── game.py           # Game with generation methods
│   │   ├── field.py          # Field with league restrictions
│   │   ├── field_slot.py     # FieldSlot with ownership
│   │   ├── league.py         # League with time restrictions
│   │   └── league_season.py  # LeagueSeason settings
│   ├── auth/routes.py        # Login, logout, password reset
│   ├── main/routes.py        # Dashboard
│   ├── seasons/routes.py     # Season setup, teams, playoffs
│   ├── games/routes.py       # Game list, view, upcoming
│   ├── fields/routes.py      # Field allocations, restrictions
│   ├── utils/
│   │   ├── encryption.py     # Fernet encryption for PII
│   │   └── logging.py        # Configurable logging
│   ├── static/css/           # Stylesheets (green/orange theme)
│   └── templates/            # Jinja2 templates
├── tests/                    # Test suite
├── scripts/                  # Migrations and utilities
├── requirements.txt
├── run.py                    # Dev server entry point
└── Dump20260702.sql          # Database dump
```

### Database Migrations

Run in order for fresh setup:
```bash
mysql -u lrp_master -p < Dump20260702.sql
mysql -u lrp_master -p sdllapp < scripts/create_users_table.sql
mysql -u lrp_master -p sdllapp < scripts/add_team_name_column.sql
mysql -u lrp_master -p sdllapp < scripts/create_field_slots_table.sql
mysql -u lrp_master -p sdllapp < scripts/add_field_slot_ownership.sql
mysql -u lrp_master -p sdllapp < scripts/create_league_seasons_table.sql
mysql -u lrp_master -p sdllapp < scripts/add_playoff_columns.sql
mysql -u lrp_master -p sdllapp < scripts/add_game_type_columns.sql
mysql -u lrp_master -p sdllapp < scripts/add_field_restrictions.sql
mysql -u lrp_master -p sdllapp < scripts/add_league_time_restrictions.sql
```

---

## Features

### Implemented (Phase 1-2)

| Feature | Description | Status |
|---------|-------------|--------|
| **User Authentication** | Login/logout, password reset, session management | Complete |
| **Role-Based Access** | admin, scheduler, umpire_coordinator, viewer | Complete |
| **Dashboard** | Upcoming games, season overview, quick actions | Complete |
| **Season Management** | Create, copy, view, reset seasons | Complete |
| **Team Management** | Add/remove teams, set names, playoff placeholders | Complete |
| **Field Allocations** | Time slots, ownership, derive from games, copy | Complete |
| **League Settings** | Games/team, playoff format, qualifying teams | Complete |
| **Playoff Placeholders** | Seed generation, bracket tracking, resolution | Complete |
| **Game Generation** | Round-robin regular season, playoff games | Complete |
| **Field Restrictions** | Anyone/Exclude/Only per field | Complete |
| **League Time Restrictions** | Earliest/latest start times | Complete |
| **Season Reset** | Delete games/slots/placeholders/teams with cascading | Complete |

### MVP Remaining (Phase 3)

| Priority | Feature | Description |
|----------|---------|-------------|
| **HIGH** | Edit Games | Change date/time/location of existing games |
| **HIGH** | Game Status | Mark games as postponed/cancelled/completed |
| **MED** | Action Queue | Generate notification list when changes are made |
| **MED** | Notifications | Send email/text from the app |
| **LOW** | Add Games | Create new game records (beyond generation) |

### Future Features (Post-MVP)

- CRM for league sponsorships
- Ticket management for field maintenance
- Umpire registration, training, assignment, and communications
- Marketing/social media CMS
- Auto-schedule based on teams, field availability, and constraints
- Parent/player registration and payment
- Assignr API integration

---

## UI/UX

### Design System

| Element | Specification |
|---------|---------------|
| Primary Color | Forest Green (#228B22) |
| Accent Color | Orange (#FF8C00) |
| Season Badges | Green = Spring, Orange = Fall |
| Status Badges | Playoff (gray), Named (green), Pending (yellow) |
| Navigation | Dropdown menus, role-based items |
| Modals | For edit/delete actions (Escape to close) |
| Mobile | Responsive design, core functions phone-friendly |

### Key URLs

| Page | URL |
|------|-----|
| Dashboard | http://localhost:8084/ |
| Season Setup | http://localhost:8084/seasons/setup |
| Copy Season | http://localhost:8084/seasons/copy |
| All Seasons | http://localhost:8084/seasons/ |
| All Games | http://localhost:8084/games/ |
| Field Allocations | http://localhost:8084/fields/allocations |
| Field Restrictions | http://localhost:8084/fields/restrictions |
| League Time Restrictions | http://localhost:8084/leagues/time-restrictions |

---

## Test Users

| Name | Email | Role | Password |
|------|-------|------|----------|
| Janna Price | schedule.sdll@gmail.com | scheduler | changeme123 |
| Zack Capozzi | sdll.umpires@gmail.com | umpire_coordinator | changeme123 |

---

## Deployment

**Target:** Public website at southdurhamlittleleague.org

**Requirements:**
- Hosting costs under $300/year
- SSL/HTTPS support
- Likely Vercel or similar

**Current:** Development on localhost:8084

---

## Development Approach

- **TDD:** Green/Red test-driven development
- **Soft Delete:** Default for all records (active=0), hard delete available
- **Cascading:** Teams deletion cascades to games
- **Idempotent Operations:** Copy/generate can be run multiple times safely

---

## Changelog

### v2.0 (July 2026)
- Phase 2 complete: Season management, field allocations, league settings, playoffs, game generation
- Field and league restrictions implemented
- Season reset with cascading delete options
- Comprehensive copy workflow (season, allocations, league settings, placeholders)

### v1.0 (Initial)
- Original specification document with requirements and vision
