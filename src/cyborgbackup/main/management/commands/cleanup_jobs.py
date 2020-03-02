
# Django
from django.core.management.base import BaseCommand
from django.db import transaction

# CyBorgBackup
from cyborgbackup.main.models import Job, Repository


class Command(BaseCommand):
    '''
    Management command to cleanup old jobs.
    '''

    help = 'Remove old jobs  from the database.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            default=False, help='Dry run mode (show items that would '
                            'be removed)')
        parser.add_argument('--jobs', dest='only_jobs', action='store_true',
                            default=True,
                            help='Remove jobs')

    def cleanup_jobs(self):
        # Sanity check: Is there already a running job on the System?
        jobs = Job.objects.filter(status="running")
        if jobs.exists():
            print('A job is already running, exiting.')
            return

        repos = Repository.objects.filter(enabled=True)
        repoArchives = []
        if repos.exists():
            for repo in repos:
                lines = self.launch_command(["borg", "list", "::"], repo, repo.repository_key, repo.path)

                for line in lines:
                    archive_name = line.split(' ')[0]  #
                    for type in ('rootfs', 'vm', 'mysql', 'postgresql', 'config', 'piped', 'mail', 'folders'):
                        if '{}-'.format(type) in archive_name:
                            repoArchives.append(archive_name)

                entries = Job.objects.filter(job_type='job')
                if entries.exists():
                    for entry in entries:
                        if entry.archive_name != '' and entry.archive_name not in repoArchives:
                            action_text = 'would delete' if self.dry_run else 'deleting'
                            self.logger.info('%s %s', action_text, entry.archive_name)
                            if not self.dry_run:
                                entry.delete()
        return 0, 0

    @transaction.atomic
    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.init_logging()
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
                skipped, deleted = getattr(self, 'cleanup_%s' % m)()
                if self.dry_run:
                    self.logger.log(99, '%s: %d would be deleted, %d would be skipped.', m.replace('_', ' '),
                                    deleted, skipped)
                else:
                    self.logger.log(99, '%s: %d deleted, %d skipped.', m.replace('_', ' '), deleted, skipped)
