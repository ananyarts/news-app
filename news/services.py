"""Business logic for approving articles (Option 2: no signals).

The approval view (web and API) calls :func:`approve_article`, which
marks the article approved, emails subscribers and posts the article
to the internal ``/api/approved/`` endpoint.
"""

import logging

import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .models import CustomUser, Role

logger = logging.getLogger(__name__)


def get_subscriber_emails(article):
    """Return the emails of readers subscribed to an article's source.

    A reader is included if they follow the article's journalist or its
    publisher. Readers without an email address are skipped.

    Args:
        article (Article): The article whose subscribers are wanted.

    Returns:
        list[str]: Unique email addresses, sorted alphabetically. Empty
        if the article has neither an author nor a publisher.
    """
    subscription_filter = Q()
    if article.author_id:
        subscription_filter |= Q(subscribed_journalists=article.author)
    if article.publisher_id:
        subscription_filter |= Q(subscribed_publishers=article.publisher)
    if not subscription_filter:
        return []
    emails = (
        CustomUser.objects.filter(subscription_filter, role=Role.READER)
        .exclude(email='')
        .values_list('email', flat=True)
        .distinct()
    )
    return sorted(emails)


def email_subscribers(article):
    """Email the approved article to its subscribers.

    Subscribers are sent the article by Bcc so their addresses stay
    private. Mail errors are logged, not raised, so a mail outage never
    blocks an approval.

    Args:
        article (Article): The approved article to send.

    Returns:
        int: The number of recipients, or 0 if there were none or the
        email could not be sent.
    """
    recipients = get_subscriber_emails(article)
    if not recipients:
        return 0

    source = article.publisher.name if article.publisher else 'Independent'
    author = article.author
    byline = (author.get_full_name() or author.username) if author else ''
    body = (
        f'{article.title}\n'
        f'By {byline} - {source}\n\n'
        f'{article.content}\n'
    )
    message = EmailMessage(
        subject=f'New article: {article.title}',
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        # Bcc keeps subscribers' addresses private from each other.
        bcc=recipients,
    )
    try:
        message.send()
    except Exception:  # noqa: BLE001 - any mail backend failure
        logger.exception('Could not email subscribers of article %s',
                         article.pk)
        return 0
    return len(recipients)


def post_to_approved_api(article, editor):
    """POST the approved article to the ``/api/approved/`` endpoint.

    The request is authenticated with the approving editor's API token,
    which is created if the editor does not have one yet. Network and
    HTTP errors are logged, not raised.

    Args:
        article (Article): The approved article to log.
        editor (CustomUser): The editor who approved the article.

    Returns:
        bool: True if the endpoint accepted the article, otherwise False.
    """
    token, _ = Token.objects.get_or_create(user=editor)
    payload = {
        'article': article.pk,
        'title': article.title,
        'author_name': article.author.username if article.author else '',
        'publisher_name': article.publisher.name if article.publisher else '',
    }
    try:
        response = requests.post(
            settings.APPROVED_API_URL,
            json=payload,
            headers={'Authorization': f'Token {token.key}'},
            timeout=settings.APPROVED_API_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception('Could not post article %s to %s',
                         article.pk, settings.APPROVED_API_URL)
        return False
    return True


def approve_article(article, editor):
    """Approve ``article`` as ``editor`` and share it.

    The article is marked approved and stamped with the editor and the
    time. Once the database transaction commits, subscribers are emailed
    and the article is posted to ``/api/approved/``.

    Args:
        article (Article): The article to approve.
        editor (CustomUser): The user approving the article.

    Returns:
        Article: The updated, approved article.

    Raises:
        PermissionError: If ``editor`` does not have the Editor role.
        ValueError: If the article has already been approved.
    """
    if not editor.is_editor:
        raise PermissionError('Only editors can approve articles.')
    if article.approved:
        raise ValueError('This article has already been approved.')

    article.approved = True
    article.approved_by = editor
    article.approved_at = timezone.now()
    article.save(update_fields=['approved', 'approved_by', 'approved_at',
                                'updated_at'])

    # Notify only once the approval is committed to the database.
    transaction.on_commit(lambda: _share_article(article, editor))
    return article


def _share_article(article, editor):
    """Email subscribers and log the article at ``/api/approved/``.

    Args:
        article (Article): The newly approved article.
        editor (CustomUser): The editor who approved it.
    """
    email_subscribers(article)
    post_to_approved_api(article, editor)
