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
        return '/'  # All users go to temp page

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
        import logging
        from django.shortcuts import redirect
        from django.contrib import messages
        from allauth.exceptions import ImmediateHttpResponse

        logger = logging.getLogger(__name__)

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
                return
            except User.DoesNotExist:
                # New user - check if they have invitation code
                is_employee_signup = request.session.get('is_employee_signup', False)

                if not is_employee_signup:
                    # Check for invitation code
                    invitation_code = request.session.get('pending_invitation_code')

                    if not invitation_code:
                        # Block the signup - redirect to registration page with error
                        logger.warning(f"Blocked Google signup attempt without invitation code for email: {email}")
                        messages.error(
                            request,
                            'This email address is not registered. New client accounts require an invitation code. Please use the registration page to sign up.'
                        )
                        # Raise ImmediateHttpResponse to interrupt the OAuth flow
                        raise ImmediateHttpResponse(redirect('register'))

    def save_user(self, request, sociallogin, form=None):
        """
        Saves a newly signed up social login user.
        We'll determine if they're an employee or external user based on the signup URL.
        """
        from .models import ClientInvitation
        import logging
        logger = logging.getLogger(__name__)

        # Check the path to determine user type
        # Store this info in session during the OAuth flow
        is_employee_signup = request.session.get('is_employee_signup', False)

        # For NEW external user signups (not employee signups), validate invitation code
        # Note: save_user is only called for NEW users, not existing users logging in
        if not is_employee_signup:
            invitation_code = request.session.get('pending_invitation_code')

            # Debug logging
            logger.info(f"OAuth NEW user signup - is_employee_signup: {is_employee_signup}")
            logger.info(f"Session keys: {list(request.session.keys())}")
            logger.info(f"Pending invitation code from session: {invitation_code}")

            if not invitation_code:
                # No invitation code provided - block NEW client signup
                # This means they tried to sign up via the login page instead of registration page
                logger.error("No invitation code found in session during OAuth NEW user signup")
                from django.contrib import messages
                messages.error(request, 'New client registration requires an invitation code. Please use the registration page.')
                raise Exception("Invitation code is required for new client registration. Please use the registration page with an invitation code.")

            try:
                invitation = ClientInvitation.objects.get(code=invitation_code)
            except ClientInvitation.DoesNotExist:
                raise Exception("Invalid invitation code")

            if not invitation.is_valid():
                raise Exception("This invitation code has expired or has been fully used")

        # Save the user
        user = super().save_user(request, sociallogin, form)

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

            # Mark invitation as used
            invitation_code = request.session.get('pending_invitation_code')
            if invitation_code:
                try:
                    invitation = ClientInvitation.objects.get(code=invitation_code)
                    invitation.mark_as_used(user)
                    logger.info(f"Invitation code {invitation_code} used by {user.username} via Google OAuth")
                    # Clear the pending invitation code from session
                    del request.session['pending_invitation_code']
                except ClientInvitation.DoesNotExist:
                    pass

        profile.save()

        return user

    def get_login_redirect_url(self, request):
        """
        Redirect all users to temp page after social login
        """
        return '/'  # All users go to temp page

    def get_signup_redirect_url(self, request):
        """
        Redirect all users to temp page after signup
        """
        return '/'  # All users go to temp page

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Return whether automatic signup is allowed for this social account.
        Block auto-signup for new clients who don't have an invitation code.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Check if this is an employee signup
        is_employee_signup = request.session.get('is_employee_signup', False)

        if is_employee_signup:
            # Allow employee auto-signup
            return True

        # For client signups, check if there's an invitation code in session
        invitation_code = request.session.get('pending_invitation_code')

        if invitation_code:
            # Invitation code present, allow auto-signup
            logger.info(f"Auto-signup allowed with invitation code: {invitation_code}")
            return True

        # No invitation code - block auto-signup for new clients
        # This will prevent the user from being created and show them an error
        logger.warning("Auto-signup blocked: No invitation code found for new client")
        from django.contrib import messages
        messages.error(
            request,
            'This email address is not registered. Please use the registration page with an invitation code to create an account.'
        )
        return False

    def add_message(self, request, level, message_template, message_context=None, extra_tags=''):
        """
        Suppress certain allauth messages to prevent stale message display
        """
        # Suppress login/logout success messages
        if 'signed in as' in message_template.lower() or 'signed out' in message_template.lower():
            return
        # Call parent for other messages
        super().add_message(request, level, message_template, message_context, extra_tags)
