import logging
import os
import stat
import tempfile

from django.conf import settings

from cyborgbackup.main.exceptions import JobCatalogException
from cyborgbackup.main.models import User, JobEvent
from cyborgbackup.main.tasks.builders.helpers import build_env

logger = logging.getLogger('cyborgbackup.main.tasks.builders.catalog')


def _build_args_for_catalog(job, **kwargs):
    agent_users = User.objects.filter(is_agent=True)
    env = build_env(job, **kwargs)
    args = []
    if not agent_users.exists():
        agent_user = User()
        agent_user.email = 'cyborg@agent.local'
        agent_user.is_superuser = True
        agent_user.is_agent = True
        agent_user.save()
    else:
        agent_user = agent_users.first()
    if job.client_id:
        handle, path = tempfile.mkstemp()
        f = os.fdopen(handle, 'w')
        if not job.master_job:
            raise JobCatalogException("Unable to get master job")

        job_events = JobEvent.objects.filter(
            job=job.master_job.pk,
            stdout__contains="Archive name: {}".format(
                job.master_job.policy.policy_type
            )
        )
        archive_name = None
        if job_events.exists():
            job_stdout = job_events.first().stdout
            archive_name = job_stdout.split(':')[1].strip()
        if not archive_name:
            raise JobCatalogException("Latest backup haven't archive name in the report")
        job.master_job.archive_name = archive_name
        job.master_job.save()
        base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'fill_catalog')
        with open(base_script) as fs:
            script = fs.read()
        f.write(script)
        f.close()
        os.chmod(path, stat.S_IEXEC | stat.S_IREAD)
        handle_env, path_env = tempfile.mkstemp()
        f = os.fdopen(handle_env, 'w')
        for key, var in env.items():
            f.write('export {}="{}"\n'.format(key, var))
        f.close()
        repository_conn = job.policy.repository.path.split(':')[0]
        args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += [repository_conn]
        args += ['\"', 'mkdir', '-p', env['PRIVATE_DATA_DIR'], '\"', '&&']
        args += ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += [path, path_env, '{}:{}/'.format(repository_conn, env['PRIVATE_DATA_DIR'])]
        args += ['&&', 'rm', '-f', path, path_env, '&&']
        args += ['ssh', '-Ao', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += [repository_conn]
        args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        args += [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)),
                 '; exitcode=$?;',
                 'rm',
                 '-rf',
                 env['PRIVATE_DATA_DIR'],
                 '; exit $exitcode\"']
    return args
