from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ssi", "0008_studentrecord"),
    ]

    operations = [
        migrations.RenameModel(old_name="StudentRecord", new_name="MemberRecord"),
        migrations.AddField(
            model_name="memberrecord",
            name="role",
            field=models.CharField(default="student", max_length=20),
        ),
    ]
