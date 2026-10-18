from django.db.models import Prefetch

from .models import Page, Workspace


def sidebar(request):
    """Adds the signed-in user's workspaces and their top-level pages to every template."""
    if not request.user.is_authenticated:
        return {}
    top_pages = Page.objects.filter(parent__isnull=True).order_by('title')
    workspaces = (
        Workspace.objects.filter(memberships__user=request.user)
        .prefetch_related(Prefetch('pages', queryset=top_pages, to_attr='top_pages'))
        .order_by('name')
    )
    return {'sidebar_workspaces': workspaces}
