import django.db.models.deletion
from django.db import migrations, models

import ssi.models


class Migration(migrations.Migration):

    dependencies = [
        ("ssi", "0011_chatinvitation_portal_accepted_at"),
    ]

    operations = [
        # Existing chat messages were keyed by a single connection_id with no
        # reliable record of who actually sent each one -- the very ambiguity
        # behind the bug this migration fixes -- so there is nothing worth
        # preserving; clear them rather than guess at attribution.
        migrations.RunSQL("DELETE FROM ssi_basicmessage;", reverse_sql=migrations.RunSQL.noop),
        migrations.RemoveField(
            model_name="chatinvitation",
            name="portal_accepted_at",
        ),
        migrations.AddField(
            model_name="chatinvitation",
            name="counterparty_connection_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="chatinvitation",
            name="counterparty_invitation_msg_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="chatinvitation",
            name="counterparty_invitation_url",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="chatinvitation",
            name="counterparty_invitation_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="chatinvitation",
            name="counterparty_token",
            field=models.CharField(db_index=True, default=ssi.models.short_token, max_length=32),
        ),
        migrations.RemoveField(
            model_name="basicmessage",
            name="connection_id",
        ),
        migrations.RemoveField(
            model_name="basicmessage",
            name="outgoing",
        ),
        migrations.AddField(
            model_name="basicmessage",
            name="sender_role",
            field=models.CharField(default="student", max_length=20),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="basicmessage",
            name="chat",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="messages",
                to="ssi.chatinvitation",
            ),
            preserve_default=False,
        ),
    ]
