"""Database models"""

from .user import User
from .team import TeamSeason
from .game import Game
from .field import Field
from .field_slot import FieldSlot
from .league import League
from .league_season import LeagueSeason
from .organization import Organization
from .org_season import OrgSeason
from .game_change import GameChange
from .notification_queue import NotificationQueue
from .notification_draft import NotificationDraft
from .umpire_assignment import UmpireAssignment
from .season_blackout import SeasonBlackout
from .field_blackout import FieldBlackout
from .field_allocation_specific import FieldAllocationSpecific
from .practice_pairing import PracticePairing
from .analytics import PageView, Ad, AdImpression, AdClick, generate_session_id
from .app_error import AppError

# Umpire system models
from .umpire_profile import UmpireProfile
from .umpire_guardian import UmpireGuardian
from .umpire_blockout import UmpireBlockout
from .umpire_partner import UmpirePartner
from .partner_contact import PartnerContact
from .partner_payment import PartnerPaymentRecord, PartnerCredit
from .partner_league_rate import PartnerLeagueRate
from .umpire_payment_event import UmpirePaymentEvent
from .game_umpire import GameUmpire
from .umpire_delegation import UmpireDelegationRule, UmpireDelegationOverride
from .umpire_delegation_allocation import UmpireDelegationAllocation
from .delegation_proposal import DelegationProposal, DelegationProposalGame
from .umpire_payment import UmpirePayment
from .coach import CoachSeason
from .scheduled_email import ScheduledEmail
from .weekly_digest import WeeklyDigest
from .umpire_digest import UmpireDigest
from .game_start_record import GameStartRecord
from .field_captain import FieldCaptain
from .umpire_group_assignment import UmpireGroupAssignment
from .umpire_game_payment import UmpireGamePayment
from .umpire_dayof_notification import UmpireDayOfNotification

# Email campaign system
from .email_campaign_template import EmailCampaignTemplate
from .email_campaign_instance import EmailCampaignInstance
from .training_type import TrainingType
from .training_completion import TrainingCompletion

# Assignr webhook integration
from .assignr_webhook_event import AssignrWebhookEvent

# Access request system
from .access_request import AccessRequest

# Post-game reporting
from .post_game_report import PostGameReport

# Institutional knowledge system
from .email_routing_config import EmailRoutingConfig
from .artifact import Artifact
from .role_task import RoleTaskTemplate, RoleTaskInstance
