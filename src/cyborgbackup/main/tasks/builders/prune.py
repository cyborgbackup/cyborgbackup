import logging

logger = logging.getLogger('cyborgbackup.main.tasks.builders.prune')


def _build_args_for_prune(job, **kwargs):
    args = []
    if job.client_id:
        prefix = '{}-{}-'.format(job.policy.policy_type, job.client.hostname)
        args = ['borg', 'prune', '-v', '--list']
        args += ['--prefix', prefix]
        if job.policy.keep_hourly and job.policy.keep_hourly > 0:
            args += ['--keep-hourly={}'.format(job.policy.keep_hourly)]
        if job.policy.keep_daily and job.policy.keep_daily > 0:
            args += ['--keep-daily={}'.format(job.policy.keep_daily)]
        if job.policy.keep_weekly and job.policy.keep_weekly > 0:
            args += ['--keep-weekly={}'.format(job.policy.keep_weekly)]
        if job.policy.keep_monthly and job.policy.keep_monthly > 0:
            args += ['--keep-monthly={}'.format(job.policy.keep_monthly)]
        if job.policy.keep_yearly and job.policy.keep_yearly > 0:
            args += ['--keep-monthly={}'.format(job.policy.keep_yearly)]
    return args
