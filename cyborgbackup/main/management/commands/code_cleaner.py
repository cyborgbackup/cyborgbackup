# Django
from django.core.management.base import BaseCommand
from django.db import transaction, connection


class Command(BaseCommand):
    """
    Management command to clean orphan running jobs.
    """

    help = 'Clean old unecessary model in DB.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            default=False, help='Dry run mode (show items that would '
                                                'be removed)')

    @transaction.atomic
    def handle(self, *args, **options):
        self.dry_run = bool(options.get('dry_run', False))
        with connection.cursor() as cursor:
            cursor.execute("UPDATE bar SET foo = 1 WHERE baz = %s", [self.baz])
            cursor.execute("SELECT foo FROM bar WHERE baz = %s", [self.baz])
            row = cursor.fetchone()
