
# Django
from django.core.management.base import BaseCommand
from django.db import transaction

# CyBorgBackup
from cyborgbackup.main.models import Setting


class Command(BaseCommand):
    '''
    Management command to rebuild settings with group and order.
    '''

    help = 'Rebuild settings with group and order.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            default=False, help='Dry run mode (show items that would '
                            'be removed)')

    @transaction.atomic
    def handle(self, *args, **options):
        self.dry_run = bool(options.get('dry_run', False))

        settings = Setting.objects.all()
        if settings.exists():
            for setting in settings:
                if setting.order is None or setting.group is None:

                    if self.dry_run:
                        print('{}: {} would be updated, {} would be skipped.'.format(m.replace('_', ' '),
                                        updated, skipped))
                    else:
                        print('{}: {} updated, {} skipped.'.format(m.replace('_', ' '), updated, skipped))
