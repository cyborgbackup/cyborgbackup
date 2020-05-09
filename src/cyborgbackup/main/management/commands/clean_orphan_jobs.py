
# Django
from django.core.management.base import BaseCommand
from django.db import transaction

# CyBorgBackup
from cyborgbackup.main.models import Job, Repository


class Command(BaseCommand):
    '''
    Management command to clean orphan running jobs.
    '''

    help = 'Remove old jobs from the database.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            default=False, help='Dry run mode (show items that would '
                            'be removed)')

    def cleanup_jobs(self):
        # Sanity check: Is there already a running job on the System?
        jobs = Job.objects.filter(status="running")

        counter = 0
        if jobs.exists():
            for job in jobs:
                if not self.dry_run:
                    job.status = 'error'
                    job.save()
                counter += 1
        return 0, counter

    @transaction.atomic
    def handle(self, *args, **options):
        self.dry_run = bool(options.get('dry_run', False))

        model_names = ('jobs',)
        models_to_cleanup = set()
        for m in model_names:
            if options.get('only_%s' % m, False):
                models_to_cleanup.add(m)
        if not models_to_cleanup:
            models_to_cleanup.update(model_names)

        for m in model_names:
            if m in models_to_cleanup:
                skipped, updated = getattr(self, 'cleanup_%s' % m)()
                if self.dry_run:
                    print('{}: {} would be updated, {} would be skipped.'.format(m.replace('_', ' '),
                                    updated, skipped))
                else:
                    print('{}: {} updated, {} skipped.'.format(m.replace('_', ' '), updated, skipped))
