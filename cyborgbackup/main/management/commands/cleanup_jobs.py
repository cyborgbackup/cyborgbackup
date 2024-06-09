import datetime
import os
import re
import shutil
import stat
import tempfile
from collections import OrderedDict
from io import StringIO

import pymongo
from django.conf import settings
# Django
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from packaging.version import parse, Version

from cyborgbackup.main.expect import run
# CyBorgBackup
from cyborgbackup.main.models import Job, Repository
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.utils.common import get_ssh_version
from cyborgbackup.main.utils.encryption import decrypt_field

db = pymongo.MongoClient(settings.MONGODB_URL).local

OPENSSH_KEY_ERROR = u'''\
It looks like you're trying to use a private key in OpenSSH format, which \
isn't supported by the installed version of OpenSSH on this instance. \
Try upgrading OpenSSH or providing your private key in an different format. \
'''


class Command(BaseCommand):
    """
    Management command to cleanup old jobs.
    """

    help = 'Remove old jobs from the database.'

    cleanup_paths = []

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            default=False, help='Dry run mode (show items that would '
                                                'be removed)')
        parser.add_argument('--jobs', dest='only_jobs', action='store_true',
                            default=True,
                            help='Remove jobs')

    def get_password_prompts(self, **kwargs):
        d = OrderedDict()
        for k, v in kwargs['passwords'].items():
            d[re.compile(r'Enter passphrase for .*' + k + r':\s*?$', re.M)] = k
            d[re.compile(r'Enter passphrase for .*' + k, re.M)] = k
        d[re.compile(r'Bad passphrase, try again for .*:\s*$', re.M)] = ''
        return d

    def get_ssh_key_path(self, instance, **kwargs):
        """
        If using an SSH key, return the path for use by ssh-agent.
        """
        private_data_files = kwargs.get('private_data_files', {})
        if 'ssh' in private_data_files.get('credentials', {}):
            return private_data_files['credentials']['ssh']

        return ''

    def build_passwords(self, job, **kwargs):
        """
        Build a dictionary of passwords for SSH private key, SSH user, sudo/su.
        """
        passwords = {}
        for setting in Setting.objects.filter(key__contains='ssh_key'):
            set = Setting.objects.get(key=setting.key.replace('ssh_key', 'ssh_password'))
            passwords['credential_{}'.format(setting.key)] = decrypt_field(set, 'value')
        return passwords

    def build_private_data(self, instance, **kwargs):
        """
        Return SSH private key data (only if stored in DB as ssh_key_data).
        Return structure is a dict of the form:
        """
        private_data = {'credentials': {}}
        for sets in Setting.objects.filter(key__contains='ssh_key'):
            # If we were sent SSH credentials, decrypt them and send them
            # back (they will be written to a temporary file).
            private_data['credentials'][sets] = decrypt_field(sets, 'value') or ''

        return private_data

    def build_private_data_dir(self, instance, **kwargs):
        """
        Create a temporary directory for job-related files.
        """
        path = tempfile.mkdtemp(prefix='cyborgbackup_%s_' % instance.pk, dir='/var/tmp/cyborgbackup')
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.cleanup_paths.append(path)
        return path

    def build_private_data_files(self, instance, **kwargs):
        """
        Creates temporary files containing the private data.
        Returns a dictionary i.e.,

        {
            'credentials': {
                <cyborgbackup.main.models.Credential>: '/path/to/decrypted/data',
                <cyborgbackup.main.models.Credential>: '/path/to/decrypted/data',
                <cyborgbackup.main.models.Credential>: '/path/to/decrypted/data',
            }
        }
        """
        private_data = self.build_private_data(instance, **kwargs)
        private_data_files = {'credentials': {}}
        if private_data is not None:
            ssh_ver = get_ssh_version()
            ssh_too_old = True if ssh_ver == "unknown" else parse(ssh_ver) < Version("6.0")
            openssh_keys_supported = ssh_ver != "unknown" and parse(ssh_ver) >= Version("6.5")
            for sets, data in private_data.get('credentials', {}).items():
                # Bail out now if a private key was provided in OpenSSH format
                # and we're running an earlier version (<6.5).
                if 'OPENSSH PRIVATE KEY' in data and not openssh_keys_supported:
                    raise RuntimeError(OPENSSH_KEY_ERROR)
            listpaths = []
            for sets, data in private_data.get('credentials', {}).items():
                # OpenSSH formatted keys must have a trailing newline to be
                # accepted by ssh-add.
                if 'OPENSSH PRIVATE KEY' in data and not data.endswith('\n'):
                    data += '\n'
                # For credentials used with ssh-add, write to a named pipe which
                # will be read then closed, instead of leaving the SSH key on disk.
                if sets and not ssh_too_old:
                    name = 'credential_{}'.format(sets.key)
                    path = os.path.join(kwargs['private_data_dir'], name)
                    run.open_fifo_write(path, data)
                    listpaths.append(path)
            if len(listpaths) > 1:
                private_data_files['credentials']['ssh'] = listpaths
            elif len(listpaths) == 1:
                private_data_files['credentials']['ssh'] = listpaths[0]

        return private_data_files

    def launch_command(self, cmd, instance, key, path, **kwargs):
        cwd = '/tmp/'
        env = {'BORG_PASSPHRASE': key, 'BORG_REPO': path, 'BORG_RELOCATED_REPO_ACCESS_IS_OK': 'yes',
               'BORG_RSH': 'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'}
        args = cmd
        safe_args = args

        kwargs['private_data_dir'] = self.build_private_data_dir(instance, **kwargs)
        kwargs['private_data_files'] = self.build_private_data_files(instance, **kwargs)
        kwargs['passwords'] = self.build_passwords(instance, **kwargs)

        expect_passwords = {}
        for k, v in self.get_password_prompts(**kwargs).items():
            expect_passwords[k] = kwargs['passwords'].get(v, '') or ''

        _kw = dict(
            expect_passwords=expect_passwords,
            job_timeout=getattr(settings, 'DEFAULT_JOB_TIMEOUT', 0),
            idle_timeout=getattr(settings, 'JOB_RUN_IDLE_TIMEOUT', None),
            extra_update_fields={},
            pexpect_timeout=getattr(settings, 'PEXPECT_TIMEOUT', 5),
        )
        stdout_handle = StringIO()

        ssh_key_path = self.get_ssh_key_path(instance, **kwargs)
        # If we're executing on an isolated host, don't bother adding the
        # key to the agent in this environment
        if ssh_key_path:
            ssh_auth_sock = os.path.join(kwargs['private_data_dir'], 'ssh_auth.sock')
            args = run.wrap_args_with_ssh_agent(args, ssh_key_path, ssh_auth_sock)
            safe_args = run.wrap_args_with_ssh_agent(safe_args, ssh_key_path, ssh_auth_sock)

        status, rc = run.run_pexpect(
            args, cwd, env, stdout_handle, **_kw
        )

        lines = stdout_handle.getvalue().splitlines()
        shutil.rmtree(kwargs['private_data_dir'])
        return lines

    def cleanup_jobs(self):
        # Sanity check: Is there already a running job on the System?
        jobs = Job.objects.filter(status="running")
        if jobs.exists():
            print('A job is already running, exiting.')
            return

        repos = Repository.objects.filter()
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
            keepJobs = []
            deletedJobs = []
            if entries.exists():
                for entry in entries:
                    if entry.archive_name != '' and entry.archive_name and entry.archive_name not in repoArchives:
                        action_text = 'would delete' if self.dry_run else 'deleting'
                        print('{} {}'.format(action_text, entry.archive_name))
                        if not self.dry_run:
                            db.catalog.delete_many({'archive_name': entry.archive_name})
                            deletedJobs.append(entry)
                            entry.delete()
                    else:
                        if entry.archive_name is None and entry.created < (
                                timezone.now() - datetime.timedelta(days=settings.JOB_RETENTION)):
                            action_text = 'would delete' if self.dry_run else 'deleting'
                            print('{} orphan JobID={} => {}'.format(action_text, entry.pk, entry.name))
                            if not self.dry_run:
                                entry.delete()

            if not self.dry_run:
                Job.objects.exclude(job_type='job') \
                    .filter(dependent_jobs_id__isnull=True,
                            master_job_id__isnull=True,
                            created__lt=(timezone.now() - datetime.timedelta(days=settings.JOB_RETENTION))) \
                    .delete()

        return 0, 0

    @transaction.atomic
    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
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
                    print('{}: {} would be deleted, {} would be skipped.'.format(m.replace('_', ' '),
                                                                                 deleted, skipped))
                else:
                    print('{}: {} deleted, {} skipped.'.format(m.replace('_', ' '), deleted, skipped))
