from django.conf import settings
from django.db import models


class Workspace(models.Model):
    """A shared space that has members and pages."""
    name = models.CharField(max_length=100)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='Membership', related_name='workspaces'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    """Links a user to a workspace and says what they may do there."""

    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        EDITOR = 'editor', 'Editor'
        VIEWER = 'viewer', 'Viewer'

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.EDITOR)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'user'], name='one_membership_per_user_per_workspace'
            ),
        ]

    def __str__(self):
        return f'{self.user} in {self.workspace} ({self.role})'


class Page(models.Model):
    """A document. A page can sit inside another page."""
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='pages')
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE, related_name='children'
    )
    title = models.CharField(max_length=200, default='Untitled')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Block(models.Model):
    """One paragraph, heading or to-do on a page."""

    class Kind(models.TextChoices):
        PARAGRAPH = 'paragraph', 'Paragraph'
        HEADING = 'heading', 'Heading'
        TODO = 'todo', 'To-do'

    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='blocks')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PARAGRAPH)
    text = models.TextField(blank=True)
    checked = models.BooleanField(default=False)  # only used by to-do blocks
    position = models.FloatField(db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position']

    def __str__(self):
        return f'{self.kind}: {self.text[:30]}'
