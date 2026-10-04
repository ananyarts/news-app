"""Role-based permission classes for the API."""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class ArticlePermission(BasePermission):
    """Readers view; journalists create; editors and owning journalists
    update/delete."""

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
    """Signed-in users view; journalists and editors create; the author
    or an editor updates and deletes."""

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
