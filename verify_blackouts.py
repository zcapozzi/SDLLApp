"""Verify blackout dates and field start dates are being respected."""

import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.utils.scheduler import ScheduleGenerator

app = create_app(os.environ.get('FLASK_CONFIG', 'development'))

with app.app_context():
    print('Verifying blackout dates and field restrictions...\n')

    gen = ScheduleGenerator(2026, 0)
    result = gen.generate(start_fresh=True)

    # Check Labor Day weekend (Sept 4-7)
    labor_day_dates = [date(2026, 9, 4), date(2026, 9, 5), date(2026, 9, 6), date(2026, 9, 7)]
    print('=== LABOR DAY WEEKEND (Sept 4-7) ===')
    labor_day_activities = []
    for game in gen.proposed_games:
        if game.game_date:
            game_date = game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date
            if game_date in labor_day_dates:
                labor_day_activities.append(game)

    if labor_day_activities:
        print(f'VIOLATION: {len(labor_day_activities)} activities scheduled on Labor Day weekend!')
        for g in labor_day_activities[:5]:
            print(f'  - {g.game_type}: {g.home_team.display_name if g.home_team else "?"} on {g.game_date}')
    else:
        print('OK: No activities scheduled on Labor Day weekend')

    # Check Herndon 1 before Sept 8
    herndon_1_start = date(2026, 9, 8)
    print('\n=== HERNDON 1 (start date: Sept 8) ===')
    herndon_early = []
    for game in gen.proposed_games:
        if game.field and game.field.ID == 10:  # Herndon 1 ID
            game_date = game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date
            if game_date < herndon_1_start:
                herndon_early.append(game)

    if herndon_early:
        print(f'VIOLATION: {len(herndon_early)} activities at Herndon 1 before Sept 8!')
        for g in herndon_early[:5]:
            print(f'  - {g.game_type}: {g.home_team.display_name if g.home_team else "?"} on {g.game_date}')
    else:
        print('OK: No activities at Herndon 1 before Sept 8')

    # Show what's scheduled at Herndon 1 after Sept 8
    herndon_after = [g for g in gen.proposed_games
                     if g.field and g.field.ID == 10
                     and g.game_date.date() >= herndon_1_start]
    print(f'\nHerndon 1 activities after Sept 8: {len(herndon_after)}')
    for g in herndon_after[:3]:
        print(f'  - {g.game_type}: {g.home_team.display_name if g.home_team else "?"} on {g.game_date}')

    print('\n=== SUMMARY ===')
    print(f'Hard violations: {result["summary"]["hard_violations"]}')
    print(f'Soft violations: {result["summary"]["soft_violations"]}')
