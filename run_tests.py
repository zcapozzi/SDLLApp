#!/usr/bin/env python
"""Test runner script for SDLL Web Application

Usage:
    python run_tests.py           # Run all tests
    python run_tests.py -v        # Run with verbose output
    python run_tests.py --cov     # Run with coverage report
    python run_tests.py auth      # Run only auth tests
"""

import sys
import subprocess


def main():
    """Run pytest with appropriate arguments"""
    # Base pytest command
    cmd = [sys.executable, '-m', 'pytest']

    # Add default arguments
    cmd.extend([
        'tests/',
        '-v',  # verbose
        '--tb=short',  # shorter traceback
    ])

    # Check for coverage flag
    if '--cov' in sys.argv:
        cmd.extend([
            '--cov=app',
            '--cov-report=term-missing',
            '--cov-report=html:coverage_html'
        ])
        sys.argv.remove('--cov')

    # Add any additional arguments
    for arg in sys.argv[1:]:
        if arg.startswith('-'):
            cmd.append(arg)
        else:
            # Assume it's a test file pattern
            cmd.append(f'tests/test_{arg}.py')

    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)

    # Run pytest
    result = subprocess.run(cmd)

    # Return exit code
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
