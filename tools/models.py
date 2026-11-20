from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.utils import timezone

DAYS_PER_MONTH = 30


class AreaQuerySet(models.QuerySet):
    def editable_by(self, user):
        """Areas the user may edit tools in: all for superusers, otherwise
        those listing the user, or one of their groups, as an editor."""
        if not user.is_active:
            return self.none()
        if user.is_superuser:
            return self.all()
        return self.filter(
            models.Q(editors=user) | models.Q(editor_groups__in=user.groups.all())
        ).distinct()


class Area(models.Model):
    """A part of the space, such as the woodshop, that tools belong to."""

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.CharField(max_length=200, blank=True)
    editors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="editable_areas",
        help_text="Users who can add and edit tools in this area. They also need staff status to log in.",
    )
    editor_groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="editable_areas",
        help_text="Groups whose members can add and edit tools in this area.",
    )

    objects = AreaQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Tool(models.Model):
    name = models.CharField(max_length=50, primary_key=True)
    area = models.ForeignKey(
        Area, on_delete=models.PROTECT, null=True, blank=True, related_name="tools"
    )
    description = models.CharField(max_length=200, null=True, blank=True)
    functional = models.BooleanField()
    last_maintained = models.DateField(null=True, blank=True)
    maintenance_interval = models.IntegerField(
        null=True, blank=True, help_text="Months between maintenance"
    )
    latest_issue = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def next_due(self):
        """Date maintenance is next due, or None if it can't be worked out."""
        if self.last_maintained is None or self.maintenance_interval is None:
            return None
        return self.last_maintained + timedelta(days=self.maintenance_interval * DAYS_PER_MONTH)

    @property
    def days_remaining(self):
        """Days until maintenance is due; negative when overdue."""
        if self.next_due is None:
            return None
        return (self.next_due - timezone.localdate()).days

    @property
    def maintenance_overdue(self):
        return self.days_remaining is not None and self.days_remaining < 0

    @property
    def days_overdue(self):
        return -self.days_remaining if self.maintenance_overdue else 0

    @property
    def status(self):
        """One of "down", "overdue" or "ok"."""
        if not self.functional:
            return "down"
        if self.maintenance_overdue:
            return "overdue"
        return "ok"
