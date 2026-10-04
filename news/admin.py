"""Django admin configuration.

Site administrators (superusers) can manage every model here, including
publishers and the editors and journalists that belong to them.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    ApprovedArticleLog, Article, CustomUser, Newsletter, Publisher,
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """User admin with the role and reader subscription fields."""

    list_display = ['username', 'email', 'role', 'is_staff']
    list_filter = ['role', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        ('Role & subscriptions', {
            'fields': ('role', 'subscribed_publishers',
                       'subscribed_journalists'),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role', {'fields': ('role', 'email')}),
    )
    filter_horizontal = ['groups', 'user_permissions',
                         'subscribed_publishers', 'subscribed_journalists']


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    """Publisher admin with pickers for its editors and journalists."""

    list_display = ['name', 'created_at']
    filter_horizontal = ['editors', 'journalists']
    search_fields = ['name']


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Article admin, filterable by approval status and publisher."""

    list_display = ['title', 'author', 'publisher', 'approved', 'created_at']
    list_filter = ['approved', 'publisher']
    search_fields = ['title', 'content']


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    """Newsletter admin with a picker for its articles."""

    list_display = ['title', 'author', 'created_at']
    filter_horizontal = ['articles']


@admin.register(ApprovedArticleLog)
class ApprovedArticleLogAdmin(admin.ModelAdmin):
    """Read the records saved by ``/api/approved/``."""

    list_display = ['title', 'author_name', 'publisher_name', 'received_at']
