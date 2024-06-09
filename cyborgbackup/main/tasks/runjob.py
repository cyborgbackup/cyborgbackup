import logging
import re

from cyborgbackup.main.models import Job, JobEvent
from cyborgbackup.main.tasks.basetask import BaseTask
from cyborgbackup.main.tasks.builders.backup import _build_args_for_backup
from cyborgbackup.main.tasks.builders.catalog import _build_args_for_catalog
from cyborgbackup.main.tasks.builders.check import _build_args_for_check
from cyborgbackup.main.tasks.builders.prune import _build_args_for_prune
from cyborgbackup.main.tasks.builders.restore import _build_args_for_restore
from cyborgbackup.main.tasks.shared import cyborgbackup_notifier

logger = logging.getLogger('cyborgbackup.main.tasks.runjob')


class RunJob(BaseTask):
    """
    Celery task to run a job.
    """

    name = 'cyborgbackup.main.tasks.run_job'
    model = Job
    event_model = JobEvent
    event_data_key = 'job_id'

    def final_run_hook(self, instance, status, **kwargs):
        """
        Hook for any steps to run after job/task is marked as complete.
        """
        if instance.job_type == 'job':
            cyborgbackup_notifier.apply_async(args=('after', instance.pk))

    def build_args(self, job, **kwargs):
        """
        Build command line argument list for running the task,
        optionally using ssh-agent for public/private key authentication.
        """
        if job.job_type == 'check':
            return _build_args_for_check(job, **kwargs)
        elif job.job_type == 'catalog':
            return _build_args_for_catalog(job, **kwargs)
        elif job.job_type == 'prune':
            return _build_args_for_prune(job, **kwargs)
        elif job.job_type == 'restore':
            return _build_args_for_restore(job, **kwargs)
        else:
            return _build_args_for_backup(job, **kwargs)

    def build_safe_args(self, job, **kwargs):
        return self.build_args(job, display=True, **kwargs)

    def get_password_prompts(self, **kwargs):
        d = super(RunJob, self).get_password_prompts(**kwargs)
        for k, _ in kwargs['passwords'].items():
            d[re.compile(r'Enter passphrase for .*' + k + r':\s*?$', re.M)] = k
            d[re.compile(r'Enter passphrase for .*' + k, re.M)] = k
        d[re.compile(r'Bad passphrase, try again for .*:\s*$', re.M)] = ''
        return d
