"""Web views for the news application.

Every view that changes data checks the user's role (through
:func:`role_required`) and, where relevant, whether the user owns the
object (through the ``can_modify_*`` helpers).
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .api_views import visible_articles
from .forms import ArticleForm, NewsletterForm, PublisherForm, RegistrationForm
from .models import Article, CustomUser, Newsletter, Publisher, Role
from .services import approve_article

ARTICLES_PER_PAGE = 10


def role_required(*roles):
    """Decorator: allow only signed-in users whose role is in ``roles``.

    Anonymous users are redirected to the login page; signed-in users
    with another role get a 403 Forbidden response.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def can_modify_article(user, article):
    """Return True if ``user`` may edit or delete ``article``.

    Editors may change any article; journalists only their own.
    """
    return user.is_editor or (user.is_journalist
                              and article.author_id == user.pk)


def can_modify_newsletter(user, newsletter):
    """Return True if ``user`` may edit or delete ``newsletter``.

    Editors may change any newsletter; journalists only their own.
    """
    return user.is_editor or (user.is_journalist
                              and newsletter.author_id == user.pk)


def can_create_publisher(user):
    """Return True if ``user`` may create publishers.

    Any editor, or a site administrator (superuser), may do so.
    """
    return user.is_authenticated and (user.is_superuser or user.is_editor)


def can_manage_publisher(user, publisher):
    """Return True if ``user`` may edit or delete ``publisher``.

    Superusers may manage every publisher. Editors may manage the
    publishers they are an editor of.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (user.is_editor
            and publisher.editors.filter(pk=user.pk).exists())


# Accounts

def register(request):
    """Show the sign-up form and log the new user in on success.

    The chosen role puts the user in the matching group (see
    :meth:`CustomUser.save`).
    """
    if request.user.is_authenticated:
        return redirect('home')
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f'Welcome, {user.username}!')
        return redirect('home')
    return render(request, 'registration/register.html', {'form': form})


# Articles

def home(request):
    """List approved articles, newest first, with optional search.

    ``?q=`` filters by title or content; ``?page=`` paginates.
    """
    articles = Article.objects.filter(approved=True).select_related(
        'author', 'publisher'
    )
    query = request.GET.get('q', '').strip()
    if query:
        articles = articles.filter(
            Q(title__icontains=query) | Q(content__icontains=query)
        )
    page = Paginator(articles, ARTICLES_PER_PAGE).get_page(
        request.GET.get('page')
    )
    return render(request, 'news/home.html',
                  {'page': page, 'query': query})


def article_detail(request, pk):
    """Show one article.

    Guests and readers see only approved articles. Journalists may also
    see their own pending articles, and editors may see every article.
    """
    if request.user.is_authenticated:
        queryset = visible_articles(request.user)
    else:
        queryset = Article.objects.filter(approved=True)
    article = get_object_or_404(queryset, pk=pk)
    can_edit = (request.user.is_authenticated
                and can_modify_article(request.user, article))
    return render(request, 'news/article_detail.html',
                  {'article': article, 'can_edit': can_edit})


@role_required(Role.JOURNALIST)
def article_create(request):
    """Let a journalist write a new article (journalists only).

    The article is saved unapproved and goes to the editors' review
    queue. With no publisher selected it is an independent article; the
    form sets the journalist as author before validation so this works.
    """
    form = ArticleForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        article = form.save(commit=False)
        article.author = request.user
        article.approved = False
        article.save()
        messages.success(request, 'Article submitted for editor review.')
        return redirect('article_detail', pk=article.pk)
    return render(request, 'news/form.html',
                  {'form': form, 'heading': 'Write an article'})


@role_required(Role.JOURNALIST, Role.EDITOR)
def article_update(request, pk):
    """Edit an article (its author, or any editor)."""
    article = get_object_or_404(Article, pk=pk)
    if not can_modify_article(request.user, article):
        raise PermissionDenied
    form = ArticleForm(request.POST or None, instance=article,
                       user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Article updated.')
        return redirect('article_detail', pk=article.pk)
    return render(request, 'news/form.html',
                  {'form': form, 'heading': f'Edit "{article.title}"'})


@role_required(Role.JOURNALIST, Role.EDITOR)
def article_delete(request, pk):
    """Confirm (GET) and delete (POST) an article (its author or an
    editor)."""
    article = get_object_or_404(Article, pk=pk)
    if not can_modify_article(request.user, article):
        raise PermissionDenied
    if request.method == 'POST':
        article.delete()
        messages.success(request, 'Article deleted.')
        return redirect('home')
    return render(request, 'news/confirm_delete.html', {'object': article})


@role_required(Role.JOURNALIST)
def my_articles(request):
    """List the signed-in journalist's articles, including pending ones."""
    articles = request.user.articles.select_related('publisher')
    return render(request, 'news/my_articles.html', {'articles': articles})


# Editor review

@role_required(Role.EDITOR)
def review_queue(request):
    """List every article still waiting for approval (editors only)."""
    pending = Article.objects.filter(approved=False).select_related(
        'author', 'publisher'
    )
    return render(request, 'news/review_queue.html', {'articles': pending})


@require_POST
@role_required(Role.EDITOR)
def article_approve(request, pk):
    """Approve an article (editors only, POST only).

    Delegates to :func:`news.services.approve_article`, which emails
    subscribers and POSTs the article to ``/api/approved/``.
    """
    article = get_object_or_404(Article, pk=pk)
    try:
        approve_article(article, request.user)
    except ValueError as error:
        messages.warning(request, str(error))
    else:
        messages.success(
            request, f'"{article.title}" approved and sent to subscribers.'
        )
    return redirect('review_queue')


# Newsletters

def newsletter_list(request):
    """List all newsletters (public)."""
    newsletters = Newsletter.objects.select_related('author')
    return render(request, 'news/newsletter_list.html',
                  {'newsletters': newsletters})


def newsletter_detail(request, pk):
    """Show a newsletter and its approved articles (public)."""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    articles = newsletter.articles.filter(approved=True).select_related(
        'author', 'publisher'
    )
    can_edit = (request.user.is_authenticated
                and can_modify_newsletter(request.user, newsletter))
    return render(request, 'news/newsletter_detail.html', {
        'newsletter': newsletter, 'articles': articles, 'can_edit': can_edit,
    })


@role_required(Role.JOURNALIST, Role.EDITOR)
def newsletter_create(request):
    """Create a newsletter (journalists and editors). The signed-in user
    becomes its author."""
    form = NewsletterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        newsletter = form.save(commit=False)
        newsletter.author = request.user
        newsletter.save()
        form.save_m2m()
        messages.success(request, 'Newsletter created.')
        return redirect('newsletter_detail', pk=newsletter.pk)
    return render(request, 'news/form.html',
                  {'form': form, 'heading': 'Create a newsletter'})


@role_required(Role.JOURNALIST, Role.EDITOR)
def newsletter_update(request, pk):
    """Edit a newsletter (its author, or any editor)."""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    if not can_modify_newsletter(request.user, newsletter):
        raise PermissionDenied
    form = NewsletterForm(request.POST or None, instance=newsletter)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Newsletter updated.')
        return redirect('newsletter_detail', pk=newsletter.pk)
    return render(request, 'news/form.html',
                  {'form': form, 'heading': f'Edit "{newsletter.title}"'})


@role_required(Role.JOURNALIST, Role.EDITOR)
def newsletter_delete(request, pk):
    """Confirm (GET) and delete (POST) a newsletter (its author or an
    editor)."""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    if not can_modify_newsletter(request.user, newsletter):
        raise PermissionDenied
    if request.method == 'POST':
        newsletter.delete()
        messages.success(request, 'Newsletter deleted.')
        return redirect('newsletter_list')
    return render(request, 'news/confirm_delete.html',
                  {'object': newsletter})


# Publishers

def publisher_list(request):
    """List all publishers (public). Editors also see a "New publisher"
    button."""
    publishers = Publisher.objects.prefetch_related('journalists')
    return render(request, 'news/publisher_list.html', {
        'publishers': publishers,
        'can_create': can_create_publisher(request.user),
    })


def publisher_detail(request, pk):
    """Show a publisher with its staff and approved articles.

    Readers get a Subscribe button; the publisher's editors get Manage
    and Delete buttons.
    """
    publisher = get_object_or_404(Publisher, pk=pk)
    articles = publisher.articles.filter(approved=True).select_related(
        'author'
    )
    subscribed = (request.user.is_authenticated and request.user.is_reader
                  and request.user.subscribed_publishers.filter(
                      pk=publisher.pk).exists())
    return render(request, 'news/publisher_detail.html', {
        'publisher': publisher, 'articles': articles,
        'subscribed': subscribed,
        'can_manage': can_manage_publisher(request.user, publisher),
    })


@login_required
def publisher_create(request):
    """Create a publisher and pick its editors and journalists.

    Open to editors and superusers. An editor who creates a publisher is
    always added to its editors so they can manage it afterwards.
    """
    if not can_create_publisher(request.user):
        raise PermissionDenied
    form = PublisherForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        publisher = form.save()
        if request.user.is_editor:
            publisher.editors.add(request.user)
        messages.success(request, f'Publisher "{publisher.name}" created.')
        return redirect('publisher_detail', pk=publisher.pk)
    return render(request, 'news/form.html',
                  {'form': form, 'heading': 'New publisher'})


@login_required
def publisher_update(request, pk):
    """Edit a publisher's details and its editors and journalists.

    Open to the publisher's own editors and to superusers.
    """
    publisher = get_object_or_404(Publisher, pk=pk)
    if not can_manage_publisher(request.user, publisher):
        raise PermissionDenied
    form = PublisherForm(request.POST or None, instance=publisher)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Publisher updated.')
        return redirect('publisher_detail', pk=publisher.pk)
    return render(request, 'news/form.html',
                  {'form': form, 'heading': f'Manage "{publisher.name}"'})


@login_required
def publisher_delete(request, pk):
    """Confirm (GET) and delete (POST) a publisher.

    Open to the publisher's own editors and to superusers. Its articles
    are kept and become independent (``on_delete=SET_NULL``).
    """
    publisher = get_object_or_404(Publisher, pk=pk)
    if not can_manage_publisher(request.user, publisher):
        raise PermissionDenied
    if request.method == 'POST':
        publisher.delete()
        messages.success(request, 'Publisher deleted.')
        return redirect('publisher_list')
    return render(request, 'news/confirm_delete.html', {'object': publisher})


# Journalists and subscriptions

def journalist_detail(request, pk):
    """Show a journalist's profile and approved articles, with a
    Subscribe button for readers."""
    journalist = get_object_or_404(CustomUser, pk=pk, role=Role.JOURNALIST)
    articles = journalist.articles.filter(approved=True).select_related(
        'publisher'
    )
    subscribed = (request.user.is_authenticated and request.user.is_reader
                  and request.user.subscribed_journalists.filter(
                      pk=journalist.pk).exists())
    return render(request, 'news/journalist_detail.html', {
        'journalist': journalist, 'articles': articles,
        'subscribed': subscribed,
    })


@require_POST
@role_required(Role.READER)
def toggle_subscription(request, kind, pk):
    """Subscribe to, or unsubscribe from, a publisher or journalist.

    ``kind`` is ``'publisher'`` or ``'journalist'``. Readers only.
    """
    if kind == 'publisher':
        target = get_object_or_404(Publisher, pk=pk)
        subscriptions = request.user.subscribed_publishers
        redirect_to = ('publisher_detail', pk)
    elif kind == 'journalist':
        target = get_object_or_404(CustomUser, pk=pk, role=Role.JOURNALIST)
        subscriptions = request.user.subscribed_journalists
        redirect_to = ('journalist_detail', pk)
    else:
        raise PermissionDenied

    if subscriptions.filter(pk=target.pk).exists():
        subscriptions.remove(target)
        messages.info(request, 'Unsubscribed.')
    else:
        subscriptions.add(target)
        messages.success(request, 'Subscribed! New articles will be emailed '
                                  'to you.')
    return redirect(*redirect_to)


@role_required(Role.READER)
def my_subscriptions(request):
    """Show a reader's subscriptions and the approved articles from
    them."""
    user = request.user
    publishers = user.subscribed_publishers.all()
    journalists = user.subscribed_journalists.all()
    articles = Article.objects.filter(
        Q(publisher__in=publishers) | Q(author__in=journalists),
        approved=True,
    ).select_related('author', 'publisher').distinct()
    return render(request, 'news/my_subscriptions.html', {
        'publishers': publishers, 'journalists': journalists,
        'articles': articles,
    })
