"""League helper utilities for query filtering.

These helpers support the migration from league string columns to league_id foreign keys.
They accept both league names (for backwards compatibility) and league IDs.
"""

from flask import request


def get_league_id_from_param(param_value):
    """Convert a league parameter (name or ID) to a league_id.

    Args:
        param_value: Either a league name string or league ID (int or string)

    Returns:
        int: The league ID, or None if not found/invalid
    """
    if not param_value:
        return None

    # Try as ID first (handles both int and string representations)
    try:
        league_id = int(param_value)
        # Verify it exists
        from app.models.league import League
        if League.query.get(league_id):
            return league_id
    except (ValueError, TypeError):
        pass

    # Fall back to name lookup
    from app.models.league import League
    league_obj = League.get_by_name(param_value)
    return league_obj.ID if league_obj else None


def get_league_id_from_request(param_name='league'):
    """Get league_id from request args, accepting either name or ID.

    Args:
        param_name: The query parameter name to look for (default: 'league')

    Returns:
        int: The league ID, or None if not found/invalid
    """
    param_value = request.args.get(param_name)
    return get_league_id_from_param(param_value)


def get_league_id_from_form(param_name='league'):
    """Get league_id from form data, accepting either name or ID.

    Args:
        param_name: The form field name to look for (default: 'league')

    Returns:
        int: The league ID, or None if not found/invalid
    """
    param_value = request.form.get(param_name)
    return get_league_id_from_param(param_value)


def get_leagues_for_dropdown(year=None, is_spring=None, include_all=False):
    """Get leagues for filter dropdowns.

    Returns a list of dicts with 'id', 'name', and 'display_name' for use in templates.

    Args:
        year: Optional year to filter by season
        is_spring: Optional is_spring flag to filter by season
        include_all: If True, include an "All" option at the start

    Returns:
        list: List of dicts with league info for dropdowns
    """
    from app.models.league import League
    from app.models.league_season import LeagueSeason

    if year is not None and is_spring is not None:
        # Get leagues active in this season
        league_seasons = LeagueSeason.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).all()

        leagues = []
        for ls in league_seasons:
            league_obj = ls.league_obj
            if league_obj:
                leagues.append({
                    'id': league_obj.ID,
                    'name': league_obj.display_name,
                    'display_name': league_obj.get_seasonal_name(is_spring)
                })
            else:
                # Fallback for leagues without FK set
                leagues.append({
                    'id': None,
                    'name': ls.league,
                    'display_name': ls.league
                })
    else:
        # Get all active leagues
        all_leagues = League.get_all_active()
        leagues = [{
            'id': l.ID,
            'name': l.display_name,
            'display_name': l.display_name
        } for l in all_leagues]

    # Sort by display name
    leagues.sort(key=lambda x: x['display_name'])

    if include_all:
        leagues.insert(0, {'id': '', 'name': '', 'display_name': 'All Leagues'})

    return leagues
