from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import Membership, Page

EDIT_ROLES = (Membership.Role.OWNER, Membership.Role.EDITOR)


def membership_for_workspace(user, workspace_id):
    """The user's membership in a workspace. 404 if they are not a member."""
    return get_object_or_404(
        Membership.objects.select_related('workspace'),
        workspace_id=workspace_id,
        user=user,
    )


def get_page_and_membership(user, page_pk):
    """A page plus the user's membership in its workspace. 404 if either is missing."""
    page = get_object_or_404(Page.objects.select_related('workspace'), pk=page_pk)
    membership = get_object_or_404(Membership, workspace=page.workspace, user=user)
    return page, membership


def can_edit(membership):
    return membership.role in EDIT_ROLES


def require_editor(membership):
    """Raises 403 unless the member may change content."""
    if not can_edit(membership):
        raise PermissionDenied
