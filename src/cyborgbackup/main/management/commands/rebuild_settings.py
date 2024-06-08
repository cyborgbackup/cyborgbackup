import json

from django.apps import apps
# Django
from django.core.management.base import BaseCommand
from django.db import transaction

# CyBorgBackup
from cyborgbackup.main.models.settings import Setting


class Command(BaseCommand):
    """
    Management command to rebuild settings with group and order.
    """

    help = 'Rebuild settings with group and order.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            default=False, help='Dry run mode (show items that would '
                                                'be removed)')

    @transaction.atomic
    def handle(self, *args, **options):
        added = updated = skipped = 0
        self.dry_run = bool(options.get('dry_run', False))

        main_path = apps.get_app_config('main').path
        with open('{}/fixtures/settings.json'.format(main_path), 'r') as f:
            fixtures = json.loads(f.read())
        existing = []

        settings = Setting.objects.all()
        if settings.exists():
            for setting in settings:
                existing.append(setting.key)
                if setting.order == 0 or setting.group is None:
                    item = [x for x in fixtures if x['fields']['key'] == setting.key and x['model'] == 'main.setting'][
                        0]
                    updated = updated + 1
                    if not self.dry_run:
                        setting.order = item['fields']['order']
                        setting.group = item['fields']['group']
                        setting.save()
                else:
                    skipped = skipped + 1
        for new_set in fixtures:
            if new_set['model'] == 'main.setting' and new_set['fields']['key'] not in existing:
                added = added + 1
                if not self.dry_run:
                    set = Setting(**new_set['fields'])
                    set.save()

        if self.dry_run:
            print('Settings: {} would be added, {} would be updated, {} would be skipped.'.format(added, updated,
                                                                                                  skipped))
        else:
            print('Settings: {} added, {} updated, {} skipped.'.format(added, updated, skipped))
