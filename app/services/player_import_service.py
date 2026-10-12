"""Player Import Service - imports registration and evaluation data from CSV files."""

import csv
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models.user import User
from app.models.player import Player, PlayerSeason, PlayerEvaluation, EvaluationMetric
from app.models.org_season import OrgSeason
from app.models.league import League


class PlayerImportService:
    """Service for importing player data from CSV files."""

    # Map registration division names to league IDs
    # Update these mappings based on actual sdll_leagues data
    LEAGUE_NAME_MAP = {
        # Spring/canonical names
        'tee ball': 12,
        'bb tee ball': 12,
        'rookie': 7,
        'bb rookie': 7,
        'lower machine': 7,  # Fall name for Rookie
        'lmp': 7,
        'a': 6,
        'a (upper machine pitch)': 6,
        'a (upper machine)': 6,
        'upper machine pitch': 6,
        'ump': 6,
        'bb ump': 6,
        'aa': 5,
        'bb aa': 5,
        'cactus': 5,  # Fall name for AA
        'bb cactus': 5,
        'aaa': 4,
        'bb aaa': 4,
        'grapefruit': 4,  # Fall name for AAA
        'bb grapefruit': 4,
        'majors': 3,
        'bb majors': 3,
        'intermediate': 15,
        'bb intermediate': 15,
        'juniors': 14,
        'bb juniors': 14,
        # Softball
        'sb tee ball': 13,
        'sb rookie': 8,
        'sb minors': 1,
        'sb majors': 9,
        'sb seniors': 10,
    }

    def __init__(self, org_season: OrgSeason = None):
        """Initialize import service.

        Args:
            org_season: Target OrgSeason for imports. If None, uses current season.
        """
        self.org_season = org_season or OrgSeason.get_current_season()
        self.stats = {
            'players_created': 0,
            'players_updated': 0,
            'parent_users_created': 0,
            'season_records_created': 0,
            'evaluations_created': 0,
            'errors': []
        }

    def _parse_date(self, date_str: str) -> datetime.date:
        """Parse date from various formats."""
        if not date_str:
            return None

        # Try common formats
        formats = ['%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y', '%m/%d/%y']
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _parse_score(self, value: str) -> Decimal:
        """Parse evaluation score (1-7 scale)."""
        if not value or value.strip() == '':
            return None
        try:
            score = Decimal(value.strip())
            if 1 <= score <= 7:
                return score
            return None
        except InvalidOperation:
            return None

    def _normalize_league_name(self, name: str) -> int:
        """Convert league name to league ID."""
        if not name:
            return None
        normalized = name.lower().strip()
        return self.LEAGUE_NAME_MAP.get(normalized)

    def _get_or_create_parent_user(self, email: str, name: str = None,
                                   phone: str = None) -> User:
        """Find existing user or create parent account.

        Args:
            email: Parent email address
            name: Parent name (optional)
            phone: Parent phone (optional)

        Returns:
            User instance (existing or newly created)
        """
        if not email:
            return None

        # Check if user already exists
        user = User.get_by_email(email)
        if user:
            # Add parent role if not already present
            if not user.has_role('parent'):
                user.add_role('parent')
            return user

        # Create new parent user with random password
        # (they'll need to reset password to log in)
        random_password = secrets.token_urlsafe(16)
        try:
            user = User.create_user(
                email=email,
                password=random_password,
                name=name,
                phone=phone,
                role='parent'
            )
            self.stats['parent_users_created'] += 1
            return user
        except Exception as e:
            self.stats['errors'].append(f"Error creating user for {email}: {str(e)}")
            return None

    def import_registration_csv(self, filepath: str, program: str,
                                  create_parent_users: bool = True) -> dict:
        """Import player registration data from enrollment CSV.

        Expected columns:
        - User Email: parent email
        - Player First Name, Player Last Name
        - Player Birth Date, Player Gender
        - Account First Name, Account Last Name (parent name)
        - Cellphone or Telephone
        - Division Name: registration division
        - "If your child played...": prior division

        Args:
            filepath: Path to enrollment CSV file
            program: Sport program ('baseball' or 'softball')
            create_parent_users: If True, creates User records for parents

        Returns:
            dict with import statistics
        """
        self.program = program
        self.stats = {
            'players_created': 0,
            'players_updated': 0,
            'parent_users_created': 0,
            'season_records_created': 0,
            'evaluations_created': 0,
            'errors': []
        }

        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):
                try:
                    self._import_registration_row(row, create_parent_users)
                except Exception as e:
                    self.stats['errors'].append(f"Row {row_num}: {str(e)}")

        db.session.commit()
        return self.stats

    def _import_registration_row(self, row: dict, create_parent_users: bool):
        """Import single registration row."""
        # Extract fields
        parent_email = row.get('User Email', '').strip()
        first_name = row.get('Player First Name', '').strip()
        last_name = row.get('Player Last Name', '').strip()
        birth_date_str = row.get('Player Birth Date', '')
        gender_raw = row.get('Player Gender', '').strip()

        if not parent_email or not first_name or not last_name:
            return  # Skip incomplete rows

        birth_date = self._parse_date(birth_date_str)
        if not birth_date:
            self.stats['errors'].append(
                f"Invalid birth date for {first_name} {last_name}: {birth_date_str}")
            return

        gender = 'M' if gender_raw.lower().startswith('m') else 'F' if gender_raw.lower().startswith('f') else None

        # Parent info
        parent_first = row.get('Account First Name', '').strip()
        parent_last = row.get('Account Last Name', '').strip()
        parent_phone = row.get('Cellphone', '').strip() or row.get('Telephone', '').strip()
        parent_name = f"{parent_first} {parent_last}".strip() if parent_first else None

        # Use program specified by user during import
        division_name = row.get('Division Name', '')

        # Get or create player
        existing = Player.find_by_email_and_name(parent_email, first_name, last_name)
        if existing:
            self.stats['players_updated'] += 1
        else:
            self.stats['players_created'] += 1

        player = Player.get_or_create(
            parent_email=parent_email,
            first_name=first_name,
            last_name=last_name,
            birth_date=birth_date,
            gender=gender,
            program=self.program,
            parent_first_name=parent_first,
            parent_last_name=parent_last,
            parent_phone=parent_phone
        )

        # Create parent user if requested
        if create_parent_users:
            parent_user = self._get_or_create_parent_user(parent_email, parent_name, parent_phone)
            if parent_user and not player.parent_user_id:
                player.link_to_parent_user(parent_user)

        # Create season record
        registration_division = division_name

        # Get prior league from "If your child played..." column
        prior_division_col = [k for k in row.keys() if 'if your child played' in k.lower()]
        prior_division = row.get(prior_division_col[0], '') if prior_division_col else ''
        prior_league_id = self._normalize_league_name(prior_division)

        PlayerSeason.get_or_create(
            player=player,
            org_season=self.org_season,
            registration_division=registration_division,
            prior_league_id=prior_league_id
        )
        self.stats['season_records_created'] += 1

    def import_evaluation_csv(self, filepath: str) -> dict:
        """Import evaluation data from eval CSV.

        Expected columns:
        - playerID: player code (e.g., "bennluk1810")
        - playerFirst, playerLast
        - acctEmail: parent email
        - Division: eval session name (e.g., "Cactus")
        - contact now, power now, glove Now, arm Now, outfield Now, control Now, velocity Now
        - avSpeedNow or speed (running speed)

        Args:
            filepath: Path to evaluation CSV file

        Returns:
            dict with import statistics
        """
        self.stats = {
            'players_created': 0,
            'players_updated': 0,
            'parent_users_created': 0,
            'season_records_created': 0,
            'evaluations_created': 0,
            'errors': []
        }

        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):
                try:
                    self._import_evaluation_row(row)
                except Exception as e:
                    self.stats['errors'].append(f"Row {row_num}: {str(e)}")

        db.session.commit()
        return self.stats

    def _import_evaluation_row(self, row: dict):
        """Import single evaluation row."""
        # Extract player identification
        player_code = row.get('playerID', '').strip()
        first_name = row.get('playerFirst', '').strip()
        last_name = row.get('playerLast', '').strip()
        parent_email = row.get('acctEmail', '').strip()
        secondary_email = row.get('secondEmail', '').strip()

        if not parent_email or not first_name:
            return  # Skip incomplete rows

        # Try to find player by code first, then by email+name
        player = None
        if player_code:
            player = Player.find_by_code(player_code)

        if not player and parent_email:
            player = Player.find_by_email_and_name(parent_email, first_name, last_name)

        if not player:
            # Can't create player without birth date - skip
            self.stats['errors'].append(
                f"Player not found: {first_name} {last_name} ({player_code or parent_email})")
            return

        # Update player code if we have it and player doesn't
        if player_code and not player.player_code:
            player.player_code = player_code

        # Add secondary email if not set
        if secondary_email and not player.secondary_email:
            player.secondary_email = secondary_email

        # Extract scores
        scores = {
            'contact': self._parse_score(row.get('contact now', '')),
            'power': self._parse_score(row.get('power now', '')),
            'glove': self._parse_score(row.get('glove Now', '')),
            'arm': self._parse_score(row.get('arm Now', '')),
            'outfield': self._parse_score(row.get('outfield Now', '')),
            'control': self._parse_score(row.get('control Now', '')),
            'velocity': self._parse_score(row.get('velocity Now', '')),
            'speed': self._parse_score(row.get('avSpeedNow', '') or row.get('speed', '')),
        }

        # Skip if no scores
        if not any(scores.values()):
            return

        eval_session = row.get('Division', '').strip()

        # Create evaluation
        PlayerEvaluation.create_for_player(
            player=player,
            org_season=self.org_season,
            scores=scores,
            eval_session=eval_session
        )
        self.stats['evaluations_created'] += 1

        # Ensure season record exists
        PlayerSeason.get_or_create(
            player=player,
            org_season=self.org_season,
            status='evaluated'
        )

    def import_both(self, registration_csv: str, evaluation_csv: str,
                    create_parent_users: bool = True) -> dict:
        """Import both registration and evaluation data.

        Import order matters: registration first (creates players),
        then evaluations (links to existing players).

        Args:
            registration_csv: Path to enrollment CSV
            evaluation_csv: Path to evaluation CSV
            create_parent_users: If True, creates User records for parents

        Returns:
            Combined statistics dict
        """
        # Import registration first
        reg_stats = self.import_registration_csv(registration_csv, create_parent_users)

        # Then evaluations
        eval_stats = self.import_evaluation_csv(evaluation_csv)

        # Combine stats
        return {
            'players_created': reg_stats['players_created'],
            'players_updated': reg_stats['players_updated'] + eval_stats['players_updated'],
            'parent_users_created': reg_stats['parent_users_created'],
            'season_records_created': reg_stats['season_records_created'],
            'evaluations_created': eval_stats['evaluations_created'],
            'errors': reg_stats['errors'] + eval_stats['errors']
        }
