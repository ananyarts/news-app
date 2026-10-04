"""REST API views.

Access is enforced by the permission classes in :mod:`news.permissions`;
every endpoint requires token (or session) authentication.
"""

from django.db.models import Q
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ApprovedArticleLog, Article, Newsletter, Publisher
from .permissions import (
    ArticlePermission, IsEditor, IsReader, NewsletterPermission,
)
from .serializers import (
    ApprovedArticleLogSerializer, ArticleSerializer, NewsletterSerializer,
    PublisherSerializer,
)
from .services import approve_article


def visible_articles(user):
    """Return the articles ``user`` may see.

    Everyone sees approved articles. Editors also see all pending ones,
    and journalists see their own pending ones.
    """
    articles = Article.objects.select_related('author', 'publisher')
    if user.is_editor:
        return articles
    if user.is_journalist:
        return articles.filter(Q(approved=True) | Q(author=user))
    return articles.filter(approved=True)


class ArticleViewSet(viewsets.ModelViewSet):
    """CRUD for articles plus ``subscribed`` and ``approve`` actions."""

    serializer_class = ArticleSerializer
    permission_classes = [ArticlePermission]
    http_method_names = ['get', 'post', 'put', 'patch', 'delete']

    def get_queryset(self):
        """Limit articles to those the caller may see."""
        return visible_articles(self.request.user)

    def list(self, request, *args, **kwargs):
        """GET /api/articles/ - all approved articles."""
        articles = self.get_queryset().filter(approved=True)
        serializer = self.get_serializer(articles, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Save a new article as unapproved, authored by the caller."""
        serializer.save(author=self.request.user, approved=False)

    @action(detail=False, methods=['get'], permission_classes=[IsReader])
    def subscribed(self, request):
        """GET /api/articles/subscribed/ - approved articles from the
        reader's subscribed publishers and journalists."""
        user = request.user
        articles = Article.objects.filter(
            Q(publisher__in=user.subscribed_publishers.all())
            | Q(author__in=user.subscribed_journalists.all()),
            approved=True,
        ).select_related('author', 'publisher').distinct()
        serializer = self.get_serializer(articles, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsEditor])
    def approve(self, request, pk=None):
        """POST /api/articles/<id>/approve/ - editors only."""
        article = self.get_object()
        try:
            approve_article(article, request.user)
        except ValueError as error:
            return Response({'detail': str(error)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(article).data)


class NewsletterViewSet(viewsets.ModelViewSet):
    """CRUD for newsletters: everyone reads, journalists and editors
    write."""

    queryset = Newsletter.objects.select_related('author').prefetch_related(
        'articles'
    )
    serializer_class = NewsletterSerializer
    permission_classes = [NewsletterPermission]
    http_method_names = ['get', 'post', 'put', 'patch', 'delete']

    def perform_create(self, serializer):
        """Save a new newsletter with the caller as its author."""
        serializer.save(author=self.request.user)


class PublisherViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list and detail of publishers and their staff."""

    queryset = Publisher.objects.prefetch_related('editors', 'journalists')
    serializer_class = PublisherSerializer


class ApprovedArticleLogView(generics.ListCreateAPIView):
    """GET/POST /api/approved/: approved-article log (editors only).

    The approval flow POSTs here to simulate sharing the article with an
    external service.
    """

    queryset = ApprovedArticleLog.objects.all()
    serializer_class = ApprovedArticleLogSerializer
    permission_classes = [IsEditor]
