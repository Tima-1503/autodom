# Generated by Django 5.1.7 on 2025-03-31 05:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('service_app', '0005_remove_worksession_initial_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='worksession',
            name='last_action',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='worksession',
            name='pause_reason_code',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
    ]
