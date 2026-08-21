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
    if game1.location != game2.location:
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

    if not game.location or not game.game_date:
        return None

    game_date = game.game_date.date()

    # Get all games at the same field on the same day
    same_field_games = Game.query.filter(
        Game.location == game.location,
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
        league_id: League ID
        year: Season year
        is_spring: Whether spring season

    Returns:
        dict: {'academy_pct': float, 'diamond_pct': float, 'dynamic_pct': float, 'total': int}
    """
    from app.models.game import Game
    from app.models.game_umpire import GameUmpire
    from app.models.umpire_partner import UmpirePartner

    # Get all games for this league/season
    games = Game.query.filter_by(
        league=league_id if isinstance(league_id, str) else None,
        year=year,
        is_spring=is_spring,
        active=1
    ).all()

    academy_count = 0
    diamond_count = 0
    dynamic_count = 0
    total = 0

    for game in games:
        assignment = GameUmpire.query.filter(
            GameUmpire.game_id == game.ID,
            GameUmpire.status != 'cancelled'
        ).first()

        if assignment:
            total += 1
            if assignment.umpire_profile_id:
                academy_count += 1
            elif assignment.partner:
                if assignment.partner.short_code == 'DIA':
                    diamond_count += 1
                elif assignment.partner.short_code == 'DYN':
                    dynamic_count += 1

    if total == 0:
        return {'academy_pct': 0, 'diamond_pct': 0, 'dynamic_pct': 0, 'total': 0}

    return {
        'academy_pct': (academy_count / total) * 100,
        'diamond_pct': (diamond_count / total) * 100,
        'dynamic_pct': (dynamic_count / total) * 100,
        'total': total
    }


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
            game.umpire_override = adjacent_partner.short_code.lower()
            create_partner_assignment(game, adjacent_partner.id, assigned_by)
            return adjacent_partner.short_code.lower()

    # 2. Check for manual override keywords
    override = check_override_keywords(game)
    if override:
        if override.target_type == 'academy':
            game.umpire_override = 'academy'
            return 'academy'
        elif override.partner_id:
            partner = UmpirePartner.query.get(override.partner_id)
            if partner:
                game.umpire_override = partner.short_code.lower()
                create_partner_assignment(game, partner.id, assigned_by)
                return partner.short_code.lower()

    # 3. Get delegation rules for this league
    rule = UmpireDelegationRule.get_for_league(league.ID, game.year, game.is_spring)
    if not rule:
        # Default to academy if no rules
        game.umpire_override = 'academy'
        return 'academy'

    # 4. Get current allocation stats to find most under-allocated source
    stats = get_allocation_stats(game.league, game.year, game.is_spring)

    target_vs_actual = [
        ('academy', rule.academy_pct, stats.get('academy_pct', 0)),
        ('diamond', rule.diamond_pct, stats.get('diamond_pct', 0)),
        ('dynamic', rule.dynamic_pct, stats.get('dynamic_pct', 0)),
    ]

    # Filter out sources with 0% target
    target_vs_actual = [(s, t, a) for s, t, a in target_vs_actual if t > 0]

    if not target_vs_actual:
        game.umpire_override = 'academy'
        return 'academy'

    # Sort by deficit (target - actual), assign to largest deficit
    target_vs_actual.sort(key=lambda x: x[1] - x[2], reverse=True)

    best_source = target_vs_actual[0][0]
    game.umpire_override = best_source

    # Create partner assignment if not academy
    if best_source != 'academy':
        partner = UmpirePartner.get_by_code(best_source[:3].upper())
        if partner:
            create_partner_assignment(game, partner.id, assigned_by)

    return best_source


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
        elif (current_sequence[-1].location == game.location and
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

    Args:
        sequence: List of games in the sequence

    Returns:
        UmpirePartner to assign to the sequence
    """
    from app.models.umpire_partner import UmpirePartner

    if not sequence:
        return None

    # Get first game to check league/season
    game = sequence[0]

    # Get current allocation stats
    stats = get_allocation_stats(game.league, game.year, game.is_spring)

    # Compare Diamond vs Dynamic allocation
    diamond_deficit = 50 - stats.get('diamond_pct', 0)  # Assume 50% target
    dynamic_deficit = 50 - stats.get('dynamic_pct', 0)

    if diamond_deficit >= dynamic_deficit:
        return UmpirePartner.get_by_code('DIA')
    return UmpirePartner.get_by_code('DYN')


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
        game.umpire_override = partner.short_code.lower()
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
    ).order_by(Game.location, Game.game_date).all()

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
