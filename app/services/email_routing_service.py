"""Email Routing Service - resolves email routing based on configuration."""

from typing import Optional, List, Dict
from app.models.email_routing_config import EmailRoutingConfig
from app.models.user import User


class EmailRoutingService:
    """Service for resolving email routing configuration.

    Handles role-based email resolution and provides routing
    details for different email types.
    """

    def __init__(self, org_id: int = 1):
        self.org_id = org_id

    def get_routing(self, email_type: str) -> Dict:
        """Get routing configuration for an email type.

        Args:
            email_type: The email type constant

        Returns:
            Dict with keys: reply_to, cc_list, bcc_list, from_name
        """
        config = EmailRoutingConfig.get_for_email_type(email_type, self.org_id)

        result = {
            'reply_to': None,
            'cc_list': [],
            'bcc_list': [],
            'from_name': None,
        }

        if not config:
            return result

        # Resolve reply-to
        if config.reply_to_email:
            result['reply_to'] = config.reply_to_email
        elif config.reply_to_role:
            role_email = self._get_role_holder_email(config.reply_to_role)
            if role_email:
                result['reply_to'] = role_email

        # Resolve CC
        cc_emails = config.cc_email_list.copy()
        for role in config.cc_role_list:
            role_email = self._get_role_holder_email(role)
            if role_email and role_email not in cc_emails:
                cc_emails.append(role_email)
        result['cc_list'] = cc_emails

        # BCC
        result['bcc_list'] = config.bcc_email_list

        # From name
        result['from_name'] = config.from_name

        return result

    def get_reply_to(self, email_type: str) -> Optional[str]:
        """Get reply-to address for an email type.

        Args:
            email_type: The email type constant

        Returns:
            Email address or None
        """
        routing = self.get_routing(email_type)
        return routing.get('reply_to')

    def get_cc_list(self, email_type: str) -> List[str]:
        """Get CC list for an email type.

        Args:
            email_type: The email type constant

        Returns:
            List of email addresses
        """
        routing = self.get_routing(email_type)
        return routing.get('cc_list', [])

    def _get_role_holder_email(self, role: str) -> Optional[str]:
        """Find email of current user with a specific role.

        Args:
            role: Role name to look up

        Returns:
            Email address or None if no user has role
        """
        # Find users with this role who are active
        # User.role is a pipe-delimited string, use LIKE for substring match
        users = User.query.filter(
            User.role.contains(role),
            User.active == 1
        ).all()

        # Return first match (could be enhanced to handle multiple)
        for user in users:
            if user.has_role(role) and user.email:
                return user.email

        return None

    def get_role_holder(self, role: str) -> Optional[User]:
        """Get the user who holds a specific role.

        Args:
            role: Role name to look up

        Returns:
            User instance or None
        """
        users = User.query.filter(
            User.role.contains(role),
            User.active == 1
        ).all()

        for user in users:
            if user.has_role(role):
                return user

        return None

    def get_all_role_holders(self) -> Dict[str, List[User]]:
        """Get all users grouped by their roles.

        Returns:
            Dict mapping role names to lists of users
        """
        from app.models.user import User

        result = {}

        # Get key board roles
        key_roles = [
            'admin', 'scheduler', 'umpire_coordinator',
            'coaching_coordinator', 'treasurer', 'facilities',
            'BB_VP', 'SB_VP', 'BoardExec'
        ]

        for role in key_roles:
            users = User.query.filter(
                User.role.contains(role),
                User.active == 1
            ).all()

            # Filter to only those who actually have the role
            holders = [u for u in users if u.has_role(role)]
            if holders:
                result[role] = holders

        return result


def get_email_routing(email_type: str, org_id: int = 1) -> Dict:
    """Convenience function to get routing for an email type.

    Args:
        email_type: The email type constant
        org_id: Organization ID

    Returns:
        Dict with routing configuration
    """
    service = EmailRoutingService(org_id)
    return service.get_routing(email_type)
