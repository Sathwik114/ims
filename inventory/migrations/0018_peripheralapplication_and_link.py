from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0017_issuerequest_attachment'),
    ]

    operations = [
        migrations.CreateModel(
            name='PeripheralApplication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('form_id', models.PositiveIntegerField(blank=True, db_index=True, null=True, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('application_department', models.CharField(blank=True, default='', max_length=50)),
                ('user_full_name', models.CharField(blank=True, default='', max_length=200)),
                ('employee_id', models.CharField(blank=True, default='', max_length=100)),
                ('intercom_no', models.CharField(blank=True, default='', max_length=100)),
                ('equipment_name', models.CharField(blank=True, default='', max_length=250)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('equipment_type', models.CharField(blank=True, default='', max_length=100)),
                ('budget_number', models.CharField(blank=True, default='', max_length=100)),
                ('remaining_pcs_count', models.CharField(blank=True, default='', max_length=100)),
                ('account_passed_date', models.DateField(blank=True, null=True)),
                ('requirement_date', models.DateField(blank=True, null=True)),
                ('specification', models.TextField(blank=True, default='')),
                ('additional_item', models.TextField(blank=True, default='')),
                ('reason_of_application', models.TextField(blank=True, default='')),
                ('applicant_name', models.CharField(blank=True, default='', max_length=200)),
                ('head_of_section', models.CharField(blank=True, default='', max_length=200)),
                ('department_head', models.CharField(blank=True, default='', max_length=200)),
                ('signed_form_file', models.FileField(blank=True, null=True, upload_to='peripheral_applications/')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='peripheral_applications', to='inventory.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='issuerequest',
            name='application_form',
            field=models.ForeignKey(blank=True, help_text='Printed brochure/application form linked to this request', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='issue_requests', to='inventory.peripheralapplication'),
        ),
    ]

