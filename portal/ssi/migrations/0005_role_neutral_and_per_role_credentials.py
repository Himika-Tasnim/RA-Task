"""
Role-neutral attributes, one credential type per role, person-to-person chats.

Written by hand rather than generated: `makemigrations` cannot tell a rename
from a drop-and-add without asking, and dropping would lose the issuance
history.

LedgerArtifacts rows are cleared rather than migrated. They point at the old
single cred-def, which no longer exists under the new per-role schemas, so
carrying them forward would leave the portal pointing at a credential
definition the login can no longer accept. `manage.py ssi_setup` repopulates
them.
"""

from django.db import migrations, models
import django.db.models.deletion


def clear_stale_artifacts(apps, schema_editor):
    apps.get_model("ssi", "LedgerArtifacts").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [("ssi", "0004_issuancerequest_role")]

    operations = [
        # --- role-neutral attribute names --------------------------------
        migrations.RenameField(
            model_name="issuancerequest",
            old_name="student_name",
            new_name="full_name",
        ),
        migrations.RenameField(
            model_name="issuancerequest",
            old_name="student_id",
            new_name="id_number",
        ),

        # --- one published credential type per role -----------------------
        migrations.RunPython(clear_stale_artifacts, migrations.RunPython.noop),
        migrations.AddField(
            model_name="ledgerartifacts",
            name="role",
            field=models.CharField(default="student", max_length=20, unique=True),
            preserve_default=False,
        ),

        # --- chats are with a specific person -----------------------------
        migrations.AddField(
            model_name="chatinvitation",
            name="counterparty",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="chats",
                to="ssi.issuancerequest",
            ),
        ),
        migrations.AddField(
            model_name="chatinvitation",
            name="initiated_by_role",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
