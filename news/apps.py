"""App configuration for the ``news`` app."""

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class NewsConfig(AppConfig):
    """Configure the app and hook up role-group creation."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'news'

    def ready(self):
        """Create role groups and their permissions after every migrate."""
        from .groups import setup_role_groups

        post_migrate.connect(
            lambda sender, **kwargs: setup_role_groups(),
            sender=self,
            weak=False,
            dispatch_uid='news_setup_role_groups',
        )
