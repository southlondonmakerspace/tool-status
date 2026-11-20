from datetime import timedelta

from django.db import models
from django.utils import timezone

DAYS_PER_MONTH = 30


class Tool(models.Model):
    name = models.CharField(max_length=50, primary_key=True)
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
    def status(self):
        """One of "down", "overdue" or "ok"."""
        if not self.functional:
            return "down"
        if self.maintenance_overdue:
            return "overdue"
        return "ok"
