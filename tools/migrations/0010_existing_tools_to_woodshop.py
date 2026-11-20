from django.db import migrations


def existing_tools_to_woodshop(apps, schema_editor):
    """Every tool so far is a woodshop tool, so put them in a Woodshop area.
    Does nothing on a fresh database."""
    Area = apps.get_model("tools", "Area")
    Tool = apps.get_model("tools", "Tool")
    unassigned = Tool.objects.filter(area__isnull=True)
    if not unassigned.exists():
        return
    woodshop, _ = Area.objects.get_or_create(slug="woodshop", defaults={"name": "Woodshop"})
    unassigned.update(area=woodshop)


class Migration(migrations.Migration):

    dependencies = [
        ("tools", "0009_area"),
    ]

    operations = [
        migrations.RunPython(existing_tools_to_woodshop, migrations.RunPython.noop),
    ]
