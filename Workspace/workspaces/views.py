from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .models import Page


@login_required
def page_detail(request, pk):
    """Shows one page and its blocks. Only members of the page's workspace may see it."""
    page = get_object_or_404(
        Page.objects.select_related('workspace'),
        pk=pk,
        workspace__memberships__user=request.user,
    )
    return render(request, 'workspaces/page_detail.html', {
        'page': page,
        'blocks': page.blocks.all(),
        'title': page.title,
    })