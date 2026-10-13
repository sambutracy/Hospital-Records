from django.contrib.auth.backends import BaseBackend
from .models import User


class OIDCSessionBackend(BaseBackend):
    """Restore authenticated sessions; never authenticate a local password."""
    def get_user(self, user_id):
        return User.objects.select_related('person').filter(
            pk=user_id, is_active=True, person__status='active',
        ).first()
