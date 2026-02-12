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
