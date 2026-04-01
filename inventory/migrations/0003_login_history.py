from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_issuerequest_approval_note_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoginHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('logged_in_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('ip_address', models.CharField(blank=True, default='', max_length=64)),
                ('user_agent', models.CharField(blank=True, default='', max_length=512)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='login_history', to='inventory.user')),
            ],
            options={
                'verbose_name_plural': 'Login history',
                'ordering': ['-logged_in_at'],
            },
        ),
    ]

