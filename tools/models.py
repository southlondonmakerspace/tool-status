from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

DAYS_PER_MONTH = 30

# URL segment for tools that aren't in an area: /other/<tool-slug>
NO_AREA_SLUG = "other"

# First path segments an area must never take over.
RESERVED_AREA_SLUGS = {"admin", "static", NO_AREA_SLUG}


def unique_slug(name, queryset, fallback, reserved=()):
    """Slug made from name that isn't already used in queryset, such as
    "band-saw", or "band-saw-2" if that's taken."""
    base = slugify(name)[:45] or fallback
    if base in reserved:
        base = f"{base}-{fallback}"
    taken = set(queryset.filter(slug__startswith=base).values_list("slug", flat=True))
    slug, n = base, 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


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
    slug = models.SlugField(
        max_length=50, unique=True, editable=False, help_text="Used in URLs; made from the name."
    )
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

    def save(self, *args, **kwargs):
        # Made from the name on every save; saving without renaming keeps it.
        self.slug = unique_slug(
            self.name, Area.objects.exclude(pk=self.pk), "area", RESERVED_AREA_SLUGS
        )
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "slug"}
        super().save(*args, **kwargs)


class Tool(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(
        max_length=50, editable=False, help_text="Used in the tool's URL; made from the name. Unique within its area."
    )
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
        constraints = [
            models.UniqueConstraint(fields=["area", "slug"], name="unique_tool_slug_per_area"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Made from the name on every save, unique within the tool's area.
        # Saving without renaming or moving the tool keeps the same slug.
        siblings = Tool.objects.exclude(pk=self.pk).filter(area_id=self.area_id)
        self.slug = unique_slug(self.name, siblings, "tool")
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "slug"}
        super().save(*args, **kwargs)

    @property
    def area_slug(self):
        return self.area.slug if self.area_id else NO_AREA_SLUG

    @property
    def url_kwargs(self):
        return {"area_slug": self.area_slug, "tool_slug": self.slug}

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("tool page", kwargs=self.url_kwargs)

    def can_be_edited_by(self, user):
        """Superusers can edit any tool; other users only tools in their areas."""
        if user.is_superuser and user.is_active:
            return True
        return self.area_id is not None and Area.objects.editable_by(user).filter(pk=self.area_id).exists()

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

    STATUS_DISPLAY = {
        # status: (label, Bootstrap colour)
        "down": ("Not working", "danger"),
        "overdue": ("Maintenance due", "warning"),
        "ok": ("Working", "success"),
    }

    @property
    def status_label(self):
        return self.STATUS_DISPLAY[self.status][0]

    @property
    def status_color(self):
        return self.STATUS_DISPLAY[self.status][1]
