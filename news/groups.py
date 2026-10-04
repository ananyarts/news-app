"""Create the role groups and give each one its permissions."""

from django.contrib.auth.models import Group, Permission

from .models import ROLE_GROUP_NAMES, Role

# Permission codenames granted to each role's group.
ROLE_PERMISSIONS = {
    Role.READER: [
        'view_article',
        'view_newsletter',
        'view_publisher',
    ],
    Role.EDITOR: [
        'view_article', 'change_article', 'delete_article',
        'approve_article',
        'view_newsletter', 'change_newsletter', 'delete_newsletter',
        # Editors manage publishers and their staff.
        'add_publisher', 'view_publisher', 'change_publisher',
        'delete_publisher',
    ],
    Role.JOURNALIST: [
        'add_article', 'view_article', 'change_article', 'delete_article',
        'add_newsletter', 'view_newsletter', 'change_newsletter',
        'delete_newsletter',
        'view_publisher',
    ],
}


def setup_role_groups():
    """Create (or refresh) the Reader, Editor and Journalist groups."""
    for role, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=ROLE_GROUP_NAMES[role])
        permissions = Permission.objects.filter(
            content_type__app_label='news', codename__in=codenames
        )
        group.permissions.set(permissions)
