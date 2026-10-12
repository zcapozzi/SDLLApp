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
        from app.utils.encryption import hash_for_lookup, get_fernet
        from werkzeug.security import generate_password_hash
        import hashlib

        self.program = program
        self.column_mapping = column_mapping
        self._hash_for_lookup = hash_for_lookup  # Cache function reference
        self._generate_password_hash = generate_password_hash

        # Cache Fernet instance ONCE - avoid recreating for every field
        self._fernet = get_fernet()

        # Fast hash function (avoid function call overhead)
        def fast_hash(value):
            if value is None:
                return None
            return hashlib.sha256(value.lower().strip().encode()).hexdigest()
        self._fast_hash = fast_hash

        # Fast encrypt function using cached Fernet
        def fast_encrypt(value):
            if value is None:
                return None
            return self._fernet.encrypt(value.encode()).decode()
        self._fast_encrypt = fast_encrypt
        self.stats = {
            'players_created': 0,
            'players_updated': 0,
            'parent_users_created': 0,
            'season_records_created': 0,
            'evaluations_created': 0,
            'errors': []
        }

        # Pre-load existing data using ONLY columns needed for lookup (much faster)
        # Use with_entities to avoid loading full ORM objects and encrypted data

        # Players: only need id, hashes, player_code for lookups
        player_rows = db.session.query(
            Player.id, Player.parent_email_hash, Player.name_hash, Player.player_code
        ).all()
        self._player_cache = {}  # (email_hash, name_hash) -> player_id
        self._player_id_cache = {}  # cache player_id for existing players
        self._existing_player_codes = set()
        for pid, email_hash, name_hash, pcode in player_rows:
            key = (email_hash, name_hash)
            self._player_cache[key] = pid  # Just store ID, not full object
            self._player_id_cache[key] = pid
            if pcode:
                self._existing_player_codes.add(pcode)

        # Users: only need ID and email_hash for lookups
        user_rows = db.session.query(User.ID, User.email_hash).all()
        self._user_cache = {email_hash: uid for uid, email_hash in user_rows if email_hash}

        # Player seasons: only need player_id for existence check
        season_rows = db.session.query(PlayerSeason.player_id).filter_by(
            org_season_id=self.org_season.ID
        ).all()
        self._season_cache = {pid for (pid,) in season_rows}  # Just a set of player_ids

        # Track new records as dicts for bulk insert
        self._new_players = []  # List of dicts for bulk insert
        self._new_users = []
        self._new_seasons = []
        self._player_code_counts = {}

        # Track which new players need linking to users (by index)
        self._player_user_links = []  # (player_index, email_hash)

        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

            # Find prior division column once (not per row)
            self._prior_division_col = None
            if rows:
                for k in rows[0].keys():
                    if 'if your child played' in k.lower():
                        self._prior_division_col = k
                        break

            # Process all rows - collect data only, no DB operations
            for i, row in enumerate(rows):
                row_num = i + 2
                try:
                    self._collect_row_data(row, create_parent_users)
                except Exception as e:
                    self.stats['errors'].append(f"Row {row_num}: {str(e)}")

        # Bulk insert all new records at once
        self._bulk_insert_all()
        db.session.commit()
        return self.stats

    def _collect_row_data(self, row: dict, create_parent_users: bool):
        """Collect row data into insert lists (no DB operations)."""
        # Extract fields using mapping
        parent_email = self._get_field(row, 'User Email')
        first_name = self._get_field(row, 'Player First Name')
        last_name = self._get_field(row, 'Player Last Name')
        birth_date_str = self._get_field(row, 'Player Birth Date')
        gender_raw = self._get_field(row, 'Player Gender')

        if not parent_email or not first_name or not last_name:
            return

        birth_date = self._parse_date(birth_date_str)
        if not birth_date:
            self.stats['errors'].append(
                f"Invalid birth date for {first_name} {last_name}: {birth_date_str}")
            return

        gender = 'M' if gender_raw.lower().startswith('m') else 'F' if gender_raw.lower().startswith('f') else None

        parent_first = self._get_field(row, 'Account First Name')
        parent_last = self._get_field(row, 'Account Last Name')
        parent_phone = self._get_field(row, 'Cellphone')
        if not parent_phone:
            parent_phone = row.get('Telephone', '').strip()
        parent_name = f"{parent_first} {parent_last}".strip() if parent_first else None

        division_name = self._get_field(row, 'Division Name')

        # Compute hashes
        email_hash = self._fast_hash(parent_email)
        name_normalized = f"{first_name}{last_name}".lower().replace(' ', '').replace('-', '')
        name_hash = self._fast_hash(name_normalized)
        cache_key = (email_hash, name_hash)

        # Check if player exists
        existing_player_id = self._player_cache.get(cache_key)

        if existing_player_id:
            # Existing player - just need to maybe create season record
            self.stats['players_updated'] += 1
            player_id = existing_player_id
        else:
            # New player - add to bulk insert list
            self.stats['players_created'] += 1
            player_code = self._generate_player_code_fast(first_name, last_name, birth_date)

            player_dict = {
                'birth_date': birth_date,
                'gender': gender,
                'program': self.program,
                'first_name': self._fast_encrypt(first_name),  # DB column name
                'last_name': self._fast_encrypt(last_name),
                'parent_email': self._fast_encrypt(parent_email),
                'parent_email_hash': email_hash,
                'name_hash': name_hash,
                'parent_first_name': self._fast_encrypt(parent_first) if parent_first else None,
                'parent_last_name': self._fast_encrypt(parent_last) if parent_last else None,
                'parent_phone': self._fast_encrypt(parent_phone) if parent_phone else None,
                'player_code': player_code,
            }
            player_index = len(self._new_players)
            self._new_players.append(player_dict)

            # Mark for user linking later
            if create_parent_users:
                self._player_user_links.append((player_index, email_hash))

            # Add to cache so duplicate rows find this player
            self._player_cache[cache_key] = f"NEW_{player_index}"  # Placeholder
            player_id = f"NEW_{player_index}"

        # Handle parent user
        if create_parent_users:
            existing_user_id = self._user_cache.get(email_hash)
            # Check cache - already handles both existing and pending new users
            if not existing_user_id:
                # New user
                random_password = secrets.token_urlsafe(16)
                user_dict = {
                    'role': 'parent',
                    'org_ID': 1,
                    'email': self._fast_encrypt(parent_email),  # DB column name
                    'email_hash': email_hash,
                    'name': self._fast_encrypt(parent_name) if parent_name else None,
                    'phone': self._fast_encrypt(parent_phone) if parent_phone else None,
                    'password_hash': self._generate_password_hash(
                        random_password, method='pbkdf2:sha256:1000'
                    ),
                    'active': 1,
                }
                self._new_users.append(user_dict)
                self.stats['parent_users_created'] += 1
                self._user_cache[email_hash] = f"NEW"  # Placeholder

        # Handle season record
        prior_division = ''
        if self._prior_division_col:
            prior_division = row.get(self._prior_division_col, '')
        prior_league_id = self._normalize_league_name(prior_division)

        # For existing players, check if season exists
        if isinstance(player_id, int):
            if player_id not in self._season_cache:
                self._new_seasons.append({
                    'player_id': player_id,
                    'org_season_id': self.org_season.ID,
                    'registration_division': division_name,
                    'prior_league_id': prior_league_id,
                    'status': 'registered',
                })
                self._season_cache.add(player_id)
        else:
            # New player - store season data to create after player insert
            player_index = int(player_id.split('_')[1])
            self._new_players[player_index]['_season'] = {
                'registration_division': division_name,
                'prior_league_id': prior_league_id,
            }

        self.stats['season_records_created'] += 1

    def _bulk_insert_all(self):
        """Perform bulk inserts for all collected data."""
        from sqlalchemy import insert

        # Bulk insert users first (to get IDs for linking)
        if self._new_users:
            db.session.execute(insert(User), self._new_users)
            db.session.flush()

            # Reload all new user IDs in ONE query
            new_email_hashes = [u['email_hash'] for u in self._new_users]
            user_id_rows = db.session.query(User.ID, User.email_hash).filter(
                User.email_hash.in_(new_email_hashes)
            ).all()
            for uid, email_hash in user_id_rows:
                self._user_cache[email_hash] = uid

        # Bulk insert players
        if self._new_players:
            # Extract season data before insert
            seasons_to_create = []
            player_inserts = []
            for i, p in enumerate(self._new_players):
                season_data = p.pop('_season', None)
                player_inserts.append(p)
                if season_data:
                    seasons_to_create.append((i, season_data))

            db.session.execute(insert(Player), player_inserts)
            db.session.flush()

            # Get ALL inserted player IDs in ONE query
            new_player_codes = [p['player_code'] for p in player_inserts]
            player_id_rows = db.session.query(Player.id, Player.player_code, Player.parent_email_hash).filter(
                Player.player_code.in_(new_player_codes)
            ).all()

            # Build code -> (id, email_hash) mapping
            code_to_data = {pcode: (pid, email_hash) for pid, pcode, email_hash in player_id_rows}

            # Build list of player-user links for batch update
            player_user_updates = []
            for i, p in enumerate(player_inserts):
                player_id, email_hash = code_to_data.get(p['player_code'], (None, None))
                p['_inserted_id'] = player_id

                # Collect user link updates
                if player_id:
                    user_id = self._user_cache.get(email_hash or p['parent_email_hash'])
                    if user_id and isinstance(user_id, int):
                        player_user_updates.append({'pid': player_id, 'uid': user_id})

            # Batch update player-user links
            if player_user_updates:
                db.session.execute(
                    db.text("UPDATE sdll_players SET parent_user_id = :uid WHERE id = :pid"),
                    player_user_updates
                )

            # Create season records for new players
            for i, season_data in seasons_to_create:
                player_id = player_inserts[i].get('_inserted_id')
                if player_id:
                    self._new_seasons.append({
                        'player_id': player_id,
                        'org_season_id': self.org_season.ID,
                        'registration_division': season_data['registration_division'],
                        'prior_league_id': season_data['prior_league_id'],
                        'status': 'registered',
                    })

        # Bulk insert seasons
        if self._new_seasons:
            db.session.execute(insert(PlayerSeason), self._new_seasons)

    def _flush_pending(self):
        """Flush pending records and create season records that need player IDs."""
        if self._pending_players or self._pending_users:
            db.session.flush()

        # Link players to parent users now that we have IDs
        for player in self._pending_players:
            if not player.parent_user_id and player.parent_email_hash:
                parent_user = self._user_cache.get(player.parent_email_hash)
                if parent_user and parent_user.ID:
                    player.parent_user_id = parent_user.ID

        # Now create season records for pending players
        for player, division_name, prior_league_id in self._pending_seasons:
            season_key = (player.id, self.org_season.ID)
            if season_key not in self._season_cache:
                season_record = PlayerSeason(
                    player_id=player.id,
                    org_season_id=self.org_season.ID,
                    registration_division=division_name,
                    prior_league_id=prior_league_id,
                    status='registered'
                )
                db.session.add(season_record)
                self._season_cache[season_key] = season_record

        # Clear pending lists
        self._pending_players = []
        self._pending_users = []
        self._pending_seasons = []

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

        # Compute hashes for cache lookup (use fast inline hash)
        email_hash = self._fast_hash(parent_email)
        name_normalized = f"{first_name}{last_name}".lower().replace(' ', '').replace('-', '')
        name_hash = self._fast_hash(name_normalized)
        cache_key = (email_hash, name_hash)

        # Check cache for existing player (NO DB QUERY)
        player = self._player_cache.get(cache_key)
        is_new_player = player is None

        if player:
            # Update any missing fields on existing player (use property setters for updates - rare)
            self.stats['players_updated'] += 1
            if gender and not player.gender:
                player.gender = gender
            if self.program and not player.program:
                player.program = self.program
            if parent_first and not player._parent_first_name:
                player._parent_first_name = self._fast_encrypt(parent_first)
            if parent_last and not player._parent_last_name:
                player._parent_last_name = self._fast_encrypt(parent_last)
            if parent_phone and not player._parent_phone:
                player._parent_phone = self._fast_encrypt(parent_phone)
        else:
            # Create new player - use direct column assignment to bypass property setters
            self.stats['players_created'] += 1

            # Pre-compute all encrypted values and hashes
            encrypted_first = self._fast_encrypt(first_name)
            encrypted_last = self._fast_encrypt(last_name)
            encrypted_email = self._fast_encrypt(parent_email)
            encrypted_parent_first = self._fast_encrypt(parent_first) if parent_first else None
            encrypted_parent_last = self._fast_encrypt(parent_last) if parent_last else None
            encrypted_phone = self._fast_encrypt(parent_phone) if parent_phone else None

            player = Player(
                birth_date=birth_date,
                gender=gender,
                program=self.program
            )
            # Direct assignment to encrypted columns (bypasses property setters)
            player._first_name = encrypted_first
            player._last_name = encrypted_last
            player._parent_email = encrypted_email
            player.parent_email_hash = email_hash  # Already computed above
            player.name_hash = name_hash  # Already computed above
            player._parent_first_name = encrypted_parent_first
            player._parent_last_name = encrypted_parent_last
            player._parent_phone = encrypted_phone

            # Generate player code without DB query
            player.player_code = self._generate_player_code_fast(first_name, last_name, birth_date)

            db.session.add(player)
            self._pending_players.append(player)
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
                # Create new user with direct column assignment (bypass property setters)
                random_password = secrets.token_urlsafe(16)
                parent_user = User(role='parent', org_ID=1)
                # Direct assignment to encrypted columns
                parent_user._email = self._fast_encrypt(parent_email)
                parent_user.email_hash = email_hash  # Already computed
                parent_user._name = self._fast_encrypt(parent_name) if parent_name else None
                parent_user._phone = self._fast_encrypt(parent_phone) if parent_phone else None
                parent_user.password_hash = self._generate_password_hash(
                    random_password, method='pbkdf2:sha256:1000'
                )
                db.session.add(parent_user)
                self._pending_users.append(parent_user)
                self.stats['parent_users_created'] += 1
                # Add to cache immediately so duplicate emails in CSV don't create duplicates
                self._user_cache[email_hash] = parent_user

            # Link player to user - will be done after flush when IDs are available
            if parent_user and not player.parent_user_id:
                if player.id is not None and parent_user.ID is not None:
                    player.parent_user_id = parent_user.ID
                # else: will be linked after batch flush

        # Get prior league from pre-computed column name
        prior_division = ''
        if self._prior_division_col:
            prior_division = row.get(self._prior_division_col, '')
        prior_league_id = self._normalize_league_name(prior_division)

        # Handle season record
        if player.id is not None:
            # Existing player - can create/update season record immediately
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
        else:
            # New player - defer season record creation until after flush
            self._pending_seasons.append((player, division_name, prior_league_id))

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
            # Use _existing_player_codes set which contains actual player codes
            count = 0
            for pcode in self._existing_player_codes:
                if pcode and pcode.startswith(base_code):
                    count += 1
            self._player_code_counts[base_code] = count

        existing_count = self._player_code_counts[base_code]
        self._player_code_counts[base_code] = existing_count + 1

        if existing_count == 0:
            new_code = base_code
        else:
            new_code = f"{base_code}{existing_count + 1}"

        # Add to set so subsequent generations don't collide
        self._existing_player_codes.add(new_code)
        return new_code

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
