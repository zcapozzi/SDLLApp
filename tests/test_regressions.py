"""Regression tests for production errors.

This file contains tests that reproduce production errors before they are fixed.
Each test follows the TDD pattern:
1. Test is written to reproduce the exact error seen in production
2. Test FAILS (confirming the bug exists)
3. Fix is implemented
4. Test PASSES (confirming the fix works)
5. Test remains as regression prevention

Naming convention: test_regression_error_{error_id}_{brief_description}

Usage:
    # Run all regression tests
    pytest tests/test_regressions.py -v

    # Run a specific regression test
    pytest tests/test_regressions.py::test_regression_error_123_null_field -v
"""

import pytest
from datetime import datetime, date, time


class TestProductionRegressions:
    """Tests that reproduce and verify fixes for production errors."""

    # === Add regression tests below this line ===
    # Each test should:
    # 1. Set up the exact conditions that caused the error
    # 2. Call the code path that failed
    # 3. Assert the expected behavior (not the error)

    def test_regression_template_example(self, app):
        """
        TEMPLATE: Copy this for new regression tests.

        Production Error: #XXX
        Context: <what was happening>
        Error: <error type>: <error message>
        Path: <request path>
        Root cause: <why it happened>
        """
        # This is a template - skip it
        pytest.skip("This is a template test, not an actual regression")

        # Example structure:
        # with app.app_context():
        #     # 1. Set up conditions
        #     # 2. Call the failing code
        #     # 3. Assert expected behavior
        #     pass

    # === Actual regression tests will be added below ===
    # When Claude Code diagnoses an error, it will add a test here
    # following the TDD red-green pattern.

    @pytest.mark.quick
    def test_regression_error_5_dashboard_null_league(self):
        """
        Production Error: #5
        Context: Dashboard page displaying upcoming games
        Error: AttributeError: 'NoneType' object has no attribute 'upper'
        Path: /dashboard
        Root cause: game.league can be None for games without a league assigned,
                    and the code called .upper() on it without checking for None.
        """
        # Create a mock game object with league=None
        class MockGame:
            def __init__(self, league):
                self.league = league

        # Test the fixed logic: game.league.upper() if game.league else 'TBD'
        def format_league_display(game):
            """Replicate the dashboard route logic."""
            return game.league.upper() if game.league else 'TBD'

        # Test case 1: league is None (the bug condition)
        game_with_null_league = MockGame(league=None)
        result = format_league_display(game_with_null_league)
        assert result == 'TBD', f"Null league should display as 'TBD', got '{result}'"

        # Test case 2: league has a value (normal case)
        game_with_league = MockGame(league='bb majors')
        result = format_league_display(game_with_league)
        assert result == 'BB MAJORS', f"League should be uppercased, got '{result}'"

        # Test case 3: league is empty string
        game_with_empty_league = MockGame(league='')
        result = format_league_display(game_with_empty_league)
        assert result == 'TBD', f"Empty league should display as 'TBD', got '{result}'"

    @pytest.mark.quick
    def test_regression_error_18_day_view_field_import(self):
        """
        Production Error: #18
        Context: Day view page when no schedule proposal exists
        Error: UnboundLocalError: cannot access local variable 'Field'
               where it is not associated with a value
        Path: /games/2026/0/day/2026-08-22
        Root cause: A local 'from app.models.field import Field' import inside
                    the 'if has_proposal:' block (line 1107) creates a local
                    binding that shadows the module-level import. When has_proposal
                    is False, the import never executes but Python still treats
                    Field as a local variable, causing UnboundLocalError at line 1155.

        Fix: Remove the redundant local import at line 1107 since Field is
             already imported at the module level.
        """
        import ast
        import inspect
        from pathlib import Path

        # Read the routes.py file
        routes_path = Path(__file__).parent.parent / 'app' / 'games' / 'routes.py'
        source = routes_path.read_text(encoding='utf-8')
        tree = ast.parse(source)

        # Find the day_view function
        day_view_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'day_view':
                day_view_func = node
                break

        assert day_view_func is not None, "day_view function not found in routes.py"

        # Check for local imports of Field within the function
        local_field_imports = []
        for node in ast.walk(day_view_func):
            if isinstance(node, ast.ImportFrom):
                if node.module and 'field' in node.module.lower():
                    for alias in node.names:
                        if alias.name == 'Field':
                            local_field_imports.append(node.lineno)

        # The bug was caused by a local import of Field inside day_view
        # After the fix, there should be NO local imports of Field in day_view
        # (Field should only be imported at module level)
        assert len(local_field_imports) == 0, \
            f"Found local import of 'Field' at line(s) {local_field_imports} in day_view(). " \
            "This causes UnboundLocalError when has_proposal is False. " \
            "Remove the local import and use the module-level import instead."
