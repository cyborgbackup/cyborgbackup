# Generated by Django 2.2.12 on 2020-04-13 19:28

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('main', '0009_auto_20200413_1638'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='bandwidth_limit',
            field=models.PositiveIntegerField(blank=True, default=None, null=True),
        ),
    ]
