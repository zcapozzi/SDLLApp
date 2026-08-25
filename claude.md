

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

# High-Level Criteria

I want to use Green/Red TDD for this project; our color palette is orange and forest green; i would like a python script that I can run to verify that the project is working as expected and that all tasks are being executed successfully. 

# Eventual deployment

This is going to be a public facing website (southdurhamlittleleague.org) that league admins will be able to log in to. Plan for it to be deployed (possibly via Vercel); I'm agnostic about hosting, but I would like the hosting costs to be under $300 per year.

# LocalHost

This should be deployed to port 8084 locally

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