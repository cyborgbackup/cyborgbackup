# Generated by Django 4.1.7 on 2023-05-30 15:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0018_client_mark_as_to_update'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='behind_firewall',
            field=models.BooleanField(default=False),
        ),
    ]