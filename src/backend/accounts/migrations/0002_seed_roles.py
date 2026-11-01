"""Install the fixed role vocabulary without creating any privileged accounts."""
import uuid

from django.db import migrations


def seed_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    for name in ("student", "maintainer", "administrator"):
        Role.objects.using(schema_editor.connection.alias).get_or_create(
            role_name=name,
            defaults={"role_id": uuid.uuid5(uuid.NAMESPACE_URL, f"compass:role:{name}")},
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    # Keep referenced roles intact on reversal; no user data is deleted here.
    operations = [migrations.RunPython(seed_roles, migrations.RunPython.noop)]
