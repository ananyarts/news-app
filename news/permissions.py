"""Role-based permission classes for the REST API.

Each class is used by a view in :mod:`news.api_views`. Django REST
Framework calls ``has_permission`` for every request and
``has_object_permission`` when a single object is retrieved, updated
or deleted.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class ArticlePermission(BasePermission):
    """Control access to articles by role.

    * Any signed-in user may view articles.
    * Only journalists may create articles.
    * Editors may update or delete any article; journalists only their
      own.
    """

    def has_permission(self, request, view):
        """Check the caller's role for the request method."""
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        if request.method == 'POST':
            # Only journalists create articles.
            return user.is_journalist
        return user.is_editor or user.is_journalist

    def has_object_permission(self, request, view, obj):
        """Editors may change any article; journalists only their own."""
        user = request.user
        if request.method in SAFE_METHODS:
            return True
        if user.is_editor:
            return True
        return user.is_journalist and obj.author_id == user.pk


class NewsletterPermission(BasePermission):
    """Control access to newsletters by role.

    * Any signed-in user may view newsletters.
    * Journalists and editors may create newsletters.
    * The newsletter's author or an editor may update or delete it.
    """

    def has_permission(self, request, view):
        """Anyone signed in may read; journalists and editors may write."""
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.is_journalist or user.is_editor

    def has_object_permission(self, request, view, obj):
        """Editors may change any newsletter; others only their own."""
        user = request.user
        if request.method in SAFE_METHODS:
            return True
        return user.is_editor or obj.author_id == user.pk


class IsEditor(BasePermission):
    """Allow only signed-in users with the Editor role."""

    def has_permission(self, request, view):
        """Return True for authenticated editors."""
        user = request.user
        return bool(user and user.is_authenticated and user.is_editor)


class IsReader(BasePermission):
    """Allow only signed-in users with the Reader role."""

    def has_permission(self, request, view):
        """Return True for authenticated readers."""
        user = request.user
        return bool(user and user.is_authenticated and user.is_reader)
