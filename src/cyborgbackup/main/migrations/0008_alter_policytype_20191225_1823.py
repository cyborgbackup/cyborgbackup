from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('main', '0007_auto_20191110_0123'),
    ]

    operations = [
        migrations.AlterField(
            model_name='policy',
            name='policy_type',
            field=models.CharField(
                choices=[('rootfs', 'Root FileSystem'), ('vm', 'Virtual Machine'), ('mysql', 'MySQL'),
                         ('postgresql', 'PostgreSQL'), ('piped', 'Piped Backup'), ('config', 'Only /etc'),
                         ('mail', 'Only mail directory'), ('folders', 'Specified folders')], default='rootfs',
                max_length=20)
        ),
    ]
