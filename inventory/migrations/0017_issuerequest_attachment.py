from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0016_user_department_user_section'),
    ]

    operations = [
        migrations.AddField(
            model_name='issuerequest',
            name='attachment',
            field=models.FileField(blank=True, null=True, upload_to='issue_request_files/'),
        ),
    ]

