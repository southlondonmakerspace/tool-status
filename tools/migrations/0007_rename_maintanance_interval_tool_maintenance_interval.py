from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tools', '0006_tool_latest_issue'),
    ]

    operations = [
        migrations.RenameField(
            model_name='tool',
            old_name='maintanance_interval',
            new_name='maintenance_interval',
        ),
    ]
