import json
import logging
import os
import stat
import tempfile

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from cyborgbackup.main.exceptions import JobCatalogException
from cyborgbackup.main.models import JobEvent
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.utils.encryption import decrypt_field

logger = logging.getLogger('cyborgbackup.main.tasks.builders.helpers')


def build_env(job, **kwargs):
    env = _initialize_env_from_settings()
    env = _set_private_data_dir(env, kwargs)
    env = _set_agent_token(env, job)
    env = _set_cyborg_url(env, job)
    env = _set_borg_repository(env, job)
    env = _set_catalog_specific_env(env, job)
    env = _set_common_borg_env(env, job)
    return env


def _initialize_env_from_settings():
    env = {}
    for attr in dir(settings):
        if attr == attr.upper() and attr.startswith('CYBORGBACKUP_'):
            env[attr] = str(getattr(settings, attr))
    return env


def _set_private_data_dir(env, kwargs):
    if 'private_data_dir' in kwargs.keys():
        env['PRIVATE_DATA_DIR'] = kwargs['private_data_dir']
    return env


def _get_or_create_agent_user():
    user_model = get_user_model()
    agent_users = user_model.objects.filter(is_agent=True)
    if not agent_users.exists():
        agent_user = user_model()
        agent_user.email = 'cyborg@agent.local'
        agent_user.is_superuser = True
        agent_user.is_agent = True
        agent_user.save()
    else:
        agent_user = agent_users.first()
    token, _ = Token.objects.get_or_create(user=agent_user)
    return agent_user, token


def _set_agent_token(env, job):
    _, token = _get_or_create_agent_user()
    if token and (job.job_type == 'check' or job.job_type == 'catalog'):
        env['CYBORG_AGENT_TOKEN'] = str(token)
    return env


def _set_cyborg_url(env, job):
    try:
        setting = Setting.objects.get(key='cyborgbackup_url')
        base_url = setting.value
    except Exception:
        base_url = 'http://web:8000'
    if job.job_type == 'check':
        if job.client_id:
            env['CYBORG_URL'] = '{}/api/v1/clients/{}/'.format(base_url, job.client_id)
        if job.repository_id:
            env['CYBORG_URL'] = '{}/api/v1/repositories/{}/'.format(base_url, job.repository_id)
    if job.job_type == 'catalog':
        env['CYBORG_URL'] = '{}/api/v1/catalogs/'.format(base_url)
    return env


def _set_borg_repository(env, job):
    if job.repository_id or job.job_type == 'catalog':
        env['CYBORG_BORG_PASSPHRASE'] = job.policy.repository.repository_key
        if job.job_type == 'catalog':
            env['CYBORG_BORG_REPOSITORY'] = job.policy.repository.path.split(':')[1]
        else:
            env['CYBORG_BORG_REPOSITORY'] = job.policy.repository.path
    return env


def _set_catalog_specific_env(env, job):
    if job.job_type == 'catalog':
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
        if archive_name:
            env['CYBORG_JOB_ARCHIVE_NAME'] = archive_name
        else:
            raise JobCatalogException('Unable to get archive from backup. Backup job may failed.')
        env['CYBORG_JOB_ID'] = str(job.master_job.pk)
    return env


def _set_common_borg_env(env, job):
    env['BORG_PASSPHRASE'] = job.policy.repository.repository_key
    env['BORG_REPO'] = job.policy.repository.path
    env['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'
    env['BORG_RSH'] = 'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
    return env


def build_cwd(job, **kwargs):
    cwd = '/var/tmp/cyborgbackup/'
    return cwd


def get_idle_timeout():
    return getattr(settings, 'JOB_RUN_IDLE_TIMEOUT', None)


def build_passwords():
    """
    Build a dictionary of passwords for SSH private key, SSH user, sudo/su.
    """
    passwords = {}
    for setting in Setting.objects.filter(key__contains='ssh_key'):
        set_parsed = Setting.objects.get(key=setting.key.replace('ssh_key', 'ssh_password'))
        passwords['credential_{}'.format(setting.key)] = decrypt_field(set_parsed, 'value')
    return passwords


def build_extra_vars_file(extra_vars, **kwargs):
    handle, path = tempfile.mkstemp(dir=kwargs.get('private_data_dir', None))
    f = os.fdopen(handle, 'w')
    f.write("# CyBorgBackup Extra Vars #\n")
    f.write(json.dumps(extra_vars))
    f.close()
    os.chmod(path, stat.S_IRUSR)
    return path
