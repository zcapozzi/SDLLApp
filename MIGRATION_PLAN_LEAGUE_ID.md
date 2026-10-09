# Migration Plan: Replace League Strings with League IDs

## Executive Summary

The current codebase uses string-based `league` fields (e.g., `"BB Majors"`, `"SB 8U"`) throughout the system. This causes recurring issues where:
1. League names differ between spring and fall seasons (e.g., `"BB AA"` vs `"Fall Ball AA"`)
2. String matching fails when names have slight variations
3. The `League.get_by_name()` method is called frequently but can return `None` when names don't match exactly
4. The treasurer/umpire payment calculations fail to find league rates when names mismatch

The solution is to replace string-based `league` fields with `league_id` foreign keys that reference the `sdll_leagues` table.

---

## 1. INVENTORY OF CURRENT LEAGUE STRING USAGE

### 1.1 Database Tables with `league` String Columns

| Table | Column | Type | Purpose | Migration Complexity |
|-------|--------|------|---------|---------------------|
| `sdll_games` | `league` | VARCHAR(30) | Game's league | HIGH - Core table |
| `sdll_team_seasons` | `league` | VARCHAR(50) | Team's league | HIGH - Core table |
| `sdll_league_seasons` | `league` | VARCHAR(50) | Season config for league | HIGH - Core table |
| `sdll_field_slots` | `league` | VARCHAR(50) | Field slot restriction | MEDIUM |
| `sdll_field_allocations_specific` | `league` | VARCHAR(50) | Specific date allocation | MEDIUM |
| `sdll_org_events` | `league` | VARCHAR(50) | Event scope | MEDIUM |
| `sdll_game_changes` | `league` | VARCHAR(50) | Change log snapshot | LOW - Historical |
| `sdll_umpire_payment_events` | `original_league` | VARCHAR(30) | Payment snapshot | LOW - Historical |
| `sdll_umpire_dayof_notifications` | `game_league` | VARCHAR(50) | Notification snapshot | LOW - Historical |
| `sdll_analytics` | `target_leagues` | VARCHAR(200) | Comma-separated names | LOW |
| `sdll_fields` | `restricted_leagues` | VARCHAR(500) | Comma-separated names | LOW |
| `sdll_umpire_profiles` | `excluded_leagues` | VARCHAR(200) | Comma-separated IDs (already uses IDs!) | N/A |
| `sdll_scheduled_emails` | `_leagues` | TEXT | JSON array of names | LOW |

### 1.2 Models with `league` String Fields

| Model | File | Field(s) |
|-------|------|----------|
| `Game` | `app/models/game.py:16` | `league = db.Column(db.String(30))` |
| `TeamSeason` | `app/models/team.py:20` | `league = db.Column(db.String(50))` |
| `LeagueSeason` | `app/models/league_season.py:20` | `league = db.Column(db.String(50))` |
| `FieldSlot` | `app/models/field_slot.py:22` | `league = db.Column(db.String(50))` |
| `FieldAllocationSpecific` | `app/models/field_allocation_specific.py:30` | `league = db.Column(db.String(50))` |
| `OrgEvent` | `app/models/org_event.py:66` | `league = db.Column(db.String(50))` |
| `GameChange` | `app/models/game_change.py:31` | `league = db.Column(db.String(50))` |
| `UmpirePaymentEvent` | `app/models/umpire_payment_event.py:42` | `original_league = db.Column(db.String(30))` |
| `UmpireDayofNotification` | `app/models/umpire_dayof_notification.py:61` | `game_league = db.Column(db.String(50))` |

### 1.3 Tables Already Using `league_id` (Good Examples)

These tables already follow the correct pattern:
- `sdll_umpire_delegation_rules` - `league_id` FK to `sdll_leagues.ID`
- `sdll_partner_league_rates` - `league_id` FK to `sdll_leagues.ID`

### 1.4 Files with `League.get_by_name()` Calls (32 occurrences)

| File | Count | Context |
|------|-------|---------|
| `app/models/game.py` | 2 | `umpire_count` and `rules_url` properties |
| `app/models/org_event.py` | 4 | Team/league sport lookup |
| `app/models/umpire_profile.py` | 1 | Game eligibility check |
| `app/services/umpire_delegation_service.py` | 3 | Delegation rules |
| `app/services/delegation_proposal_service.py` | 2 | Partner rates |
| `app/services/red_flag_service.py` | 1 | League lookup with caching |
| `app/utils/scheduler.py` | 4 | Schedule generation |
| `app/umpires/proposals.py` | 1 | Delegation proposals |
| `app/main/routes.py` | 2 | Dashboard |
| `app/public/routes.py` | 8 | Public schedules |
| `app/coach/routes.py` | 1 | Coach view |
| `app/umpire_portal/routes.py` | 1 | Umpire portal |
| `app/scheduler/routes.py` | 1 | Scheduler view |
| `app/reports/routes.py` | 1 | Reports |

---

## 2. DATA MODEL CHANGES

### 2.1 Add `league_id` Foreign Key Columns

```sql
-- Phase 1: Add nullable league_id columns (no data loss)

ALTER TABLE sdll_games
    ADD COLUMN league_id BIGINT,
    ADD INDEX idx_games_league_id (league_id),
    ADD CONSTRAINT fk_games_league_id
        FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

ALTER TABLE sdll_team_seasons
    ADD COLUMN league_id BIGINT,
    ADD INDEX idx_team_seasons_league_id (league_id),
    ADD CONSTRAINT fk_team_seasons_league_id
        FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

ALTER TABLE sdll_league_seasons
    ADD COLUMN league_id BIGINT,
    ADD INDEX idx_league_seasons_league_id (league_id),
    ADD CONSTRAINT fk_league_seasons_league_id
        FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

ALTER TABLE sdll_field_slots
    ADD COLUMN league_id BIGINT,
    ADD INDEX idx_field_slots_league_id (league_id),
    ADD CONSTRAINT fk_field_slots_league_id
        FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

ALTER TABLE sdll_field_allocations_specific
    ADD COLUMN league_id BIGINT,
    ADD INDEX idx_field_alloc_specific_league_id (league_id),
    ADD CONSTRAINT fk_field_alloc_specific_league_id
        FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

ALTER TABLE sdll_org_events
    ADD COLUMN league_id BIGINT,
    ADD INDEX idx_org_events_league_id (league_id),
    ADD CONSTRAINT fk_org_events_league_id
        FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);
```

### 2.2 Migrate Existing Data

```sql
-- Phase 2: Populate league_id from existing league strings
-- Must handle both spring (display_name) and fall (fall_display_name) names

-- Games table
UPDATE sdll_games g
LEFT JOIN sdll_leagues l ON (
    g.league = l.display_name OR g.league = l.fall_display_name
)
SET g.league_id = l.ID
WHERE g.league IS NOT NULL;

-- Team seasons
UPDATE sdll_team_seasons ts
LEFT JOIN sdll_leagues l ON (
    ts.league = l.display_name OR ts.league = l.fall_display_name
)
SET ts.league_id = l.ID
WHERE ts.league IS NOT NULL;

-- League seasons (critical - this is the configuration table)
UPDATE sdll_league_seasons ls
LEFT JOIN sdll_leagues l ON (
    ls.league = l.display_name OR ls.league = l.fall_display_name
)
SET ls.league_id = l.ID
WHERE ls.league IS NOT NULL;

-- Field slots
UPDATE sdll_field_slots fs
LEFT JOIN sdll_leagues l ON (
    fs.league = l.display_name OR fs.league = l.fall_display_name
)
SET fs.league_id = l.ID
WHERE fs.league IS NOT NULL;

-- Field allocations specific
UPDATE sdll_field_allocations_specific fas
LEFT JOIN sdll_leagues l ON (
    fas.league = l.display_name OR fas.league = l.fall_display_name
)
SET fas.league_id = l.ID
WHERE fas.league IS NOT NULL;

-- Org events
UPDATE sdll_org_events oe
LEFT JOIN sdll_leagues l ON (
    oe.league = l.display_name OR oe.league = l.fall_display_name
)
SET oe.league_id = l.ID
WHERE oe.league IS NOT NULL;
```

### 2.3 Verify Migration and Handle Edge Cases

```sql
-- Check for unmatched leagues (games with league string but no league_id)
SELECT DISTINCT league, COUNT(*) as cnt
FROM sdll_games
WHERE league IS NOT NULL AND league_id IS NULL
GROUP BY league;

-- Check team_seasons
SELECT DISTINCT league, COUNT(*) as cnt
FROM sdll_team_seasons
WHERE league IS NOT NULL AND league_id IS NULL
GROUP BY league;

-- Check league_seasons
SELECT DISTINCT league, COUNT(*) as cnt
FROM sdll_league_seasons
WHERE league IS NOT NULL AND league_id IS NULL
GROUP BY league;
```

---

## 3. CODE CHANGES

### 3.1 Model Changes

**A. `app/models/game.py`**

```python
# ADD:
league_id = db.Column(db.BigInteger, db.ForeignKey('sdll_leagues.ID'))
league_rel = db.relationship('League', foreign_keys=[league_id], lazy='joined')

# DEPRECATE (keep for backward compatibility during transition):
league = db.Column(db.String(30))  # Mark as deprecated

# ADD property for backward-compatible access:
@property
def league_obj(self):
    """Get the League object for this game."""
    return self.league_rel

@property
def league_display_name(self):
    """Get league display name for current season context."""
    if self.league_rel:
        return self.league_rel.get_seasonal_name(self.is_spring)
    return self.league  # Fallback to string during transition
```

**B. `app/models/team.py` (TeamSeason)**

```python
# ADD:
league_id = db.Column(db.BigInteger, db.ForeignKey('sdll_leagues.ID'))
league_rel = db.relationship('League', foreign_keys=[league_id], lazy='joined')

# ADD property:
@property
def league_obj(self):
    return self.league_rel

@property
def league_display_name(self):
    if self.league_rel:
        return self.league_rel.get_seasonal_name(self.is_spring)
    return self.league
```

**C. `app/models/league_season.py`**

```python
# ADD:
league_id = db.Column(db.BigInteger, db.ForeignKey('sdll_leagues.ID'))
league_rel = db.relationship('League', foreign_keys=[league_id], lazy='joined')

# MODIFY get_or_create to use league_id:
@classmethod
def get_or_create(cls, year, is_spring, league_id):
    """Get existing config or create a new one with defaults"""
    config = cls.query.filter_by(
        year=year,
        is_spring=is_spring,
        league_id=league_id,
        active=1
    ).first()
    # ...
```

**D. `app/models/field_slot.py` and `app/models/field_allocation_specific.py`**

Similar pattern - add `league_id` FK and relationship.

### 3.2 Service Changes

**A. `app/services/umpire_delegation_service.py`**

Replace:
```python
league = League.get_by_name(game.league)
```

With:
```python
league = game.league_rel  # Direct relationship access
```

**B. `app/services/assignr_service.py` - `enrich_games_with_local_data`**

Add league_id to the enrichment data:
```python
game['_local'] = {
    'game_id': local_game.ID,
    'league': local_game.league,  # Keep for display
    'league_id': local_game.league_id,  # Add for lookups
    'league_obj': local_game.league_rel,  # Add relationship
    # ... rest
}
```

**C. `app/treasurer/routes.py`**

Replace string-based lookup:
```python
# OLD:
league_lookup = {}
for l in League.get_all_active():
    league_lookup[l.display_name] = l
    if l.fall_display_name:
        league_lookup[l.fall_display_name] = l

league_name = g.get('league', '')
league = league_lookup.get(league_name)
```

With ID-based lookup:
```python
# NEW:
league_lookup = {l.ID: l for l in League.get_all_active()}

league_id = g.get('league_id') or g.get('_local', {}).get('league_id')
league = league_lookup.get(league_id)
```

### 3.3 Route Changes

Files requiring updates (74 files reference league):
- `app/seasons/routes.py` - Season management
- `app/scheduler/routes.py` - Schedule generation
- `app/games/routes.py` - Game management
- `app/public/routes.py` - Public schedules
- `app/umpires/*.py` - Umpire management
- `app/fields/routes.py` - Field allocations
- `app/main/routes.py` - Dashboard
- `app/coach/routes.py` - Coach views
- `app/reports/routes.py` - Reports

Pattern for each:
```python
# OLD:
games = Game.query.filter_by(league='BB Majors', ...)

# NEW:
from app.models.league import League
league = League.get_by_name('BB Majors')  # Only for parsing user input
games = Game.query.filter_by(league_id=league.ID if league else None, ...)
```

### 3.4 Template Changes

Templates that filter by league need updated filter logic:
- `app/templates/games/*.html`
- `app/templates/umpires/*.html`
- `app/templates/scheduler/review.html`
- `app/templates/public/*.html`

Pattern:
```html
<!-- OLD -->
<option value="{{ league.display_name }}">{{ league.display_name }}</option>

<!-- NEW -->
<option value="{{ league.ID }}">{{ league.get_seasonal_name(is_spring) }}</option>
```

---

## 4. EDGE CASES AND SPECIAL HANDLING

### 4.1 Games with No Matching League

For games where `league` string doesn't match any `sdll_leagues` record:
- Set `league_id = NULL`
- Log these for manual review
- Keep `league` string for reference

```python
def migrate_game_league_ids():
    """Data migration script - run once."""
    unmatched = []
    for game in Game.query.filter(Game.league.isnot(None)).all():
        league = League.get_by_name(game.league)
        if league:
            game.league_id = league.ID
        else:
            unmatched.append((game.ID, game.league))
    db.session.commit()
    return unmatched
```

### 4.2 Assignr Integration

Assignr sends league names as strings. The sync logic needs to:
1. Parse incoming league name
2. Look up corresponding `league_id`
3. Store both the name (for reference) and the ID (for joins)

```python
# In Assignr sync:
def match_assignr_league(league_name: str) -> Optional[int]:
    """Map Assignr league name to local league_id."""
    league = League.get_by_name(league_name)
    return league.ID if league else None
```

### 4.3 Historical/Snapshot Tables

These tables store snapshots and should NOT be migrated to FK:
- `sdll_game_changes` - Historical record of what league name was
- `sdll_umpire_payment_events` - Payment snapshot
- `sdll_umpire_dayof_notifications` - Notification snapshot

Keep these as strings - they represent point-in-time data.

### 4.4 Backward Compatibility During Transition

During the transition period (both fields exist):
1. Write to BOTH `league` (string) AND `league_id` (FK)
2. Read from `league_id` first, fall back to `league` string
3. Add deprecation warnings for `league` string access

```python
@property
def league(self):
    """DEPRECATED: Use league_id or league_rel instead."""
    import warnings
    warnings.warn("game.league is deprecated, use game.league_rel", DeprecationWarning)
    return self._league

@league.setter
def league(self, value):
    """DEPRECATED: Set league_id instead."""
    self._league = value
    # Auto-populate league_id
    if value and not self.league_id:
        league = League.get_by_name(value)
        if league:
            self.league_id = league.ID
```

---

## 5. MIGRATION ORDER (Risk Minimization)

### Phase 1: Add Infrastructure (No Breaking Changes)
1. Add `league_id` columns as NULLABLE
2. Add FK constraints and indexes
3. Add relationships to models
4. Add backward-compatible properties
5. **Test:** Verify app still works unchanged

### Phase 2: Populate Data (No Breaking Changes)
1. Run data migration scripts to populate `league_id`
2. Verify all records have `league_id` where applicable
3. Log and review any unmatched records
4. **Test:** Verify data integrity

### Phase 3: Update Write Paths (Dual-Write)
1. Update `Game.create()` / `__init__` to require `league_id`
2. Update form handlers to pass `league_id`
3. Update Assignr sync to set `league_id`
4. Update schedule generation to use `league_id`
5. **Test:** New records have both fields

### Phase 4: Update Read Paths (Incremental)
1. Update queries to use `league_id` instead of `league`
2. Update templates to use `league_id` for filters
3. Update services to use relationships
4. Remove `League.get_by_name()` calls (except for user input parsing)
5. **Test:** All features work with `league_id`

### Phase 5: Cleanup (After Verification)
1. Make `league_id` NOT NULL (after all data migrated)
2. Drop `league` string column (or keep for display only)
3. Remove deprecation fallbacks
4. **Test:** Final verification

---

## 6. TESTING PLAN

### Unit Tests
- Model tests for new relationships
- Query tests with `league_id` filters
- Migration script tests

### Integration Tests
- Schedule generation with `league_id`
- Assignr sync with league matching
- Treasurer reports with `league_id` lookup
- Public schedule pages

### Manual Testing
- Verify all league dropdowns work
- Verify all schedule views display correct league names
- Verify treasurer payment calculations
- Verify umpire delegation by league

---

## 7. CRITICAL FILES FOR IMPLEMENTATION

Priority order:

1. **`app/models/game.py`** - Core game model, needs `league_id` FK and relationship
2. **`app/models/league.py`** - Already has `get_by_name()` - keep for parsing user input
3. **`app/models/team.py`** - TeamSeason needs `league_id` FK
4. **`app/models/league_season.py`** - League configuration, needs `league_id` FK
5. **`app/treasurer/routes.py`** - Currently broken due to league name mismatch - needs ID-based lookup
6. **`app/services/umpire_delegation_service.py`** - Uses `League.get_by_name()` heavily
7. **`app/services/assignr_service.py`** - Enrichment needs to include `league_id`

---

## 8. ESTIMATED EFFORT

| Phase | Effort | Risk |
|-------|--------|------|
| Phase 1: Infrastructure | 2-3 hours | Low |
| Phase 2: Data Migration | 1-2 hours | Medium |
| Phase 3: Write Paths | 4-6 hours | Medium |
| Phase 4: Read Paths | 6-8 hours | High |
| Phase 5: Cleanup | 1-2 hours | Low |

**Total: 14-21 hours of development + testing**

---

## 9. ROLLBACK PLAN

If issues arise:
1. Keep `league` string column populated at all times
2. Revert code to use string-based lookups
3. No data migration needed for rollback since strings are preserved

This is why we keep both fields during transition and only drop the string column in Phase 5 after thorough verification.
