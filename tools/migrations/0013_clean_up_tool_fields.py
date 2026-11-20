import django.core.validators
from django.db import migrations, models


def tidy_values(apps, schema_editor):
    Tool = apps.get_model("tools", "Tool")
    Tool.objects.filter(description__isnull=True).update(description="")
    Tool.objects.filter(latest_issue__isnull=True).update(latest_issue="")
    # An interval below one month means no schedule.
    Tool.objects.filter(maintenance_interval__lt=1).update(maintenance_interval=None)


class Migration(migrations.Migration):

    dependencies = [
        ("tools", "0012_tool_id_primary_key"),
    ]

    operations = [
        migrations.RunPython(tidy_values, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tool",
            name="description",
            field=models.CharField(blank=True, default="", max_length=200),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="tool",
            name="functional",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="tool",
            name="latest_issue",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="tool",
            name="maintenance_interval",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Months between maintenance. Leave blank if it has no schedule.",
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
    ]
