import logging

logger = logging.getLogger('cyborgbackup.main.tasks.builders.restore')


def _build_args_for_restore(job, **kwargs):
    logger.debug(job.extra_vars)
    logger.debug(job.extra_vars_dict)
    args = []
    if job.client_id:
        args = ['mkdir', '-p', job.extra_vars_dict['dest_folder'], '&&', 'cd', job.extra_vars_dict['dest_folder'],
                '&&', 'borg', 'extract', '-v', '--list',
                '{}::{}'.format(job.policy.repository.path, job.archive_name),
                job.extra_vars_dict['item'], '-n' if job.extra_vars_dict['dry_run'] else '']
        logger.debug(' '.join(args))
    return args
