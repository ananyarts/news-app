"""Create demo users, publishers and articles for trying the app."""

from django.core.management.base import BaseCommand

from news.models import Article, CustomUser, Newsletter, Publisher, Role

DEMO_PASSWORD = 'NewsDemo123!'


class Command(BaseCommand):
    """``python manage.py seed_demo``: optional sample data only.

    Publishers can be created without this command, on the Publishers
    page or in the Django admin (see README.md).
    """

    help = f'Seed demo data. Every demo user has password {DEMO_PASSWORD}'

    def handle(self, *args, **options):
        """Create the demo users, publisher, articles and newsletter."""
        reader = self.user('reader', Role.READER, 'Riya', 'Reader')
        journalist = self.user('journalist', Role.JOURNALIST, 'Jai', 'Writer')
        editor = self.user('editor', Role.EDITOR, 'Eve', 'Editor')

        publisher, _ = Publisher.objects.get_or_create(
            name='The Daily Brief',
            defaults={'description': 'Concise daily news.'},
        )
        publisher.journalists.add(journalist)
        publisher.editors.add(editor)
        reader.subscribed_publishers.add(publisher)

        published, _ = Article.objects.get_or_create(
            title='City council approves new cycle lanes',
            defaults={'content': 'The council voted 9-2 in favour...',
                      'author': journalist, 'publisher': publisher,
                      'approved': True, 'approved_by': editor},
        )
        Article.objects.get_or_create(
            title='Independent: a week on the night shift',
            defaults={'content': 'What happens after midnight...',
                      'author': journalist},
        )
        newsletter, _ = Newsletter.objects.get_or_create(
            title='Weekend round-up',
            defaults={'description': 'The best of the week.',
                      'author': journalist},
        )
        newsletter.articles.add(published)
        self.stdout.write(self.style.SUCCESS(
            'Demo data ready. Log in as reader / journalist / editor with '
            f'password {DEMO_PASSWORD}'
        ))

    @staticmethod
    def user(username, role, first_name, last_name):
        """Get or create a demo user with the shared demo password."""
        user, created = CustomUser.objects.get_or_create(
            username=username,
            defaults={'role': role, 'first_name': first_name,
                      'last_name': last_name,
                      'email': f'{username}@example.com'},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        return user
