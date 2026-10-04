"""Tests for the web front end: access control, article forms and
publisher management."""

from django.test import TestCase
from django.urls import reverse

from news.models import Article, CustomUser, Publisher, Role


class WebAccessTests(TestCase):
    """Role-based access to the main web pages."""

    def setUp(self):
        """Create one user per role, a publisher and a pending article."""
        self.reader = CustomUser.objects.create_user(
            'reader', password='S3cure-pass!', role=Role.READER)
        self.journalist = CustomUser.objects.create_user(
            'journalist', password='S3cure-pass!', role=Role.JOURNALIST)
        self.editor = CustomUser.objects.create_user(
            'editor', password='S3cure-pass!', role=Role.EDITOR)
        self.publisher = Publisher.objects.create(name='The Daily')
        self.article = Article.objects.create(
            title='Pending', content='...', author=self.journalist)

    def test_home_is_public_and_hides_pending_articles(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Pending')

    def test_review_queue_is_editor_only(self):
        url = reverse('review_queue')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.editor)
        self.assertContains(self.client.get(url), 'Pending')

    def test_only_journalists_can_open_article_form(self):
        url = reverse('article_create')
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.journalist)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_approve_requires_post(self):
        self.client.force_login(self.editor)
        url = reverse('article_approve', args=[self.article.pk])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_reader_can_subscribe_and_unsubscribe(self):
        self.client.force_login(self.reader)
        url = reverse('toggle_subscription',
                      args=['publisher', self.publisher.pk])
        self.client.post(url)
        self.assertTrue(self.reader.subscribed_publishers.exists())
        self.client.post(url)
        self.assertFalse(self.reader.subscribed_publishers.exists())

    def test_registration_assigns_role_group(self):
        response = self.client.post(reverse('register'), {
            'username': 'newbie', 'first_name': 'New', 'last_name': 'User',
            'email': 'newbie@example.com', 'role': Role.JOURNALIST,
            'password1': 'An0ther-secure!', 'password2': 'An0ther-secure!',
        })
        self.assertRedirects(response, reverse('home'))
        user = CustomUser.objects.get(username='newbie')
        self.assertTrue(user.groups.filter(name='Journalist').exists())


class ArticleFormTests(TestCase):
    """Journalists can submit independent and publisher articles."""

    def setUp(self):
        """Create a journalist who writes for one of two publishers."""
        self.journalist = CustomUser.objects.create_user(
            'journalist', password='S3cure-pass!', role=Role.JOURNALIST)
        self.publisher = Publisher.objects.create(name='The Daily')
        self.other_publisher = Publisher.objects.create(name='The Weekly')
        self.publisher.journalists.add(self.journalist)
        self.client.force_login(self.journalist)
        self.url = reverse('article_create')

    def test_journalist_can_create_independent_article(self):
        """Leaving publisher empty creates an independent article
        (regression: this used to fail model validation)."""
        response = self.client.post(self.url, {
            'title': 'Solo story', 'publisher': '', 'content': 'Body text',
        })
        article = Article.objects.get(title='Solo story')
        self.assertRedirects(
            response, reverse('article_detail', args=[article.pk]))
        self.assertEqual(article.author, self.journalist)
        self.assertIsNone(article.publisher)
        self.assertTrue(article.is_independent)
        self.assertFalse(article.approved)

    def test_journalist_can_create_publisher_article(self):
        """Choosing a publisher they write for files the article there."""
        self.client.post(self.url, {
            'title': 'Daily story', 'publisher': self.publisher.pk,
            'content': 'Body text',
        })
        article = Article.objects.get(title='Daily story')
        self.assertEqual(article.publisher, self.publisher)
        self.assertEqual(article.author, self.journalist)

    def test_journalist_cannot_use_publisher_they_do_not_write_for(self):
        """A publisher outside the journalist's list is rejected."""
        response = self.client.post(self.url, {
            'title': 'Sneaky', 'publisher': self.other_publisher.pk,
            'content': 'Body text',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Article.objects.filter(title='Sneaky').exists())

    def test_blank_title_is_rejected(self):
        """A whitespace-only title shows an error and saves nothing."""
        response = self.client.post(self.url, {
            'title': '   ', 'publisher': '', 'content': 'Body text',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Article.objects.count(), 0)


class PublisherManagementTests(TestCase):
    """Creating publishers and managing their editors and journalists."""

    def setUp(self):
        """Create users for every role plus a publisher run by
        ``self.editor``."""
        password = 'S3cure-pass!'
        self.reader = CustomUser.objects.create_user(
            'reader', password=password, role=Role.READER)
        self.journalist = CustomUser.objects.create_user(
            'journalist', password=password, role=Role.JOURNALIST)
        self.editor = CustomUser.objects.create_user(
            'editor', password=password, role=Role.EDITOR)
        self.other_editor = CustomUser.objects.create_user(
            'other_editor', password=password, role=Role.EDITOR)
        self.admin = CustomUser.objects.create_superuser(
            'admin', password=password, email='admin@example.com')
        self.publisher = Publisher.objects.create(name='The Daily')
        self.publisher.editors.add(self.editor)

    def test_editor_can_create_publisher_and_assign_staff(self):
        """The creating editor is added as an editor automatically."""
        self.client.force_login(self.other_editor)
        response = self.client.post(reverse('publisher_create'), {
            'name': 'The Weekly', 'description': 'Weekly news',
            'journalists': [self.journalist.pk],
        })
        publisher = Publisher.objects.get(name='The Weekly')
        self.assertRedirects(
            response, reverse('publisher_detail', args=[publisher.pk]))
        self.assertIn(self.other_editor, publisher.editors.all())
        self.assertIn(self.journalist, publisher.journalists.all())

    def test_readers_and_journalists_cannot_create_publishers(self):
        """Non-editors get 403; guests are sent to log in."""
        url = reverse('publisher_create')
        self.assertEqual(self.client.get(url).status_code, 302)
        for user in (self.reader, self.journalist):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.post(url, {'name': 'Nope'})
        self.assertFalse(Publisher.objects.filter(name='Nope').exists())

    def test_superuser_can_create_publisher(self):
        """Site administrators can create publishers too."""
        self.client.force_login(self.admin)
        self.client.post(reverse('publisher_create'), {'name': 'Admin Co'})
        self.assertTrue(Publisher.objects.filter(name='Admin Co').exists())

    def test_publisher_editor_can_add_and_remove_journalists(self):
        """An editor of the publisher can change its staff."""
        self.client.force_login(self.editor)
        url = reverse('publisher_update', args=[self.publisher.pk])
        self.client.post(url, {
            'name': 'The Daily', 'editors': [self.editor.pk],
            'journalists': [self.journalist.pk],
        })
        self.assertIn(self.journalist, self.publisher.journalists.all())
        self.client.post(url, {
            'name': 'The Daily', 'editors': [self.editor.pk],
        })
        self.assertEqual(self.publisher.journalists.count(), 0)

    def test_staff_lists_only_accept_matching_roles(self):
        """A journalist cannot be added as an editor (and vice versa)."""
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('publisher_update', args=[self.publisher.pk]),
            {'name': 'The Daily', 'editors': [self.journalist.pk],
             'journalists': [self.editor.pk]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.journalist, self.publisher.editors.all())

    def test_other_editors_cannot_manage_publisher(self):
        """Editors of a different publisher get 403."""
        self.client.force_login(self.other_editor)
        for name in ('publisher_update', 'publisher_delete'):
            url = reverse(name, args=[self.publisher.pk])
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_publisher_editor_can_delete_publisher(self):
        """Deleting keeps articles, which become independent."""
        article = Article.objects.create(
            title='Kept', content='...', author=self.journalist,
            publisher=self.publisher)
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('publisher_delete', args=[self.publisher.pk]))
        self.assertRedirects(response, reverse('publisher_list'))
        self.assertFalse(Publisher.objects.exists())
        article.refresh_from_db()
        self.assertIsNone(article.publisher)

    def test_new_publisher_journalist_can_then_file_under_it(self):
        """End to end: a journalist added on the management page can
        immediately choose that publisher when writing."""
        self.client.force_login(self.editor)
        self.client.post(
            reverse('publisher_update', args=[self.publisher.pk]),
            {'name': 'The Daily', 'editors': [self.editor.pk],
             'journalists': [self.journalist.pk]},
        )
        self.client.force_login(self.journalist)
        self.client.post(reverse('article_create'), {
            'title': 'First Daily piece', 'publisher': self.publisher.pk,
            'content': 'Body',
        })
        self.assertTrue(Article.objects.filter(
            title='First Daily piece', publisher=self.publisher).exists())
