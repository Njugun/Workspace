"""
Definition of models.
"""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Our own user model. Owning this class lets us add fields later."""
    pass