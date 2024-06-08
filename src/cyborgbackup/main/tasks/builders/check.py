import logging
import os
import stat
import tempfile

from django.conf import settings

from cyborgbackup.main.models import User
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.tasks.builders.helpers import build_env
from cyborgbackup.main.utils.common import load_module_provider

logger = logging.getLogger('cyborgbackup.main.tasks.builders.check')


def _build_args_for_check(job, **kwargs):
    args = []
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
    if job.client_id and job.policy.policy_type != 'vm':
        try:
            setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
            client_user = setting_client_user.value
        except Exception:
            client_user = 'root'
        handle, path = tempfile.mkstemp()
        f = os.fdopen(handle, 'w')
        base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'prepare_client')
        with open(base_script) as fs:
            script = fs.read()
        f.write(script)
        f.close()
        handle_env, path_env = tempfile.mkstemp()
        f = os.fdopen(handle_env, 'w')
        for key, var in env.items():
            f.write('export {}="{}"\n'.format(key, var))
        f.close()
        os.chmod(path, stat.S_IEXEC | stat.S_IREAD)
        args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += ['{}@{}'.format(client_user, job.client.hostname)]
        if job.client.port != 22:
            args += ['-p', job.client.port]
        args += ['\"', 'mkdir', '-p', env['PRIVATE_DATA_DIR'], '\"', '&&']
        args += ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += ['-o', 'PreferredAuthentications=publickey']
        if job.client.port != 22:
            args += ['-P' + job.client.port]
        args += [path, path_env, '{}@{}:{}/'.format(client_user, job.client.hostname, env['PRIVATE_DATA_DIR'])]
        args += ['&&', 'rm', '-f', path, path_env, '&&']
        args += ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        if job.client.port != 22:
            args += ['-p', job.client.port]
        args += ['{}@{}'.format(client_user, job.client.hostname)]
        args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        args += [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)),
                 '; exitcode=$?;',
                 'rm',
                 '-rf',
                 env['PRIVATE_DATA_DIR'],
                 '; exit $exitcode\"']
    if job.client_id and job.policy.policy_type == 'vm':
        try:
            setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
            client_user = setting_client_user.value
        except Exception:
            client_user = 'root'
        handle, path_prepare = tempfile.mkstemp()
        f = os.fdopen(handle, 'w')
        base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'prepare_hypervisor')
        with open(base_script) as fs:
            script = fs.read()
        f.write(script)
        f.close()
        handle, path_backup_script = tempfile.mkstemp()
        f = os.fdopen(handle, 'w')
        provider = load_module_provider(job.policy.vmprovider)
        hypervisor_hostname = provider.get_client(job.client.hostname)
        f.write(provider.get_script())
        f.close()
        backup_script_path = os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_backup_script))
        env.update({'CYBORGBACKUP_BACKUP_SCRIPT': backup_script_path})
        handle_env, path_env = tempfile.mkstemp()
        f = os.fdopen(handle_env, 'w')
        for key, var in env.items():
            f.write('export {}="{}"\n'.format(key, var))
        f.close()
        os.chmod(path_prepare, stat.S_IEXEC | stat.S_IREAD)
        args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += ['{}@{}'.format(client_user, hypervisor_hostname)]
        args += ['\"', 'mkdir', '-p', env['PRIVATE_DATA_DIR'], '\"', '&&']
        args += ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += [path_prepare,
                 path_env,
                 path_backup_script,
                 '{}@{}:{}/'.format(client_user, hypervisor_hostname, env['PRIVATE_DATA_DIR'])]
        args += ['&&', 'rm', '-f', path_env, path_prepare, path_backup_script, '&&']
        args += ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += ['{}@{}'.format(client_user, hypervisor_hostname)]
        args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        args += [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_prepare)),
                 '; exitcode=$?;',
                 'rm',
                 '-rf',
                 env['PRIVATE_DATA_DIR'],
                 '; exit $exitcode\"']
    if job.repository_id:
        handle, path = tempfile.mkstemp()
        f = os.fdopen(handle, 'w')
        base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'prepare_repository')
        with open(base_script) as fs:
            script = fs.read()
        f.write(script)
        f.close()
        os.chmod(path, stat.S_IEXEC | stat.S_IREAD)
        handle_env, path_env = tempfile.mkstemp()
        f = os.fdopen(handle_env, 'w')
        for key, var in env.items():
            if key == 'CYBORG_BORG_REPOSITORY' and ':' in var:
                var = var.split(':')[1]
            f.write('export {}="{}"\n'.format(key, var))
        f.close()
        repository_conn = job.policy.repository.path.split(':')[0]
        args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += [repository_conn]
        args += ['\"', 'mkdir', '-p', env['PRIVATE_DATA_DIR'], '\"', '&&']
        args += ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += [path, path_env, '{}:{}/'.format(repository_conn, env['PRIVATE_DATA_DIR'])]
        args += ['&&', 'rm', '-f', path, path_env, '&&']
        args += ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        args += [repository_conn]
        args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        args += [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)),
                 '; exitcode=$?;',
                 'rm',
                 '-rf',
                 env['PRIVATE_DATA_DIR'],
                 '; exit $exitcode\"']
        args += ['rm', path, path_env]
    return args
