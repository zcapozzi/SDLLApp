"""Player Import Service - imports registration and evaluation data from CSV files."""

import csv
import secrets
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Optional

from app.extensions import db
from app.models.user import User
from app.models.player import Player, PlayerSeason, PlayerEvaluation, EvaluationMetric
from app.models.org_season import OrgSeason
from app.models.league import League


@dataclass
class ExpectedColumn:
    """Definition of an expected CSV column with aliases."""
    name: str  # Internal field name
    display_name: str  # Human-readable name
    required: bool = True
    aliases: tuple = ()  # Alternative names that match this column


# Expected columns for registration CSV import
EXPECTED_REGISTRATION_COLUMNS: List[ExpectedColumn] = [
    ExpectedColumn(
        name='User Email',
        display_name='Parent/Account Email',
        required=True,
        aliases=('email', 'parent email', 'account email', 'guardian email', 'acct email')
    ),
    ExpectedColumn(
        name='Player First Name',
        display_name='Player First Name',
        required=True,
        aliases=('first name', 'firstname', 'first', 'player first', 'playerfirst')
    ),
    ExpectedColumn(
        name='Player Last Name',
        display_name='Player Last Name',
        required=True,
        aliases=('last name', 'lastname', 'last', 'surname', 'player last', 'playerlast')
    ),
    ExpectedColumn(
        name='Player Birth Date',
        display_name='Birth Date',
        required=True,
        aliases=('birth date', 'birthdate', 'dob', 'date of birth', 'birthday')
    ),
    ExpectedColumn(
        name='Division Name',
        display_name='Division/League',
        required=False,
        aliases=('division', 'league', 'level', 'program', 'team level')
    ),
    ExpectedColumn(
        name='Player Gender',
        display_name='Gender',
        required=False,
        aliases=('gender', 'sex', 'player sex')
    ),
    ExpectedColumn(
        name='Account First Name',
        display_name='Parent First Name',
        required=False,
        aliases=('parent first name', 'parent first', 'guardian first name', 'acct first')
    ),
    ExpectedColumn(
        name='Account Last Name',
        display_name='Parent Last Name',
        required=False,
        aliases=('parent last name', 'parent last', 'guardian last name', 'acct last')
    ),
    ExpectedColumn(
        name='Cellphone',
        display_name='Phone',
        required=False,
        aliases=('phone', 'telephone', 'cell', 'mobile', 'cell phone', 'mobile phone')
    ),
]


def auto_map_columns(csv_headers: List[str]) -> Dict[str, Optional[str]]:
    """Automatically map CSV headers to expected columns using case-insensitive matching and aliases.

    Args:
        csv_headers: List of column headers from the CSV file

    Returns:
        Dict mapping internal field names to CSV header names (or None if not matched)
    """
    mapping = {}
    csv_headers_lower = {h.lower().strip(): h for h in csv_headers}

    for expected in EXPECTED_REGISTRATION_COLUMNS:
        # First try exact match (case-insensitive)
        if expected.name.lower() in csv_headers_lower:
            mapping[expected.name] = csv_headers_lower[expected.name.lower()]
            continue

        # Try aliases
        matched = False
        for alias in expected.aliases:
            if alias.lower() in csv_headers_lower:
                mapping[expected.name] = csv_headers_lower[alias.lower()]
                matched = True
                break

        if not matched:
            mapping[expected.name] = None

    return mapping


def get_unmapped_required_columns(column_mapping: Dict[str, Optional[str]]) -> List[ExpectedColumn]:
    """Return list of required columns that are not mapped."""
    unmapped = []
    for expected in EXPECTED_REGISTRATION_COLUMNS:
        if expected.required and not column_mapping.get(expected.name):
            unmapped.append(expected)
    return unmapped


def all_required_columns_mapped(column_mapping: Dict[str, Optional[str]]) -> bool:
    """Check if all required columns are mapped."""
    return len(get_unmapped_required_columns(column_mapping)) == 0


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
        self.column_mapping = None  # Will be set by import methods if provided
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
                                  create_parent_users: bool = True,
                                  column_mapping: dict = None) -> dict:
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
            column_mapping: Optional dict mapping internal names to CSV column names.
                          If None, uses exact column names.

        Returns:
            dict with import statistics
        """
        from app.utils.encryption import hash_for_lookup

        self.program = program
        self.column_mapping = column_mapping
        self.stats = {
            'players_created': 0,
            'players_updated': 0,
            'parent_users_created': 0,
            'season_records_created': 0,
            'evaluations_created': 0,
            'errors': []
        }

        # Pre-load existing data to avoid N+1 queries
        # Build lookup dictionaries keyed by (email_hash, name_hash)
        existing_players = Player.query.all()
        self._player_cache = {}
        for p in existing_players:
            key = (p.parent_email_hash, p.name_hash)
            self._player_cache[key] = p

        # Build user lookup by email_hash
        existing_users = User.query.filter(User.role.contains('parent')).all()
        self._user_cache = {u.email_hash: u for u in existing_users}

        # Build player season lookup by (player_id, org_season_id)
        existing_seasons = PlayerSeason.query.filter_by(
            org_season_id=self.org_season.ID
        ).all()
        self._season_cache = {(ps.player_id, ps.org_season_id): ps for ps in existing_seasons}

        # Get max player code suffix for generating new codes
        self._player_code_counts = {}

        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):
                try:
                    self._import_registration_row_fast(row, create_parent_users)
                except Exception as e:
                    self.stats['errors'].append(f"Row {row_num}: {str(e)}")

        db.session.commit()
        return self.stats

    def _get_field(self, row: dict, field_name: str) -> str:
        """Get field value from row using column mapping if available."""
        if self.column_mapping and field_name in self.column_mapping:
            csv_col = self.column_mapping.get(field_name)
            if csv_col:
                return row.get(csv_col, '').strip()
            return ''
        # Fallback to direct field name
        return row.get(field_name, '').strip()

    def _import_registration_row_fast(self, row: dict, create_parent_users: bool):
        """Import single registration row using cached lookups (fast version)."""
        from app.utils.encryption import hash_for_lookup

        # Extract fields using mapping
        parent_email = self._get_field(row, 'User Email')
        first_name = self._get_field(row, 'Player First Name')
        last_name = self._get_field(row, 'Player Last Name')
        birth_date_str = self._get_field(row, 'Player Birth Date')
        gender_raw = self._get_field(row, 'Player Gender')

        if not parent_email or not first_name or not last_name:
            return  # Skip incomplete rows

        birth_date = self._parse_date(birth_date_str)
        if not birth_date:
            self.stats['errors'].append(
                f"Invalid birth date for {first_name} {last_name}: {birth_date_str}")
            return

        gender = 'M' if gender_raw.lower().startswith('m') else 'F' if gender_raw.lower().startswith('f') else None

        # Parent info
        parent_first = self._get_field(row, 'Account First Name')
        parent_last = self._get_field(row, 'Account Last Name')
        parent_phone = self._get_field(row, 'Cellphone')
        if not parent_phone:
            parent_phone = row.get('Telephone', '').strip()
        parent_name = f"{parent_first} {parent_last}".strip() if parent_first else None

        division_name = self._get_field(row, 'Division Name')

        # Compute hashes for cache lookup
        email_hash = hash_for_lookup(parent_email)
        name_normalized = f"{first_name}{last_name}".lower().replace(' ', '').replace('-', '')
        name_hash = hash_for_lookup(name_normalized)
        cache_key = (email_hash, name_hash)

        # Check cache for existing player (NO DB QUERY)
        player = self._player_cache.get(cache_key)

        if player:
            # Update any missing fields on existing player
            self.stats['players_updated'] += 1
            if gender and not player.gender:
                player.gender = gender
            if self.program and not player.program:
                player.program = self.program
            if parent_first and not player.parent_first_name:
                player.parent_first_name = parent_first
            if parent_last and not player.parent_last_name:
                player.parent_last_name = parent_last
            if parent_phone and not player.parent_phone:
                player.parent_phone = parent_phone
        else:
            # Create new player
            self.stats['players_created'] += 1
            player = Player(
                birth_date=birth_date,
                gender=gender,
                program=self.program
            )
            player.first_name = first_name
            player.last_name = last_name
            player.parent_email = parent_email
            player.parent_first_name = parent_first
            player.parent_last_name = parent_last
            player.parent_phone = parent_phone

            # Generate player code without DB query
            player.player_code = self._generate_player_code_fast(first_name, last_name, birth_date)

            db.session.add(player)
            # Add to cache so subsequent rows can find this player
            self._player_cache[cache_key] = player

        # Create parent user if requested (using cache)
        if create_parent_users:
            parent_user = self._user_cache.get(email_hash)
            if parent_user:
                # User exists, ensure has parent role
                if not parent_user.has_role('parent'):
                    parent_user.add_role('parent')
            else:
                # Create new user directly (avoid User.create_user which commits each time)
                from werkzeug.security import generate_password_hash
                random_password = secrets.token_urlsafe(16)
                try:
                    parent_user = User(role='parent', org_ID=1)
                    parent_user.email = parent_email
                    parent_user.name = parent_name
                    parent_user.phone = parent_phone
                    parent_user.password_hash = generate_password_hash(random_password)
                    db.session.add(parent_user)
                    self.stats['parent_users_created'] += 1
                    # Add to cache
                    self._user_cache[email_hash] = parent_user
                except Exception as e:
                    self.stats['errors'].append(f"Error creating user for {parent_email}: {str(e)}")
                    parent_user = None

            if parent_user and not player.parent_user_id:
                # Need to flush to get IDs if new
                if player.id is None or parent_user.ID is None:
                    db.session.flush()
                player.parent_user_id = parent_user.ID

        # Get prior league from "If your child played..." column
        prior_division_col = [k for k in row.keys() if 'if your child played' in k.lower()]
        prior_division = row.get(prior_division_col[0], '') if prior_division_col else ''
        prior_league_id = self._normalize_league_name(prior_division)

        # Create season record using cache
        # Need player.id, so flush if needed
        if player.id is None:
            db.session.flush()

        season_key = (player.id, self.org_season.ID)
        season_record = self._season_cache.get(season_key)

        if season_record:
            # Update existing
            if division_name:
                season_record.registration_division = division_name
            if prior_league_id:
                season_record.prior_league_id = prior_league_id
        else:
            # Create new
            season_record = PlayerSeason(
                player_id=player.id,
                org_season_id=self.org_season.ID,
                registration_division=division_name,
                prior_league_id=prior_league_id,
                status='registered'
            )
            db.session.add(season_record)
            self._season_cache[season_key] = season_record

        self.stats['season_records_created'] += 1

    def _generate_player_code_fast(self, first_name: str, last_name: str, birth_date) -> str:
        """Generate player code without DB query, using in-memory tracking."""
        last_part = (last_name or 'xxxx')[:4].lower()
        first_part = (first_name or 'xxx')[:3].lower()
        date_part = birth_date.strftime('%m%y') if birth_date else '0000'
        base_code = f"{last_part}{first_part}{date_part}"

        # Check cache of codes we've already seen/generated
        if base_code not in self._player_code_counts:
            # Check if any existing player has this code pattern
            count = 0
            for p in self._player_cache.values():
                if p.player_code and p.player_code.startswith(base_code):
                    count += 1
            self._player_code_counts[base_code] = count

        existing_count = self._player_code_counts[base_code]
        self._player_code_counts[base_code] = existing_count + 1

        if existing_count == 0:
            return base_code
        return f"{base_code}{existing_count + 1}"

    def _import_registration_row(self, row: dict, create_parent_users: bool):
        """Import single registration row (legacy method - slow)."""
        # Extract fields using mapping
        parent_email = self._get_field(row, 'User Email')
        first_name = self._get_field(row, 'Player First Name')
        last_name = self._get_field(row, 'Player Last Name')
        birth_date_str = self._get_field(row, 'Player Birth Date')
        gender_raw = self._get_field(row, 'Player Gender')

        if not parent_email or not first_name or not last_name:
            return  # Skip incomplete rows

        birth_date = self._parse_date(birth_date_str)
        if not birth_date:
            self.stats['errors'].append(
                f"Invalid birth date for {first_name} {last_name}: {birth_date_str}")
            return

        gender = 'M' if gender_raw.lower().startswith('m') else 'F' if gender_raw.lower().startswith('f') else None

        # Parent info
        parent_first = self._get_field(row, 'Account First Name')
        parent_last = self._get_field(row, 'Account Last Name')
        # Try Cellphone first, fallback handled by mapping for 'Cellphone' -> 'phone' etc.
        parent_phone = self._get_field(row, 'Cellphone')
        if not parent_phone:
            # Also try direct 'Telephone' for backwards compatibility
            parent_phone = row.get('Telephone', '').strip()
        parent_name = f"{parent_first} {parent_last}".strip() if parent_first else None

        # Use program specified by user during import
        division_name = self._get_field(row, 'Division Name')

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
