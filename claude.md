

# PROJECT BOOT SEQUENCE

When starting work in this repo:

1. Read this file fully first.
2. Then list the directory tree (depth 2–3 max).
3. Identify all top-level folders and all `.md` files.
4. Read ONLY the following files next:
   - *.md
5. Build a mental map of:
   - purpose of each folder
   - key abstractions
   - data flow / system flow
6. Before editing anything, summarize understanding back to user.

# Purpose

This project is to build a web-application that I can deploy to manage our Little League.

# Documentation Reference

## ThingsWeCanDoNow.md

The `ThingsWeCanDoNow.md` file is a comprehensive inventory of every capability in the SDLL web application. It serves as:

1. **Feature Reference** - Lists every route and action available in the system
2. **Access Control Documentation** - Tags each feature with required roles (admin, scheduler, coach, umpire, etc.)
3. **Navigation Guide** - Documents how to reach each feature from the dashboard
4. **Onboarding Resource** - Helps new administrators understand what the system can do

**Maintenance:** When adding new routes or features, update ThingsWeCanDoNow.md with:
- Access level (which roles can use it)
- Path (URL pattern)
- Actions (what users can do)
- Navigation (how to get there from the UI)

# High-Level Criteria

I want to use Green/Red TDD for this project; our color palette is orange and forest green; i would like a python script that I can run to verify that the project is working as expected and that all tasks are being executed successfully. 

# Eventual deployment

This is going to be a public facing website (southdurhamlittleleague.org) that league admins will be able to log in to. Plan for it to be deployed (possibly via Vercel); I'm agnostic about hosting, but I would like the hosting costs to be under $300 per year.

# LocalHost

This should be deployed to port 8084 locally. Note that we are running on Windows 11

## Debugging Errors on Localhost

**IMPORTANT:** When testing new code on localhost and encountering errors, always check the `sdll_app_errors` database table. Server console output may not capture all errors, but the app logs unhandled exceptions to this table.

### Quick Error Check Query

```python
# Run this to see recent errors:
cd "C:\Users\zcapo\Documents\workspace\claude\SDLLApp"
python -c "
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    result = db.session.execute(db.text('SELECT * FROM sdll_app_errors ORDER BY created_at DESC LIMIT 5'))
    rows = result.fetchall()
    for row in rows:
        print('---')
        for i, col in enumerate(result.keys()):
            print(f'{col}: {row[i]}')
"
```

### What's Logged

The `sdll_app_errors` table captures:
- `error_type`: Exception class name (e.g., `AttributeError`, `KeyError`)
- `error_message`: The exception message
- `traceback`: Full stack trace with file paths and line numbers
- `request_path`: The URL that triggered the error
- `request_method`: GET, POST, etc.
- `created_at`: When the error occurred

### When to Check

Always check this table when:
- A page returns a 500 error
- The browser shows an error page
- New code isn't working as expected
- Server console output doesn't show the error

# Database

I have dumped the current database that I'm using in a command-line project to Dump20260702.sql; if it makes sense, it would be good to be able to spin up a local DB for testing that incorporates this information and linkages.

## CRITICAL: MySQL Compatibility

**Production uses MySQL (Railway), NOT MariaDB.** When writing SQL migrations:

### DO NOT USE (MariaDB-only syntax):
- `ADD COLUMN IF NOT EXISTS` - MariaDB only
- `DROP COLUMN IF EXISTS` - MariaDB only
- `ALTER TABLE ... IF EXISTS` - MariaDB only

### USE INSTEAD (MySQL-compatible):
```sql
-- Plain ALTER TABLE (will error if column exists, which is fine)
ALTER TABLE table_name ADD COLUMN column_name VARCHAR(100) DEFAULT NULL;

-- Or use separate statements and run with --force flag to continue on errors
mysql --force database < migration.sql
```

### Why This Matters
MariaDB syntax errors will fail silently in development (if using MariaDB locally) but crash in production (MySQL on Railway). Always test migrations against MySQL or use only standard MySQL syntax.

## Model Conventions (IMPORTANT - Read Before Querying)

**CRITICAL: Always read the actual model file before writing queries.** Field names and patterns vary across models.

### User Model (`app/models/user.py`)

| What you might assume | Actual field/pattern |
|-----------------------|---------------------|
| `user.id` | `user.ID` (uppercase) |
| `user.roles` | `user.role` (singular, pipe-delimited string like `"admin\|scheduler"`) |
| `user.status == 'active'` | `user.active == 1` (SmallInteger 0/1) |
| `user.email` directly | Use property `user.email` - stored encrypted as `_email` |

```python
# WRONG
User.query.filter(User.roles.contains('admin'))
User.query.filter(User.status == 'active')

# CORRECT
User.query.filter(User.role.contains('admin'), User.active == 1)

# For role checking, prefer the method:
user.has_role('admin', 'scheduler')  # OR logic - returns True if user has either
user.roles_list  # Returns ['admin', 'scheduler'] as list
```

### Encrypted Fields Pattern (User, UmpireProfile, AccessRequest)

PII fields are encrypted at rest:
- Stored with underscore prefix: `_email`, `_name`, `_phone`
- Access via property without underscore: `user.email`, `user.name`
- **Cannot query encrypted values directly** - use hash columns for lookup

```python
# WRONG - will search encrypted gibberish
User.query.filter(User._email == 'test@example.com')

# CORRECT - use hash lookup
User.get_by_email('test@example.com')  # Uses email_hash column
```

### OrgSeason Model (`app/models/org_season.py`)

| What you might assume | Actual field/pattern |
|-----------------------|---------------------|
| `org_season.id` | `org_season.ID` (uppercase) |
| `is_spring=True` | `is_spring=1` (SmallInteger 0/1) |

```python
# CORRECT
OrgSeason.query.filter_by(year=2026, is_spring=1)  # Spring
OrgSeason.query.filter_by(year=2026, is_spring=0)  # Fall
```

### ID Naming Inconsistency

Some models use uppercase `ID`, others lowercase `id`. Check the model:
- `User.ID`, `OrgSeason.ID`, `Game.ID` - uppercase
- Newer models may use lowercase `id`

Foreign keys also vary: `user_id` vs `user_ID` - always check.

### Boolean vs SmallInteger

Some "boolean" fields are actually `SmallInteger(0/1)`:
- `User.active` - SmallInteger
- `OrgSeason.is_spring` - SmallInteger
- `OrgSeason.is_current` - SmallInteger

Newer models may use `db.Boolean` which works with Python `True`/`False`.

### Quick Reference: Common Gotchas

| Model | Gotcha |
|-------|--------|
| User | `role` not `roles`, `active` not `status`, encrypted PII |
| OrgSeason | `is_spring` is 0/1 not boolean, `ID` uppercase |
| Game | Check relationship names vs foreign key names |
| TeamSeason | `team_ID` not `team_id` for primary key |

**Rule: When in doubt, read the model file first.**

# Sending Updates to admins

Review `sendMessage.md` for instructions on keeping admins up to date on progress or otherwise sending out emails and text messages

# Development Guidelines

## Scroll-Back After Form Submissions

When a page has forms that submit and redirect back to the same page (common pattern for inline editing), the page MUST scroll back to where the user made the edit. This provides better UX by not forcing users to scroll back down after every edit.

### Implementation Pattern

1. **Route**: Track which element was edited and append an anchor to the redirect URL
   ```python
   if request.method == 'POST':
       action = request.form.get('action')
       anchor = None  # Track which element to scroll to

       if action == 'update_item':
           item_id = int(request.form.get('item_id'))
           # ... do the update ...
           anchor = f'item-{item_id}'

       redirect_url = url_for('blueprint.route_name')
       if anchor:
           redirect_url += f'#{anchor}'
       return redirect(redirect_url)
   ```

2. **Template**: Add IDs to the elements that can be edited
   ```html
   {% for item in items %}
   <tr id="item-{{ item.id }}">
       <!-- form fields here -->
   </tr>
   {% endfor %}
   ```

### Pages with Scroll-Back Implemented
- Field Properties (`/fields/properties`) - `#field-{id}`
- Field Time Restrictions (`/fields/time-restrictions`) - `#field-{id}`
- Field Allocations (`/fields/allocations/<year>/<is_spring>/manage`) - `#field-{id}`
- Fields Index (`/fields/`) - `#field-{id}`
- Schedule Settings (`/seasons/<year>/<is_spring>/schedule-settings`) - `#league-{id}`
- Manage Leagues (`/seasons/<year>/<is_spring>/leagues`) - `#league-{id}`
- Manage Teams (`/seasons/<year>/<is_spring>/teams`) - `#league-{name}`
- Manage Playoffs (`/seasons/<year>/<is_spring>/playoffs/<league>`) - `#placeholder-{id}`, `#seeds-section`, `#brackets-section`

### When Adding New Forms
Any new page with inline editing that redirects to itself MUST implement scroll-back following this pattern.

## Client-Side Filtering (No Page Reloads)

When a page has filter controls (dropdowns, date pickers, search boxes), filtering MUST be done client-side using JavaScript/CSS rather than triggering page reloads. This provides instant feedback and better UX.

### When to Use Client-Side Filtering
- Filtering data that's already loaded on the page
- Filter dropdowns (league, field, status, etc.)
- Date filters within a pre-loaded date range
- Search/text filters

### When Page Reload is Acceptable
- Changing seasons (different data set entirely)
- Pagination to load more data
- Initial page load with URL parameters

### Implementation Pattern

1. **Template**: Add data attributes to filterable rows
   ```html
   {% for game in games %}
   <tr data-league="{{ game.league }}"
       data-field="{{ game.field_name }}"
       data-date="{{ game.game_date.strftime('%Y-%m-%d') }}">
       <!-- row content -->
   </tr>
   {% endfor %}
   ```

2. **JavaScript**: Filter by hiding/showing rows
   ```javascript
   function applyFilters() {
       var leagueFilter = document.getElementById('league').value.toLowerCase();
       var rows = document.querySelectorAll('tbody tr');

       rows.forEach(function(row) {
           var rowLeague = (row.dataset.league || '').toLowerCase();
           var show = !leagueFilter || rowLeague === leagueFilter;
           row.style.display = show ? '' : 'none';
       });

       // Update URL for bookmarking (without reload)
       var url = new URL(window.location.href);
       if (leagueFilter) url.searchParams.set('league', leagueFilter);
       else url.searchParams.delete('league');
       history.replaceState(null, '', url.toString());
   }

   // Restore filters from URL on page load
   document.addEventListener('DOMContentLoaded', function() {
       var url = new URL(window.location.href);
       var league = url.searchParams.get('league');
       if (league) {
           document.getElementById('league').value = league;
           applyFilters();
       }
   });
   ```

### Pages with Client-Side Filtering
- Umpire Calendar (`/umpires/<year>/<is_spring>/calendar`) - League filter
- Partner Schedule (`/schedule/<token>`) - Field, league, date filters

## Avoiding N+1 Query Problems

**CRITICAL: Never execute database queries inside loops.** This causes N+1 query problems where loading N items requires N+1 database queries instead of 1-2.

### The Problem

```python
# BAD - N+1 queries (1 query for teams + N queries for coaches)
teams = TeamSeason.query.filter_by(year=year).all()
for team in teams:
    print(team.coaches)  # Each access triggers a new query!
```

### The Solution: Eager Loading

Use SQLAlchemy's `joinedload()` to fetch related data in a single query:

```python
# GOOD - 1 query with JOIN
from sqlalchemy.orm import joinedload

teams = TeamSeason.query.filter_by(year=year).options(
    joinedload(TeamSeason.coaches)
).all()

for team in teams:
    print(team.coaches)  # No additional queries - data already loaded
```

### When to Use Eager Loading

Always use `joinedload()` when:
- Accessing relationships in templates (e.g., `team.coaches`, `coach.user`)
- Iterating over a list and accessing related objects
- Displaying lists with related data

### Common Patterns

```python
# Load coaches with their user records
coaches = CoachUser.query.filter_by(status='active').options(
    joinedload(CoachUser.user)
).all()

# Load teams with their assigned coaches
teams = TeamSeason.query.filter_by(year=year).options(
    joinedload(TeamSeason.coaches)
).all()

# Multiple relationships
games = Game.query.filter_by(year=year).options(
    joinedload(Game.home_team),
    joinedload(Game.away_team),
    joinedload(Game.field)
).all()
```

### Warning Signs

If you see code that:
1. Queries inside a `for` loop
2. Accesses `.relationship` in a template loop without prior eager loading
3. Has slow page loads that get worse with more data

...it likely has an N+1 problem. Fix it with `joinedload()`.

## Always Use IDs for Database Lookups

**CRITICAL: Never search database records by name/string when an ID is available.** Names can change, have duplicates, or have subtle formatting differences. IDs are unique, immutable, and indexed.

### The Problem

```python
# BAD - Searching by name string
def get_coach_for_team(team_name: str, year: int):
    team = TeamSeason.query.filter(
        TeamSeason.year == year,
        TeamSeason.team_name == team_name  # Fragile!
    ).first()
    # "Greene" won't match "greene" or "Greene "
```

### The Solution: Use IDs

```python
# GOOD - Lookup by ID
def get_coach_for_team_by_id(team_id: int):
    team = TeamSeason.query.filter_by(team_ID=team_id).first()
    # Always finds the exact team
```

### When This Applies

- Looking up teams: use `team_ID`, not `team_name` or `display_name`
- Looking up users: use `user_id`, not `email` or `name`
- Looking up games: use `game_id` or `assignr_id`, not date/time/field combinations
- Looking up coaches: use `coach_id`, not coach name
- Any cross-table relationship: pass the foreign key ID, not a display value

### Passing IDs Through Layers

When enriching data (e.g., `enrich_games_with_local_data`), always include the relevant IDs alongside display names:

```python
game['_local'] = {
    'home_team': local_game.home_team.computed_display_name,
    'home_team_id': local_game.home_ID,  # Include the ID!
    'away_team': local_game.away_team.computed_display_name,
    'away_team_id': local_game.away_ID,  # Include the ID!
}
```

Then downstream code can use the ID for lookups while still having the display name for UI.

## Blueprint Size Guidelines

**Keep blueprints under 1,000 lines.** Large blueprints become difficult to navigate and maintain.

### Current Blueprint Sizes (Reference)

| Blueprint | Lines | Status |
|-----------|-------|--------|
| `umpires/routes.py` | ~2,200 | ⚠️ Too large - needs splitting |
| `main/routes.py` | ~1,500 | ⚠️ Consider splitting |
| `scheduler/routes.py` | ~800 | ✓ Acceptable |
| `public/routes.py` | ~600 | ✓ Good |

### When to Split a Blueprint

Split a blueprint when:
- It exceeds 1,000 lines
- It handles multiple distinct feature areas
- Related routes could logically group together

### How to Split

1. **Identify logical groupings** - e.g., umpires blueprint could split into:
   - `umpires/management.py` - CRUD for umpire records
   - `umpires/assignments.py` - Game assignment logic
   - `umpires/availability.py` - Blackout dates, preferences
   - `umpires/partners.py` - Partner management and schedules

2. **Create sub-modules** with their own route registrations:
   ```python
   # app/umpires/__init__.py
   from flask import Blueprint

   umpires_bp = Blueprint('umpires', __name__)

   from app.umpires import management, assignments, availability, partners
   ```

3. **Keep shared helpers** in the blueprint's `__init__.py` or a `utils.py`

## Utility Extraction Patterns

**Consolidate repeated utility code into shared modules.** The codebase has several patterns that appear in multiple places.

### Date/Time Parsing

Multiple routes implement their own date parsing. Use centralized utilities:

```python
# app/utils/date_utils.py
from datetime import datetime, date

def parse_date(date_str: str, default=None) -> date:
    """Parse date from form input. Returns default if invalid/empty."""
    if not date_str:
        return default
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return default

def parse_time(time_str: str, default=None) -> datetime.time:
    """Parse time from form input (HH:MM format)."""
    if not time_str:
        return default
    try:
        return datetime.strptime(time_str, '%H:%M').time()
    except ValueError:
        return default
```

### Form Parsing

Use a consistent pattern for extracting form values:

```python
# app/utils/form_utils.py
def get_int(form, key: str, default: int = None) -> int:
    """Safely extract integer from form data."""
    val = form.get(key, '').strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default

def get_bool(form, key: str) -> bool:
    """Extract boolean from checkbox (present = True)."""
    return form.get(key) in ('1', 'true', 'on', 'yes')
```

### Redirect with Anchor

When redirecting after form submission with scroll-back:

```python
# app/utils/redirect_utils.py
from flask import redirect, url_for

def redirect_with_anchor(endpoint: str, anchor: str = None, **kwargs):
    """Redirect to endpoint, optionally appending an anchor."""
    url = url_for(endpoint, **kwargs)
    if anchor:
        url += f'#{anchor}'
    return redirect(url)
```

## View Models and Data Transfer Objects

**Use dataclasses instead of dynamic object creation.** The codebase has patterns of creating ad-hoc objects that are hard to understand and maintain.

### Avoid These Patterns

```python
# BAD - Dynamic object creation with type()
GameRow = type('GameRow', (), {})
row = GameRow()
row.id = game.id
row.date = game.game_date

# BAD - SimpleNamespace
from types import SimpleNamespace
row = SimpleNamespace(id=game.id, date=game.game_date)

# BAD - Plain dict passed to template
row = {'id': game.id, 'date': game.game_date}
```

### Use Dataclasses Instead

```python
# GOOD - Explicit dataclass with type hints
from dataclasses import dataclass
from datetime import date

@dataclass
class GameViewModel:
    id: int
    game_date: date
    home_team: str
    away_team: str
    field_name: str
    status: str

    @classmethod
    def from_game(cls, game: Game) -> 'GameViewModel':
        return cls(
            id=game.ID,
            game_date=game.game_date,
            home_team=game.home_team_rel.name if game.home_team_rel else 'TBD',
            away_team=game.away_team_rel.name if game.away_team_rel else 'TBD',
            field_name=game.field_rel.name if game.field_rel else 'TBD',
            status=game.status
        )
```

### Benefits

- **IDE support** - Autocomplete, type checking
- **Documentation** - Fields are self-documenting
- **Refactoring** - Easy to find all usages
- **Testing** - Can instantiate with known values

## Permission Decorator Standardization

**Use consistent permission checking patterns.** The app has several similar decorators that should be unified.

### Current Decorators

| Decorator | Location | Purpose |
|-----------|----------|---------|
| `@login_required` | Flask-Login | Basic auth check |
| `@admin_required` | `app/utils/auth.py` | Admin role check |
| `@scheduler_required` | `app/utils/auth.py` | Scheduler role check |
| `@role_required(roles)` | `app/utils/auth.py` | Flexible role check |

### Preferred Pattern

Use `@role_required()` for flexibility:

```python
from app.utils.auth import role_required

# Single role
@umpires_bp.route('/manage')
@role_required('admin')
def manage_umpires():
    pass

# Multiple roles (OR logic)
@umpires_bp.route('/calendar')
@role_required('admin', 'umpire_coordinator')
def umpire_calendar():
    pass
```

### Adding New Role Checks

When a new role needs checking, extend `role_required()` rather than creating a new decorator:

```python
# app/utils/auth.py
def role_required(*roles):
    """Require user to have at least one of the specified roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not current_user.has_role(*roles):
                flash('Access denied.', 'error')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

## Service Layer Organization

**Keep business logic in services, not routes.** Routes should handle HTTP concerns (request parsing, response formatting), while services handle business logic.

### Directory Structure

```
app/
  services/
    scheduler_service.py      # Game scheduling logic
    email_service.py          # Email sending
    weekly_digest_service.py  # Digest generation
    field_service.py          # Field availability logic
    ...
```

### What Goes in Services

- Complex business logic
- Database operations beyond simple CRUD
- Calculations and algorithms
- External API integrations
- Operations used by multiple routes

### What Stays in Routes

- Request parsing (`request.form`, `request.args`)
- Response formatting (`render_template`, `jsonify`)
- Flash messages
- Redirects
- Simple CRUD operations

### Example Refactoring

```python
# BEFORE - Logic in route
@bp.route('/schedule/generate', methods=['POST'])
def generate_schedule():
    year = request.form.get('year')
    # 200 lines of scheduling logic...
    return redirect(url_for('scheduler.view'))

# AFTER - Logic in service
@bp.route('/schedule/generate', methods=['POST'])
def generate_schedule():
    year = request.form.get('year')
    result = scheduler_service.generate_schedule(year)
    if result.success:
        flash(f'Generated {result.game_count} games', 'success')
    else:
        flash(result.error, 'error')
    return redirect(url_for('scheduler.view'))
```

## Modular Scheduler Architecture

The `scheduler_service.py` handles multiple distinct concerns. When extending, consider these logical modules:

| Module | Responsibility |
|--------|----------------|
| `slot_generator.py` | Generate available time slots from field allocations |
| `constraint_checker.py` | Validate games against blackouts, conflicts |
| `assignment_engine.py` | Match games to slots optimally |
| `conflict_resolver.py` | Handle and resolve scheduling conflicts |

### Extension Points

When adding new scheduling features:
1. Identify which module the feature belongs to
2. Add to existing module if small, create new if substantial
3. Keep `scheduler_service.py` as the orchestration layer

## Windows Compatibility

**Test format strings on Windows.** Some Python format codes work on Linux/Mac but fail on Windows.

### Known Issues

| Code | Linux/Mac | Windows | Fix |
|------|-----------|---------|-----|
| `%l` | Hour without zero | ❌ Fails | Use `%I` with `.lstrip('0')` |
| `%-d` | Day without zero | ❌ Fails | Use `%d` with `.lstrip('0')` |
| `%-m` | Month without zero | ❌ Fails | Use `%m` with `.lstrip('0')` |

### Safe Pattern

```python
# Cross-platform hour without leading zero
hour = game.game_date.strftime('%I:%M %p').lstrip('0')  # "6:30 PM"

# Cross-platform day without leading zero
day = game.game_date.strftime('%d').lstrip('0')  # "7"
```