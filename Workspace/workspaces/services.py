from django.db import transaction

from .models import Membership, Workspace


@transaction.atomic
def create_workspace(user, name):
    """Creates a workspace and makes `user` its owner. Both happen, or neither does."""
    workspace = Workspace.objects.create(name=name)
    Membership.objects.create(workspace=workspace, user=user, role=Membership.Role.OWNER)
    return workspace
