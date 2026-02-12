from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class CRMAccessMixin(LoginRequiredMixin):
    """Allows access to Administrator and Real Estate Agent roles only."""

    def dispatch(self, request, *args, **kwargs):
        # LoginRequiredMixin redirects unauthenticated users before we get here
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in ('admin', 'agent'):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AdminOnlyMixin(LoginRequiredMixin):
    """Restricts access to Administrator role only."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role != 'admin':
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
