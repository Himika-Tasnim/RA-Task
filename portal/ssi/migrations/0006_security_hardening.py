"""
Security hardening: bind logins to a browser, make them single-use, and scope
chats to their owner.

`pres_ex_id` is visible in the public login page's polling URL. Without
`browser_key` anyone who observed it could complete the login in their own
browser once the real holder presented, taking over the session; without
`consumed_at` the same verified presentation could be replayed repeatedly.

`owner_id_number` stops one logged-in member opening another pair's
conversation by guessing a person id.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("ssi", "0005_role_neutral_and_per_role_credentials")]

    operations = [
        migrations.AddField(
            model_name="loginsession",
            name="browser_key",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="loginsession",
            name="consumed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chatinvitation",
            name="owner_id_number",
            field=models.CharField(blank=True, db_index=True, max_length=60),
        ),
    ]
