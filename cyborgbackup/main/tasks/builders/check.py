import logging
import os
import tempfile

from django.contrib.auth import get_user_model

from cyborgbackup.main.tasks.builders.helpers import build_env

logger = logging.getLogger('cyborgbackup.main.tasks.builders.check')


def _build_args_for_check(job, **kwargs):
    args = []
    User = get_user_model()
    agent_users = User.objects.filter(is_agent=True)
    env = build_env(job, **kwargs)
    if not agent_users.exists():
        agent_user = User()
        agent_user.email = 'cyborg@agent.local'
        agent_user.is_superuser = True
        agent_user.is_agent = True
        agent_user.save()
    else:
        agent_user = agent_users.first()
    if job.client_id:
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
        args += [path_env, '{}:{}/'.format(repository_conn, env['PRIVATE_DATA_DIR'])]
        args += ['&&', 'rm', '-f', path_env, '&&']
        args += ['ssh', '-Ao', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += [repository_conn]
        args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        args += ['borg', 'check', '{}::{}'.format(job.policy.repository.path, job.archive_name),
                 '; exitcode=$?;',
                 'rm', '-rf', env['PRIVATE_DATA_DIR'],
                 '; exit $exitcode\"']
    return args
