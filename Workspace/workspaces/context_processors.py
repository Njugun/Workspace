from django.db.models import OuterRef, Prefetch, Subquery

from .models import Membership, Page, Workspace


def sidebar(request):
    """Adds the signed-in user's workspaces, their role in each, and top-level pages."""
    if not request.user.is_authenticated:
        return {}
    top_pages = Page.objects.filter(parent__isnull=True).order_by('title')
    my_role = Membership.objects.filter(
        workspace=OuterRef('pk'), user=request.user
    ).values('role')[:1]
    workspaces = (
        Workspace.objects.filter(memberships__user=request.user)
        .annotate(my_role=Subquery(my_role))
        .prefetch_related(Prefetch('pages', queryset=top_pages, to_attr='top_pages'))
        .order_by('name')
    )
    return {'sidebar_workspaces': workspaces}