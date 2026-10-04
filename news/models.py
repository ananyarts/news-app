"""Database models for the news application.

Tables are normalised: each entity (user, publisher, article,
newsletter, approval log) lives in its own table, and relationships use
foreign keys and many-to-many join tables instead of repeated columns.
"""

from django.contrib.auth.models import AbstractUser, Group
from django.core.exceptions import ValidationError
from django.db import models


class Role(models.TextChoices):
    """The roles a user can hold. Each role maps to a Django group."""

    READER = 'reader', 'Reader'
    JOURNALIST = 'journalist', 'Journalist'
    EDITOR = 'editor', 'Editor'


# Group names are the role labels, e.g. "Reader".
ROLE_GROUP_NAMES = {role.value: role.label for role in Role}


class CustomUser(AbstractUser):
    """A user with a role that decides their group and permissions.

    Reader-only fields: ``subscribed_publishers`` and
    ``subscribed_journalists``.
    Journalist-only data: ``articles`` and ``newsletters`` (reverse
    relations from :class:`Article` and :class:`Newsletter`).
    """

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.READER
    )
    email = models.EmailField(blank=True)
    subscribed_publishers = models.ManyToManyField(
        'Publisher', blank=True, related_name='subscribers'
    )
    subscribed_journalists = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='subscribers',
        limit_choices_to={'role': Role.JOURNALIST},
    )

    @property
    def is_reader(self):
        """True if the user has the Reader role."""
        return self.role == Role.READER

    @property
    def is_journalist(self):
        """True if the user has the Journalist role."""
        return self.role == Role.JOURNALIST

    @property
    def is_editor(self):
        """True if the user has the Editor role."""
        return self.role == Role.EDITOR

    def save(self, *args, **kwargs):
        """Save the user, then sync their group and role fields."""
        super().save(*args, **kwargs)
        self.assign_group()
        self.clear_fields_for_other_roles()

    def assign_group(self):
        """Put the user in the one group that matches their role."""
        group, _ = Group.objects.get_or_create(
            name=ROLE_GROUP_NAMES[self.role]
        )
        role_groups = self.groups.filter(name__in=ROLE_GROUP_NAMES.values())
        self.groups.remove(*role_groups.exclude(pk=group.pk))
        self.groups.add(group)

    def clear_fields_for_other_roles(self):
        """Clear ("None") fields that don't belong to the user's role.

        Journalists and editors have no subscriptions. Readers and
        editors own no independently published articles or newsletters.
        """
        if not self.is_reader:
            self.subscribed_publishers.clear()
            self.subscribed_journalists.clear()
        if not self.is_journalist:
            # Unlink rather than delete so content is not lost.
            self.articles.update(author=None)
            self.newsletters.update(author=None)

    def __str__(self):
        """Show the user's name (or username) and role."""
        return f'{self.get_full_name() or self.username} ({self.role})'


class Publisher(models.Model):
    """A curated publication with its own editors and journalists."""

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    editors = models.ManyToManyField(
        CustomUser,
        blank=True,
        related_name='edited_publishers',
        limit_choices_to={'role': Role.EDITOR},
    )
    journalists = models.ManyToManyField(
        CustomUser,
        blank=True,
        related_name='publishers',
        limit_choices_to={'role': Role.JOURNALIST},
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        """Show the publisher's name."""
        return self.name


class Article(models.Model):
    """A news article written by a journalist.

    With no ``publisher`` the article is independent; otherwise it is
    publisher content. It becomes public once an editor approves it.
    """

    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='articles',
        limit_choices_to={'role': Role.JOURNALIST},
    )
    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='articles',
    )
    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_articles',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('approve_article', 'Can approve articles for publication'),
        ]

    @property
    def is_independent(self):
        """True if the article has no publisher."""
        return self.publisher_id is None

    def clean(self):
        """An article needs a journalist or a publisher to belong to."""
        if self.author_id is None and self.publisher_id is None:
            raise ValidationError(
                'An article must belong to a journalist or a publisher.'
            )

    def __str__(self):
        """Show the article's title."""
        return self.title


class Newsletter(models.Model):
    """A curated collection of articles."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    author = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='newsletters',
    )
    articles = models.ManyToManyField(
        Article, blank=True, related_name='newsletters'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        """Show the newsletter's title."""
        return self.title


class ApprovedArticleLog(models.Model):
    """A record saved by ``/api/approved/`` for each approval."""

    article = models.ForeignKey(
        Article, on_delete=models.CASCADE, related_name='approval_logs'
    )
    title = models.CharField(max_length=200)
    author_name = models.CharField(max_length=150, blank=True)
    publisher_name = models.CharField(max_length=150, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        """Show which article was approved."""
        return f'Approved: {self.title}'
