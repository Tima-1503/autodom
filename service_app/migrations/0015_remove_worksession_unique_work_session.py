# Generated by Django 5.1.7 on 2025-04-17 12:07

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('service_app', '0014_remove_worksession_unique_work_session_and_more'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='worksession',
            name='unique_work_session',
        ),
    ]
