"""URL routes for the REST API (mounted under /api/)."""

from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import api_views

router = DefaultRouter()
router.register('articles', api_views.ArticleViewSet, basename='article')
router.register('newsletters', api_views.NewsletterViewSet,
                basename='newsletter')
router.register('publishers', api_views.PublisherViewSet,
                basename='publisher')

urlpatterns = [
    path('token/', obtain_auth_token, name='api-token'),
    path('approved/', api_views.ApprovedArticleLogView.as_view(),
         name='api-approved'),
    path('', include(router.urls)),
]
