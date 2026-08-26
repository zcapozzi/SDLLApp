"""Umpire delegation service - auto-assignment of umpire sources to games.

This service handles:
1. Auto-delegating games to Academy (SDLL), Diamond, or Dynamic umpires
2. Enforcing TIER I constraints (back-to-back field continuity)
3. Respecting percentage-based allocation targets
4. Processing keyword-based overrides
"""

from datetime import datetime, timedelta
from collections import defaultdict
from app.extensions import db


def is_partner_eligible(game):
    """Check if a game is eligible for partner umpire assignment.

    Partner-eligible games are those in leagues that can use partner umpires.

    Args:
        game: Game object

    Returns:
        bool: True if game can be assigned to a partner
    """
    from app.models.league import League

    if not game.league:
        return False

    league = League.get_by_name(game.league)
    if not league:
        return False

    return league.can_use_partner_umpires()


def is_back_to_back_same_field(game1, game2):
    """Check if two games are back-to-back at the same field.

    Args:
        game1: First game (earlier)
        game2: Second game (later)

    Returns:
        bool: True if back-to-back at same field
    """
    # Must be same field
    if not game1.field_id or not game2.field_id:
        return False
    if game1.field_id != game2.field_id:
        return False

    # Must be same date
    if not game1.game_date or not game2.game_date:
        return False

    if game1.game_date.date() != game2.game_date.date():
        return False

    # Calculate gap between games
    # Game1 end time + 30 min gap max
    game1_duration = game1.duration_minutes or 120
    game1_end = game1.game_date + timedelta(minutes=game1_duration)

    gap_minutes = (game2.game_date - game1_end).total_seconds() / 60

    # Consider back-to-back if gap is 30 minutes or less
    return gap_minutes <= 30


def get_adjacent_partner_same_field(game):
    """Check if there's a partner-assigned game immediately before/after at same field.

    TIER I: If found, the game MUST be assigned to the same partner
    to maintain field continuity.

    Args:
        game: Game object

    Returns:
        UmpirePartner or None
    """
    from app.models.game import Game
    from app.models.game_umpire import GameUmpire
    from app.models.umpire_partner import UmpirePartner

    if not game.field_id or not game.game_date:
        return None

    game_date = game.game_date.date()

    # Get all games at the same field on the same day
    same_field_games = Game.query.filter(
        Game.field_id == game.field_id,
        Game.active == 1,
        Game.ID != game.ID,
        db.func.date(Game.game_date) == game_date
    ).order_by(Game.game_date).all()

    for other_game in same_field_games:
        # Check if this game has a partner assignment
        assignment = GameUmpire.query.filter(
            GameUmpire.game_id == other_game.ID,
            GameUmpire.partner_id.isnot(None),
            GameUmpire.status != 'cancelled'
        ).first()

        if assignment and assignment.partner:
            # Check if back-to-back (in either direction)
            if other_game.game_date < game.game_date:
                # Other game is before ours
                if is_back_to_back_same_field(other_game, game):
                    return assignment.partner
            else:
                # Other game is after ours
                if is_back_to_back_same_field(game, other_game):
                    return assignment.partner

    return None


def check_override_keywords(game):
    """Check if game has override keyword in notes/description.

    Args:
        game: Game object

    Returns:
        UmpireDelegationOverride or None
    """
    from app.models.umpire_delegation import UmpireDelegationOverride

    # Check umpire_override field (used for manual overrides)
    text = game.umpire_override or ''

    return UmpireDelegationOverride.find_matching(text, org_id=1)


def get_allocation_stats(league_id, year, is_spring):
    """Get current umpire allocation statistics for a league.

    Args:
        league_id: League ID (can be string league name or int ID)
        year: Season year
        is_spring: Whether spring season

    Returns:
        dict: {'total': int, 'sdl': {'count': N, 'pct': float}, 'dia': {...}, ...}
              Keys are lowercase partner short codes.
    """
    from app.models.game import Game
    from app.models.umpire_partner import UmpirePartner

    # Build stats dynamically based on ALL active partners
    stats = {'total': 0}
    partners = UmpirePartner.get_active()
    for p in partners:
        stats[p.short_code.lower()] = {'count': 0, 'pct': 0}

    # Get all games for this league/season (exclude practices)
    games = Game.query.filter(
        Game.league == (league_id if isinstance(league_id, str) else None),
        Game.year == year,
        Game.is_spring == is_spring,
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff', 'scrimmage'])
    ).all()

    # Count assignments by source (use umpire_override which stores short_code)
    for game in games:
        if game.umpire_override:
            stats['total'] += 1
            code = game.umpire_override.lower()
            if code in stats:
                stats[code]['count'] += 1

    # Calculate percentages
    if stats['total'] > 0:
        for key in stats:
            if key != 'total' and isinstance(stats[key], dict):
                stats[key]['pct'] = (stats[key]['count'] / stats['total']) * 100

    return stats


def create_partner_assignment(game, partner_id, assigned_by=None):
    """Create a partner assignment for a game.

    Args:
        game: Game object
        partner_id: UmpirePartner ID
        assigned_by: User ID who made the assignment

    Returns:
        GameUmpire assignment
    """
    from app.models.game_umpire import GameUmpire

    assignment = GameUmpire.assign_partner(
        game_id=game.ID,
        partner_id=partner_id,
        assigned_by=assigned_by
    )
    return assignment


def apply_single_game_delegation(game, assigned_by=None):
    """Apply delegation rules to a single game, respecting overrides and field continuity.

    TIER I: Back-to-back field continuity is checked FIRST - this overrides
    even manual override keywords if necessary for field continuity.

    Args:
        game: Game object
        assigned_by: User ID who triggered the delegation

    Returns:
        str: Umpire source assigned ('academy', 'diamond', 'dynamic')
    """
    from app.models.league import League
    from app.models.umpire_delegation import UmpireDelegationRule
    from app.models.umpire_partner import UmpirePartner

    # Check if league needs umpires
    league = League.get_by_name(game.league) if game.league else None
    if not league or not league.needs_umpires:
        return None

    # 1. TIER I: Check for back-to-back partner constraint at same field
    # This takes absolute priority over other rules
    if is_partner_eligible(game):
        adjacent_partner = get_adjacent_partner_same_field(game)
        if adjacent_partner:
            # MUST use same partner as adjacent game - this is Tier I
            game.umpire_override = adjacent_partner.short_code.upper()
            create_partner_assignment(game, adjacent_partner.id, assigned_by)
            return adjacent_partner.short_code.upper()

    # 2. Check for manual override keywords
    override = check_override_keywords(game)
    if override:
        if override.target_type == 'academy':
            game.umpire_override = 'ACADEMY'
            return 'academy'
        elif override.partner_id:
            partner = UmpirePartner.query.get(override.partner_id)
            if partner:
                game.umpire_override = partner.short_code.upper()
                create_partner_assignment(game, partner.id, assigned_by)
                return partner.short_code.upper()

    # 3. Get delegation rules for this league
    rule = UmpireDelegationRule.get_for_league(league.ID, game.year, game.is_spring)
    if not rule or not rule.allocations:
        # Default to SDL (academy) if no rules
        game.umpire_override = 'SDL'
        return 'SDL'

    # 4. Get current allocation stats to find most under-allocated source
    stats = get_allocation_stats(game.league, game.year, game.is_spring)

    # Build target vs actual for ALL allocations dynamically
    target_vs_actual = []
    for alloc in rule.allocations:
        if alloc.percentage > 0:
            source_code = alloc.source_code  # e.g., 'sdl', 'dia', 'dyn'
            target = alloc.percentage
            actual = stats.get(source_code, {}).get('pct', 0) if isinstance(stats.get(source_code), dict) else 0
            target_vs_actual.append((
                source_code,
                alloc.partner_id,
                alloc.is_academy,
                target,
                actual
            ))

    if not target_vs_actual:
        game.umpire_override = 'SDL'
        return 'SDL'

    # Sort by deficit (target - actual), assign to largest deficit
    target_vs_actual.sort(key=lambda x: x[3] - x[4], reverse=True)

    source_code, partner_id, is_academy, _, _ = target_vs_actual[0]
    game.umpire_override = source_code.upper()

    # Create partner assignment for non-Academy partners
    if not is_academy:
        create_partner_assignment(game, partner_id, assigned_by)

    return source_code.upper()


def identify_partner_sequences(games):
    """Find groups of back-to-back games at same field that should go to same partner.

    TIER I: Critical rule - partner games at same field back-to-back must be same partner.

    Args:
        games: List of Game objects, sorted by field and time

    Returns:
        List of lists, each inner list is a sequence of games at same field
    """
    sequences = []
    current_sequence = []

    for game in games:
        # Skip Academy-only games (not partner eligible)
        if not is_partner_eligible(game):
            if len(current_sequence) > 1:
                sequences.append(current_sequence)
            current_sequence = []
            continue

        if not current_sequence:
            current_sequence = [game]
        elif (current_sequence[-1].field_id == game.field_id and
              is_back_to_back_same_field(current_sequence[-1], game)):
            current_sequence.append(game)
        else:
            if len(current_sequence) > 1:
                sequences.append(current_sequence)
            current_sequence = [game]

    if len(current_sequence) > 1:
        sequences.append(current_sequence)

    return sequences


def get_best_partner_for_sequence(sequence):
    """Choose partner for a sequence based on allocation needs.

    Uses the delegation rules to determine which partner is most under-allocated.
    Only considers non-Academy partners since sequences are for partner assignments.

    Args:
        sequence: List of games in the sequence

    Returns:
        UmpirePartner to assign to the sequence
    """
    from app.models.umpire_partner import UmpirePartner
    from app.models.umpire_delegation import UmpireDelegationRule
    from app.models.league import League

    if not sequence:
        return None

    # Get first game to check league/season
    game = sequence[0]

    # Get delegation rules for this league
    league = League.get_by_name(game.league) if game.league else None
    if not league:
        # Default to first available partner if no league context
        partners = UmpirePartner.get_active()
        non_academy = [p for p in partners if p.short_code != 'SDL']
        return non_academy[0] if non_academy else None

    rule = UmpireDelegationRule.get_for_league(league.ID, game.year, game.is_spring)

    # Get current allocation stats
    stats = get_allocation_stats(game.league, game.year, game.is_spring)

    # Build list of partner allocations with deficits
    partner_deficits = []
    if rule and rule.allocations:
        for alloc in rule.allocations:
            if alloc.percentage > 0 and not alloc.is_academy:
                source_code = alloc.source_code
                target = alloc.percentage
                actual = stats.get(source_code, {}).get('pct', 0) if isinstance(stats.get(source_code), dict) else 0
                deficit = target - actual
                partner_deficits.append((alloc.partner, deficit))

    if partner_deficits:
        # Return partner with largest deficit
        partner_deficits.sort(key=lambda x: x[1], reverse=True)
        return partner_deficits[0][0]

    # Fallback: return first non-Academy partner
    partners = UmpirePartner.get_active()
    non_academy = [p for p in partners if p.short_code != 'SDL']
    return non_academy[0] if non_academy else None


def assign_sequence_to_partner(sequence, assigned_by=None):
    """Assign entire sequence of games to same partner.

    Args:
        sequence: List of games to assign
        assigned_by: User ID who triggered the delegation
    """
    if not sequence:
        return

    partner = get_best_partner_for_sequence(sequence)
    if not partner:
        return

    for game in sequence:
        game.umpire_override = partner.short_code.upper()
        create_partner_assignment(game, partner.id, assigned_by)


def delegate_games_for_season(year, is_spring, org_id=1, assigned_by=None):
    """Assign umpire sources to all unassigned games based on delegation rules.

    TIER I: Back-to-back field sequences are identified and assigned first.

    Args:
        year: Season year
        is_spring: Whether spring season (1/True or 0/False)
        org_id: Organization ID
        assigned_by: User ID who triggered the delegation

    Returns:
        dict: Summary of assignments made
    """
    from app.models.game import Game
    from app.models.game_umpire import GameUmpire

    # Normalize is_spring
    is_spring = 1 if is_spring else 0

    # 1. Get all games needing umpire assignment, ordered by field + time
    games = Game.query.filter(
        Game.year == year,
        Game.is_spring == is_spring,
        Game.active == 1,
        Game.game_date.isnot(None),
        # No existing assignment
        ~Game.ID.in_(
            db.session.query(GameUmpire.game_id).filter(
                GameUmpire.status != 'cancelled'
            )
        )
    ).order_by(Game.field_id, Game.game_date).all()

    if not games:
        return {'assigned': 0, 'skipped': 0}

    # 2. FIRST PASS: Identify back-to-back partner game sequences at same field
    field_sequences = identify_partner_sequences(games)

    # 3. Assign entire sequences to same partner (respecting overall allocation)
    assigned_in_sequences = set()
    for sequence in field_sequences:
        assign_sequence_to_partner(sequence, assigned_by)
        for game in sequence:
            assigned_in_sequences.add(game.ID)

    # 4. SECOND PASS: Assign remaining games respecting delegation percentages
    remaining_games = [g for g in games if g.ID not in assigned_in_sequences]

    for game in remaining_games:
        apply_single_game_delegation(game, assigned_by)

    db.session.commit()

    return {
        'assigned': len(games),
        'in_sequences': len(assigned_in_sequences),
        'individual': len(remaining_games)
    }
