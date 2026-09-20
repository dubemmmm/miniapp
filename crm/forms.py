import re
from django import forms


class EnquiryForm(forms.Form):
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            'placeholder': 'First name',
        })
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Last name',
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Your email address',
        })
    )
    phone = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Phone number (optional)',
        })
    )
    message = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            'rows': 4,
            'placeholder': 'Tell us about your interest in this property... (optional)',
        })
    )
    consent = forms.BooleanField(
        required=True,
        error_messages={'required': 'You must agree to be contacted to submit an enquiry.'},
        widget=forms.CheckboxInput(attrs={'class': 'mr-2'})
    )
    # Honeypot — must remain empty; bots fill it, humans don't see it
    website = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label='',
    )

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if phone:
            # Accept E.164 or common formats; strip non-digits for storage
            cleaned = re.sub(r'[\s\-\(\)]', '', phone)
            if not re.match(r'^\+?[0-9]{7,15}$', cleaned):
                raise forms.ValidationError('Enter a valid phone number.')
            return cleaned
        return phone

    def clean_website(self):
        """Honeypot validation — must be empty."""
        value = self.cleaned_data.get('website', '')
        if value:
            raise forms.ValidationError('Bot detected.')
        return value


BUDGET_CHOICES = [
    ('', 'Budget (optional)'),
    ('Under ₦500M', 'Under ₦500M'),
    ('₦500M to ₦1B', '₦500M to ₦1B'),
    ('₦1B to ₦3B', '₦1B to ₦3B'),
    ('Above ₦3B', 'Above ₦3B'),
]
BEDROOM_CHOICES = [('', 'Bedrooms (optional)'), ('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5+', '5 or more')]


class ShortlistForm(forms.Form):
    """Public form on a neighbourhood page: request a curated shortlist, or
    leave details to download that neighbourhood's guide."""
    intent = forms.ChoiceField(choices=[('shortlist', 'Curated shortlist'), ('guide', 'Guide download'), ('access', 'Private access')])
    # Required for shortlist and guide; optional (area of interest) for access requests.
    market = forms.CharField(required=False, max_length=80)
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    email = forms.EmailField()
    phone = forms.CharField(required=False, max_length=30)
    budget = forms.ChoiceField(required=False, choices=BUDGET_CHOICES)
    bedrooms = forms.ChoiceField(required=False, choices=BEDROOM_CHOICES)
    message = forms.CharField(required=False, max_length=2000)
    consent = forms.BooleanField(
        required=True,
        error_messages={'required': 'You must agree to be contacted to continue.'},
    )
    # Honeypot: bots fill it, humans never see it.
    website = forms.CharField(required=False)

    def clean_market(self):
        from properties.markets import market_from_slug
        slug = self.cleaned_data.get('market', '')
        if slug and market_from_slug(slug) is None:
            raise forms.ValidationError('Unknown neighbourhood.')
        return slug

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('intent') in ('shortlist', 'guide') and not cleaned.get('market'):
            self.add_error('market', 'Choose a neighbourhood.')
        return cleaned

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if phone:
            cleaned = re.sub(r'[\s\-\(\)]', '', phone)
            if not re.match(r'^\+?[0-9]{7,15}$', cleaned):
                raise forms.ValidationError('Enter a valid phone number.')
            return cleaned
        return phone
