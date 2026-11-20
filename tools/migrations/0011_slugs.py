from django.db import migrations, models
from django.utils.text import slugify

# Copied from tools.models so this migration keeps working if that changes.
RESERVED_AREA_SLUGS = {"admin", "static", "other"}


def unique_slug(name, queryset, fallback, reserved=()):
    base = slugify(name)[:45] or fallback
    if base in reserved:
        base = f"{base}-{fallback}"
    taken = set(queryset.filter(slug__startswith=base).values_list("slug", flat=True))
    slug, n = base, 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def fill_slugs(apps, schema_editor):
    Area = apps.get_model("tools", "Area")
    Tool = apps.get_model("tools", "Tool")
    for area in Area.objects.order_by("name"):
        area.slug = unique_slug(area.name, Area.objects.exclude(pk=area.pk), "area", RESERVED_AREA_SLUGS)
        area.save(update_fields=["slug"])
    for tool in Tool.objects.order_by("name"):
        siblings = Tool.objects.exclude(pk=tool.pk).filter(area_id=tool.area_id)
        tool.slug = unique_slug(tool.name, siblings, "tool")
        tool.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("tools", "0010_existing_tools_to_woodshop"),
    ]

    operations = [
        migrations.AddField(
            model_name="tool",
            name="slug",
            field=models.SlugField(default="", editable=False, max_length=50, help_text="Used in the tool's URL; made from the name. Unique within its area."),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="area",
            name="slug",
            field=models.SlugField(editable=False, help_text="Used in URLs; made from the name.", max_length=50, unique=True),
        ),
        migrations.RunPython(fill_slugs, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="tool",
            constraint=models.UniqueConstraint(fields=("area", "slug"), name="unique_tool_slug_per_area"),
        ),
    ]
