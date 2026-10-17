from django.contrib import admin
from .models import Workspace, Membership, Page, Block


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'page', 'kind', 'position')
    list_filter = ('page',)


admin.site.register([Workspace, Membership, Page])