from django.db.models import OuterRef, Subquery

from .models import Membership, Page, Workspace


def _flatten(pages):
    """Pages in sidebar order: each page followed by its sub-pages, with depth and indent set."""
    children = {}
    for page in pages:
        children.setdefault(page.parent_id, []).append(page)
    ordered = []

    def walk(parent_id, depth):
        for page in sorted(children.get(parent_id, []), key=lambda p: p.title.lower()):
            page.depth = depth
            page.indent = 0.5 + 0.9 * (depth - 1)   # in rem
            ordered.append(page)
            walk(page.pk, depth + 1)

    walk(None, 1)
    return ordered


def sidebar(request):
    """Adds the signed-in user's workspaces, their role in each, and each workspace's page tree."""
    if not request.user.is_authenticated:
        return {}
    my_role = Membership.objects.filter(
        workspace=OuterRef('pk'), user=request.user
    ).values('role')[:1]
    workspaces = list(
        Workspace.objects.filter(memberships__user=request.user)
        .annotate(my_role=Subquery(my_role))
        .order_by('name')
    )
    pages_by_workspace = {}
    for page in Page.objects.filter(workspace__in=workspaces):
        pages_by_workspace.setdefault(page.workspace_id, []).append(page)
    for workspace in workspaces:
        workspace.sidebar_pages = _flatten(pages_by_workspace.get(workspace.pk, []))
        workspace.top_pages = [p for p in workspace.sidebar_pages if p.depth == 1]   # kept for older code
    return {'sidebar_workspaces': workspaces}