"""DRF serializers for the news API."""

from rest_framework import serializers

from .models import (
    ApprovedArticleLog, Article, CustomUser, Newsletter, Publisher,
)


class UserSerializer(serializers.ModelSerializer):
    """Read-only public view of a user (no email or password)."""

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'first_name', 'last_name', 'role']
        read_only_fields = fields


class PublisherSerializer(serializers.ModelSerializer):
    """A publisher with its editors and journalists nested."""

    editors = UserSerializer(many=True, read_only=True)
    journalists = UserSerializer(many=True, read_only=True)

    class Meta:
        model = Publisher
        fields = ['id', 'name', 'description', 'editors', 'journalists']


class ArticleSerializer(serializers.ModelSerializer):
    """An article. ``author`` and approval fields are read-only: the
    author is the caller and approval has its own endpoint."""

    author = UserSerializer(read_only=True)
    publisher = serializers.PrimaryKeyRelatedField(
        queryset=Publisher.objects.all(), allow_null=True, required=False
    )
    publisher_name = serializers.CharField(
        source='publisher.name', read_only=True, default=None
    )

    class Meta:
        model = Article
        fields = [
            'id', 'title', 'content', 'author', 'publisher',
            'publisher_name', 'approved', 'approved_at', 'created_at',
            'updated_at',
        ]
        # Approval only happens through the dedicated approve action.
        read_only_fields = ['approved', 'approved_at', 'created_at',
                            'updated_at']

    def validate_title(self, value):
        """Strip whitespace and reject a blank title."""
        if not value.strip():
            raise serializers.ValidationError('Title cannot be blank.')
        return value.strip()

    def validate_publisher(self, publisher):
        """Journalists may only file under publishers they belong to."""
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if (publisher and user and user.is_journalist
                and not publisher.journalists.filter(pk=user.pk).exists()):
            raise serializers.ValidationError(
                'You are not a journalist for this publisher.'
            )
        return publisher


class NewsletterSerializer(serializers.ModelSerializer):
    """A newsletter; ``articles`` may only list approved articles."""

    author = UserSerializer(read_only=True)
    articles = serializers.PrimaryKeyRelatedField(
        queryset=Article.objects.filter(approved=True),
        many=True,
        required=False,
    )

    class Meta:
        model = Newsletter
        fields = ['id', 'title', 'description', 'author', 'articles',
                  'created_at']
        read_only_fields = ['created_at']

    def validate_title(self, value):
        """Strip whitespace and reject a blank title."""
        if not value.strip():
            raise serializers.ValidationError('Title cannot be blank.')
        return value.strip()


class ApprovedArticleLogSerializer(serializers.ModelSerializer):
    """A record posted to ``/api/approved/`` when an article is
    approved."""

    class Meta:
        model = ApprovedArticleLog
        fields = ['id', 'article', 'title', 'author_name', 'publisher_name',
                  'received_at']
        read_only_fields = ['received_at']
