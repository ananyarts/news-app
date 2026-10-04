"""Forms for the web front end."""

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Article, CustomUser, Newsletter, Publisher, Role


class RegistrationForm(UserCreationForm):
    """Sign-up form that lets a user pick a role."""

    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=Role.choices, initial=Role.READER)

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email', 'role']

    def clean_email(self):
        """Normalise the email and reject one that is already in use."""
        email = self.cleaned_data['email'].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('That email is already registered.')
        return email


class ArticleForm(forms.ModelForm):
    """Create or edit an article.

    Leaving ``publisher`` empty makes the article independent. The
    signed-in journalist is set as the author of a new article *before*
    validation runs, because :meth:`Article.clean` needs an author or a
    publisher to be present.
    """

    class Meta:
        model = Article
        fields = ['title', 'publisher', 'content']
        widgets = {'content': forms.Textarea(attrs={'rows': 14})}
        help_texts = {
            'publisher': 'Leave empty to publish independently.',
        }

    def __init__(self, *args, user=None, **kwargs):
        """Limit publisher choices and attach the author.

        ``user`` is the person filling in the form. A journalist can only
        file under publishers they write for, and becomes the author of
        any new article.
        """
        super().__init__(*args, **kwargs)
        publisher_field = self.fields['publisher']
        publisher_field.required = False
        if user is not None and user.is_journalist:
            publisher_field.queryset = user.publishers.all()
            if self.instance.pk is None:
                # Assign the author now so model validation (clean())
                # accepts independent articles with no publisher.
                self.instance.author = user

    def clean_title(self):
        """Strip whitespace and reject a blank title."""
        title = self.cleaned_data['title'].strip()
        if not title:
            raise forms.ValidationError('Title cannot be blank.')
        return title


class NewsletterForm(forms.ModelForm):
    """Create or edit a newsletter from approved articles."""

    class Meta:
        model = Newsletter
        fields = ['title', 'description', 'articles']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'articles': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        """Only offer approved articles for inclusion."""
        super().__init__(*args, **kwargs)
        self.fields['articles'].queryset = Article.objects.filter(
            approved=True
        )

    def clean_title(self):
        """Strip whitespace and reject a blank title."""
        title = self.cleaned_data['title'].strip()
        if not title:
            raise forms.ValidationError('Title cannot be blank.')
        return title


class PublisherForm(forms.ModelForm):
    """Create or edit a publisher and choose its editors and journalists.

    The member lists only offer users with the matching role, so an
    editor can never be added as a journalist or the other way round.
    """

    class Meta:
        model = Publisher
        fields = ['name', 'description', 'editors', 'journalists']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'editors': forms.CheckboxSelectMultiple,
            'journalists': forms.CheckboxSelectMultiple,
        }
        help_texts = {
            'editors': 'Editors who review this publisher\'s articles.',
            'journalists': 'Journalists who can write for this publisher.',
        }

    def __init__(self, *args, **kwargs):
        """Restrict each member list to users with the right role."""
        super().__init__(*args, **kwargs)
        self.fields['editors'].queryset = CustomUser.objects.filter(
            role=Role.EDITOR
        ).order_by('username')
        self.fields['journalists'].queryset = CustomUser.objects.filter(
            role=Role.JOURNALIST
        ).order_by('username')

    def clean_name(self):
        """Strip whitespace and reject a blank name."""
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('Name cannot be blank.')
        return name
