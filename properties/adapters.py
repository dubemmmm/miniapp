from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from .models import UserProfile


class CustomAccountAdapter(DefaultAccountAdapter):
    """Custom adapter for regular account signup"""

    def get_login_redirect_url(self, request):
        """
        Redirect all users to temp page after login
        """
        return '/default'  # All users go to temp page

    def add_message(self, request, level, message_template, message_context=None, extra_tags=''):
        """
        Suppress certain allauth messages to prevent stale message display
        """
        # Suppress login/logout success messages
        if 'signed in as' in message_template.lower() or 'signed out' in message_template.lower():
            return
        # Call parent for other messages
        super().add_message(request, level, message_template, message_context, extra_tags)


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom adapter for social account signup (Google OAuth)"""

    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after a user successfully authenticates via a social provider,
        but before the login is actually processed.
        """
        # Check if user is signing up (not connecting to existing account)
        if sociallogin.is_existing:
            return

        # Check if this email already exists
        if 'email' in sociallogin.account.extra_data:
            email = sociallogin.account.extra_data['email']
            try:
                from django.contrib.auth.models import User
                user = User.objects.get(email=email)
                # Connect the social account to existing user
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass

    def save_user(self, request, sociallogin, form=None):
        """
        Saves a newly signed up social login user.
        We'll determine if they're an employee or external user based on the signup URL.
        """
        user = super().save_user(request, sociallogin, form)

        # Check the path to determine user type
        # Store this info in session during the OAuth flow
        is_employee_signup = request.session.get('is_employee_signup', False)

        # Create or update user profile
        profile, created = UserProfile.objects.get_or_create(user=user)

        if is_employee_signup:
            # Employee signup
            profile.is_employee = True
            profile.can_share_properties = True
            # Note: Role will need to be set by admin or through a post-signup form
            profile.role = 'agent'  # Default role, can be changed later
        else:
            # External user signup
            profile.is_employee = False
            profile.can_share_properties = False
            profile.role = None

        profile.save()

        return user

    def get_login_redirect_url(self, request):
        """
        Redirect all users to temp page after social login
        """
        return '/default'  # All users go to temp page

    def get_signup_redirect_url(self, request):
        """
        Redirect all users to temp page after signup
        """
        return '/default'  # All users go to temp page

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Return whether automatic signup is allowed for this social account.
        """
        return True

    def add_message(self, request, level, message_template, message_context=None, extra_tags=''):
        """
        Suppress certain allauth messages to prevent stale message display
        """
        # Suppress login/logout success messages
        if 'signed in as' in message_template.lower() or 'signed out' in message_template.lower():
            return
        # Call parent for other messages
        super().add_message(request, level, message_template, message_context, extra_tags)
