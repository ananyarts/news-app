"""Automated tests for the news REST API and approval workflow."""

from unittest import mock

import requests
from django.contrib.auth.models import Group
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from news.models import (
    ApprovedArticleLog, Article, CustomUser, Newsletter, Publisher, Role,
)


def make_user(username, role, **extra):
    """Create a user with a known password and an example email."""
    return CustomUser.objects.create_user(
        username=username, password='S3cure-pass!', role=role,
        email=f'{username}@example.com', **extra,
    )


class NewsAPITestCase(APITestCase):
    """Shared fixtures: one user per role, publishers and articles."""

    def setUp(self):
        self.reader = make_user('reader', Role.READER)
        self.other_reader = make_user('other_reader', Role.READER)
        self.journalist = make_user('journalist', Role.JOURNALIST)
        self.other_journalist = make_user('other_journalist',
                                          Role.JOURNALIST)
        self.editor = make_user('editor', Role.EDITOR)

        self.daily = Publisher.objects.create(name='The Daily')
        self.weekly = Publisher.objects.create(name='The Weekly')
        self.daily.journalists.add(self.journalist)
        self.daily.editors.add(self.editor)

        self.daily_article = Article.objects.create(
            title='Daily story', content='...', author=self.other_journalist,
            publisher=self.daily, approved=True,
        )
        self.weekly_article = Article.objects.create(
            title='Weekly story', content='...',
            author=self.other_journalist, publisher=self.weekly,
            approved=True,
        )
        self.independent_article = Article.objects.create(
            title='Independent story', content='...',
            author=self.journalist, approved=True,
        )
        self.pending_article = Article.objects.create(
            title='Pending story', content='...', author=self.journalist,
            publisher=self.daily, approved=False,
        )

    def authenticate(self, user):
        """Authenticate the test client with the user's API token."""
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    @staticmethod
    def ids(response):
        """Return the set of ids in a list response."""
        return {item['id'] for item in response.data}


class UserRoleTests(NewsAPITestCase):
    """Users join the group for their role, with the right permissions."""

    def test_users_are_added_to_the_group_for_their_role(self):
        self.assertTrue(self.reader.groups.filter(name='Reader').exists())
        self.assertTrue(
            self.journalist.groups.filter(name='Journalist').exists()
        )
        self.assertTrue(self.editor.groups.filter(name='Editor').exists())

    def test_group_permissions_match_roles(self):
        reader = CustomUser.objects.get(pk=self.reader.pk)
        journalist = CustomUser.objects.get(pk=self.journalist.pk)
        editor = CustomUser.objects.get(pk=self.editor.pk)
        self.assertTrue(reader.has_perm('news.view_article'))
        self.assertFalse(reader.has_perm('news.change_article'))
        self.assertTrue(journalist.has_perm('news.add_article'))
        self.assertTrue(journalist.has_perm('news.delete_newsletter'))
        self.assertFalse(editor.has_perm('news.add_article'))
        self.assertTrue(editor.has_perm('news.approve_article'))

    def test_changing_role_moves_group_and_clears_reader_fields(self):
        self.reader.subscribed_publishers.add(self.daily)
        self.reader.role = Role.JOURNALIST
        self.reader.save()
        self.assertEqual(self.reader.subscribed_publishers.count(), 0)
        self.assertEqual(
            list(self.reader.groups.values_list('name', flat=True)),
            ['Journalist'],
        )
        self.assertFalse(Group.objects.get(name='Reader').user_set.filter(
            pk=self.reader.pk).exists())


class AuthenticationTests(NewsAPITestCase):
    """Token login succeeds and fails correctly; anonymous calls fail."""

    def test_token_endpoint_returns_token_for_valid_credentials(self):
        response = self.client.post(reverse('api-token'), {
            'username': 'reader', 'password': 'S3cure-pass!',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)

    def test_token_endpoint_rejects_bad_credentials(self):
        response = self.client.post(reverse('api-token'), {
            'username': 'reader', 'password': 'wrong',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_requests_are_rejected(self):
        response = self.client.get(reverse('article-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ArticleReadTests(NewsAPITestCase):
    """Listing and retrieving articles per role."""

    def test_list_returns_only_approved_articles_for_every_role(self):
        for user in (self.reader, self.journalist, self.editor):
            self.authenticate(user)
            response = self.client.get(reverse('article-list'))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertNotIn(self.pending_article.pk, self.ids(response))
            self.assertEqual(len(response.data), 3)

    def test_retrieve_single_article(self):
        self.authenticate(self.reader)
        url = reverse('article-detail', args=[self.daily_article.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Daily story')

    def test_reader_cannot_retrieve_pending_article(self):
        self.authenticate(self.reader)
        url = reverse('article-detail', args=[self.pending_article.pk])
        self.assertEqual(self.client.get(url).status_code,
                         status.HTTP_404_NOT_FOUND)

    def test_author_and_editor_can_retrieve_pending_article(self):
        url = reverse('article-detail', args=[self.pending_article.pk])
        for user in (self.journalist, self.editor):
            self.authenticate(user)
            self.assertEqual(self.client.get(url).status_code,
                             status.HTTP_200_OK)


class SubscribedArticleTests(NewsAPITestCase):
    """GET /api/articles/subscribed/ returns only subscribed content."""

    url = reverse('article-subscribed')

    def test_reader_gets_only_subscribed_publisher_articles(self):
        self.reader.subscribed_publishers.add(self.daily)
        self.authenticate(self.reader)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Pending Daily article is excluded; Weekly is not subscribed.
        self.assertEqual(self.ids(response), {self.daily_article.pk})

    def test_reader_gets_subscribed_journalist_articles(self):
        self.reader.subscribed_journalists.add(self.journalist)
        self.authenticate(self.reader)
        response = self.client.get(self.url)
        self.assertEqual(self.ids(response), {self.independent_article.pk})

    def test_combined_subscriptions_have_no_duplicates(self):
        self.reader.subscribed_publishers.add(self.daily, self.weekly)
        self.reader.subscribed_journalists.add(self.other_journalist)
        self.authenticate(self.reader)
        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(
            self.ids(response),
            {self.daily_article.pk, self.weekly_article.pk},
        )

    def test_reader_without_subscriptions_gets_nothing(self):
        self.reader.subscribed_publishers.add(self.daily)
        self.authenticate(self.other_reader)
        response = self.client.get(self.url)
        self.assertEqual(response.data, [])

    def test_non_readers_cannot_use_subscribed_feed(self):
        self.authenticate(self.journalist)
        self.assertEqual(self.client.get(self.url).status_code,
                         status.HTTP_403_FORBIDDEN)


class ArticleWriteTests(NewsAPITestCase):
    """Creating, updating and deleting articles per role."""

    def test_journalist_can_create_article_which_starts_unapproved(self):
        self.authenticate(self.journalist)
        response = self.client.post(reverse('article-list'), {
            'title': 'Breaking', 'content': 'News!',
            'publisher': self.daily.pk, 'approved': True,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        article = Article.objects.get(pk=response.data['id'])
        self.assertEqual(article.author, self.journalist)
        self.assertFalse(article.approved)

    def test_journalist_can_create_independent_article(self):
        self.authenticate(self.journalist)
        response = self.client.post(reverse('article-list'), {
            'title': 'Solo', 'content': 'Independent.',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data['publisher'])

    def test_journalist_cannot_post_to_publisher_they_do_not_write_for(self):
        self.authenticate(self.journalist)
        response = self.client.post(reverse('article-list'), {
            'title': 'Sneaky', 'content': '...', 'publisher': self.weekly.pk,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_article_data_is_rejected(self):
        self.authenticate(self.journalist)
        response = self.client.post(reverse('article-list'), {
            'title': '   ',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('content', response.data)

    def test_reader_and_editor_cannot_create_articles(self):
        for user in (self.reader, self.editor):
            self.authenticate(user)
            response = self.client.post(reverse('article-list'), {
                'title': 'Nope', 'content': '...',
            }, format='json')
            self.assertEqual(response.status_code,
                             status.HTTP_403_FORBIDDEN)

    def test_journalist_can_update_own_article(self):
        self.authenticate(self.journalist)
        url = reverse('article-detail', args=[self.pending_article.pk])
        response = self.client.put(url, {
            'title': 'Updated', 'content': 'New content',
            'publisher': self.daily.pk,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_article.refresh_from_db()
        self.assertEqual(self.pending_article.title, 'Updated')

    def test_journalist_cannot_update_someone_elses_article(self):
        self.authenticate(self.journalist)
        url = reverse('article-detail', args=[self.daily_article.pk])
        response = self.client.put(url, {
            'title': 'Hijack', 'content': '...',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_update_any_article(self):
        self.authenticate(self.editor)
        url = reverse('article-detail', args=[self.daily_article.pk])
        response = self.client.put(url, {
            'title': 'Edited', 'content': 'Copy-edited.',
            'publisher': self.daily.pk,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reader_cannot_update_or_delete(self):
        self.authenticate(self.reader)
        url = reverse('article-detail', args=[self.daily_article.pk])
        self.assertEqual(
            self.client.put(url, {'title': 'x', 'content': 'y'},
                            format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(url).status_code,
                         status.HTTP_403_FORBIDDEN)
        self.assertTrue(Article.objects.filter(
            pk=self.daily_article.pk).exists())

    def test_editor_can_delete_article(self):
        self.authenticate(self.editor)
        url = reverse('article-detail', args=[self.daily_article.pk])
        self.assertEqual(self.client.delete(url).status_code,
                         status.HTTP_204_NO_CONTENT)
        self.assertFalse(Article.objects.filter(
            pk=self.daily_article.pk).exists())

    def test_journalist_can_delete_own_but_not_others_articles(self):
        self.authenticate(self.journalist)
        own = reverse('article-detail', args=[self.independent_article.pk])
        other = reverse('article-detail', args=[self.daily_article.pk])
        self.assertEqual(self.client.delete(own).status_code,
                         status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.delete(other).status_code,
                         status.HTTP_403_FORBIDDEN)


@mock.patch('news.services.requests.post')
class ApprovalTests(NewsAPITestCase):
    """Approval must email subscribers and POST to /api/approved/."""

    def approve_url(self, article):
        return reverse('article-approve', args=[article.pk])

    def test_editor_can_approve_article(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        self.reader.subscribed_publishers.add(self.daily)
        self.other_reader.subscribed_journalists.add(self.journalist)
        self.authenticate(self.editor)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.approve_url(self.pending_article)
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_article.refresh_from_db()
        self.assertTrue(self.pending_article.approved)
        self.assertEqual(self.pending_article.approved_by, self.editor)

        # One email, sent to both publisher and journalist subscribers.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            sorted(mail.outbox[0].bcc),
            ['other_reader@example.com', 'reader@example.com'],
        )
        self.assertIn('Pending story', mail.outbox[0].subject)

        # The article was sent to /api/approved/ with the editor token.
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['article'], self.pending_article.pk)
        editor_token = Token.objects.get(user=self.editor).key
        self.assertEqual(kwargs['headers']['Authorization'],
                         f'Token {editor_token}')

    def test_no_email_when_there_are_no_subscribers(self, mock_post):
        self.authenticate(self.editor)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.approve_url(self.pending_article))
        self.assertEqual(len(mail.outbox), 0)
        mock_post.assert_called_once()

    def test_non_editors_cannot_approve(self, mock_post):
        for user in (self.reader, self.journalist):
            self.authenticate(user)
            response = self.client.post(
                self.approve_url(self.pending_article)
            )
            self.assertEqual(response.status_code,
                             status.HTTP_403_FORBIDDEN)
        self.pending_article.refresh_from_db()
        self.assertFalse(self.pending_article.approved)
        mock_post.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    def test_approving_twice_fails(self, mock_post):
        self.authenticate(self.editor)
        response = self.client.post(self.approve_url(self.daily_article))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_post.assert_not_called()

    def test_api_failure_does_not_block_approval(self, mock_post):
        mock_post.side_effect = requests.ConnectionError('down')
        self.authenticate(self.editor)
        with self.assertLogs('news.services', level='ERROR'):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    self.approve_url(self.pending_article)
                )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_article.refresh_from_db()
        self.assertTrue(self.pending_article.approved)

    @override_settings(MAILERS={'default': {
        'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}})
    def test_web_approval_view_runs_same_logic(self, mock_post):
        self.reader.subscribed_publishers.add(self.daily)
        self.client.force_login(self.editor)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse('article_approve', args=[self.pending_article.pk])
            )
        self.assertRedirects(response, reverse('review_queue'))
        self.pending_article.refresh_from_db()
        self.assertTrue(self.pending_article.approved)
        self.assertEqual(len(mail.outbox), 1)
        mock_post.assert_called_once()


class ApprovedEndpointTests(NewsAPITestCase):
    """The internal /api/approved/ log endpoint is editor-only."""

    url = reverse('api-approved')

    def test_editor_can_log_approved_article(self):
        self.authenticate(self.editor)
        response = self.client.post(self.url, {
            'article': self.daily_article.pk, 'title': 'Daily story',
            'author_name': 'other_journalist', 'publisher_name': 'The Daily',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ApprovedArticleLog.objects.count(), 1)

    def test_non_editor_cannot_log_or_view(self):
        self.authenticate(self.journalist)
        self.assertEqual(
            self.client.post(self.url, {'article': self.daily_article.pk,
                                        'title': 'x'}).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.get(self.url).status_code,
                         status.HTTP_403_FORBIDDEN)


class NewsletterTests(NewsAPITestCase):
    """Newsletter viewing, creation and editing rules."""

    def setUp(self):
        super().setUp()
        self.newsletter = Newsletter.objects.create(
            title='Morning round-up', author=self.journalist,
        )
        self.newsletter.articles.add(self.daily_article)

    def test_reader_can_list_and_view_newsletters(self):
        self.authenticate(self.reader)
        response = self.client.get(reverse('newsletter-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        detail = self.client.get(
            reverse('newsletter-detail', args=[self.newsletter.pk])
        )
        self.assertEqual(detail.data['articles'], [self.daily_article.pk])

    def test_reader_cannot_create_newsletter(self):
        self.authenticate(self.reader)
        response = self.client.post(reverse('newsletter-list'), {
            'title': 'Mine',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_journalist_and_editor_can_create_newsletters(self):
        for user in (self.journalist, self.editor):
            self.authenticate(user)
            response = self.client.post(reverse('newsletter-list'), {
                'title': f'By {user.username}',
                'articles': [self.daily_article.pk, self.weekly_article.pk],
            }, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(response.data['author']['id'], user.pk)
            self.assertEqual(len(response.data['articles']), 2)

    def test_newsletter_cannot_include_unapproved_articles(self):
        self.authenticate(self.journalist)
        response = self.client.post(reverse('newsletter-list'), {
            'title': 'Leaky', 'articles': [self.pending_article.pk],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_author_or_editor_can_modify_newsletter(self):
        url = reverse('newsletter-detail', args=[self.newsletter.pk])
        self.authenticate(self.other_journalist)
        self.assertEqual(
            self.client.patch(url, {'title': 'Taken'},
                              format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.authenticate(self.journalist)
        self.assertEqual(
            self.client.patch(url, {'title': 'Renamed'},
                              format='json').status_code,
            status.HTTP_200_OK,
        )
        self.authenticate(self.editor)
        self.assertEqual(self.client.delete(url).status_code,
                         status.HTTP_204_NO_CONTENT)
        self.assertFalse(Newsletter.objects.exists())
