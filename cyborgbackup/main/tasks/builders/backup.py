import json
import logging
import os
import tempfile

from django.conf import settings

from cyborgbackup.main.exceptions import JobCommandBuilderException
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.tasks.builders.helpers import build_env
from cyborgbackup.main.utils.common import load_module_provider

logger = logging.getLogger('cyborgbackup.main.tasks.builders.backup')


def _build_borg_cmd_for_rootfs():
    path = '/'
    excluded_dirs = ['/media',
                     '/dev',
                     '/proc',
                     '/sys',
                     '/var/run',
                     '/run',
                     '/lost+found',
                     '/mnt',
                     '/var/lib/lxcfs',
                     '/tmp']
    return path, excluded_dirs


def _build_borg_cmd_for_config():
    return '/etc', []


def _build_borg_cmd_for_folders(job):
    obj_folders = json.loads(job.policy.extra_vars)
    path = ' '.join(obj_folders['folders'])
    return path, []


def _build_borg_cmd_for_mail():
    path = '/var/lib/mail /var/mail'
    return path, []


def _build_borg_cmd_for_piped_mysql(job):
    piped = 'mysqldump'
    mysql_json = _load_mysql_json(job)
    piped = database_specify = _add_mysql_credentials(piped, mysql_json, job)
    _add_mysql_databases(piped, mysql_json, database_specify)
    return piped


def _load_mysql_json(job):
    if job.policy.extra_vars != '':
        return json.loads(job.policy.extra_vars)
    return {}


def _add_mysql_credentials(piped, mysql_json, job):
    database_specify = False
    if 'extended_mysql' in mysql_json and str(job.client.pk) in mysql_json['extended_mysql'].keys():
        return _extended_mysql_credential(piped, mysql_json, job)
    else:
        if 'user' in mysql_json and mysql_json['user']:
            piped += " -u{}".format(mysql_json['user'])
        if 'password' in mysql_json and mysql_json['password']:
            piped += " -p'{}'".format(mysql_json['password'].replace("'", r"\'"))
    return piped, database_specify


def _extended_mysql_credential(piped, mysql_json, job):
    database_specify = False
    mysql_vars = mysql_json['extended_mysql'][str(job.client.pk)]
    if 'user' in mysql_vars['credential'] and mysql_vars['credential']['user']:
        piped += " -u{}".format(mysql_vars['credential']['user'])
    if 'password' in mysql_vars['credential'] and mysql_vars['credential']['password']:
        piped += " -p'{}'".format(mysql_vars['credential']['password'].replace("'", r"\'"))
    if 'databases' in mysql_vars and mysql_vars['databases']:
        database_specify = True
        piped += " --databases {}".format(' '.join(mysql_vars['databases']))
    return piped, database_specify


def _add_mysql_databases(piped, mysql_json, database_specify):
    if 'databases' in mysql_json and mysql_json['databases']:
        database_specify = True
        if isinstance(mysql_json['databases'], list):
            piped += " --databases {}".format(' '.join(mysql_json['databases']))
        else:
            piped += " {}".format(mysql_json['databases'])
    if not database_specify:
        piped += " --all-databases"
    return piped


# def _build_borg_cmd_for_piped_mysql(job):
#     piped = 'mysqldump'
#     database_specify = False
#     if job.policy.extra_vars != '':
#         mysql_json = json.loads(job.policy.extra_vars)
#         if 'extended_mysql' in mysql_json and str(job.client.pk) in mysql_json['extended_mysql'].keys():
#             mysql_vars = mysql_json['extended_mysql'][str(job.client.pk)]
#             if 'user' in mysql_vars['credential'] and mysql_vars['credential']['user']:
#                 piped += " -u{}".format(mysql_vars['credential']['user'])
#             if 'password' in mysql_vars['credential'] and mysql_vars['credential']['password']:
#                 piped += " -p'{}'".format(mysql_vars['credential']['password'].replace("'", r"\'"))
#             if 'databases' in mysql_vars and mysql_vars['databases']:
#                 database_specify = True
#                 piped += " --databases {}".format(' '.join(mysql_vars['databases']))
#         else:
#             if 'user' in mysql_json and mysql_json['user']:
#                 piped += " -u{}".format(mysql_json['user'])
#             if 'password' in mysql_json and mysql_json['password']:
#                 piped += " -p'{}'".format(mysql_json['password'].replace("'", r"\'"))
#             if 'databases' in mysql_json and mysql_json['databases']:
#                 database_specify = True
#                 if isinstance(mysql_json['databases'], list):
#                     piped += " --databases {}".format(' '.join(mysql_json['databases']))
#                 else:
#                     piped += " {}".format(mysql_json['databases'])
#
#     if not database_specify:
#         piped += " --all-databases"
#     return piped


def _build_borg_cmd_for_piped_postgresql(job):
    piped = ''
    database_specify = False
    if job.policy.extra_vars != '':
        pgsql_json = json.loads(job.policy.extra_vars)
        if 'extended_postgresql' in pgsql_json and str(job.client.pk) in pgsql_json['extended_postgresql'].keys():
            pgsql_vars = pgsql_json['extended_postgresql'][str(job.client.pk)]
            if 'databases' in pgsql_vars and pgsql_vars['databases']:
                database_specify = True
                piped += " --databases {}".format(' '.join(pgsql_vars['databases']))
        else:
            if 'database' in pgsql_json and pgsql_json['database']:
                database_specify = True
                piped += 'sudo -u postgres pg_dump {}'.format(pgsql_json['database'])
    if not database_specify:
        piped += 'sudo -u postgres pg_dumpall'
    return piped


def _build_borg_cmd_for_piped_vm(job):
    """ @todo : Build backup system for RAW VM"""
    provider = load_module_provider(job.policy.vmprovider)
    provider.get_client(job.client.hostname)
    piped_list = ['/var/cache/cyborgbackup/borg_backup_vm']
    return ' '.join(piped_list)


def _build_borg_cmd_for_piped_proxmox(job):
    proxmox_json = json.loads(job.policy.extra_vars)
    piped = 'vzdump --mode snapshot --stdout true '
    if 'extended_proxmox' in proxmox_json.keys() and str(job.client.pk) in proxmox_json['extended_proxmox'].keys():
        piped += ' '.join(str(x) for x in proxmox_json['extended_proxmox'][str(job.client.pk)])
    else:
        piped += '--all'
    return piped


def _build_borg_cmd_for_piped(policy_type, job):
    piped = ''
    if policy_type == 'mysql':
        return _build_borg_cmd_for_piped_mysql(job)
    elif policy_type == 'postgresql':
        return _build_borg_cmd_for_piped_postgresql(job)
    elif policy_type == 'vm':
        return _build_borg_cmd_for_piped_vm(job)
    elif policy_type == 'proxmox':
        return _build_borg_cmd_for_piped_proxmox(job)
    else:
        command_specify = False
        if job.policy.extra_vars != '':
            piped_json = json.loads(job.policy.extra_vars)
            if 'command' in piped_json and piped_json['command']:
                command_specify = True
                piped += piped_json['command']
        if not command_specify:
            raise JobCommandBuilderException('Command for piped backup not defined')
    return piped


########
# Backup host => backupHost
# Client => client
# Repository => /backup
########
# rootfs        Backup all / filesystem
# vm            Backup Virtual Machine disk using snapshot
# mysql         Backup MySQL Database
# postgresql    Backup PostgreSQL
# piped         Backup using pipe program
# config        Backup only /etc
# mail          Backup only mail directory
# folders       Backup only specified directories
########
# rootfs
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX
#            && cd /tmp/sshfs_XXX && borg create /backup::archive . && fusermount -u /tmp/sshfs"
# folders
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /folder1 /folder2"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX
#            && cd /tmp/sshfs_XXX && borg create /backup::archive . && fusermount -u /tmp/sshfs"
# config
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /etc"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX
#            && cd /tmp/sshfs_XXX && borg create /backup::archive ./etc && fusermount -u /tmp/sshfs
# mail
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /var/lib/mail"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX
#            && cd /tmp/sshfs_XXX && borg create /backup::archive ./var/lib/mail && fusermount -u /tmp/sshfs
# mysql
#   pull => ssh root@client "mysqldump | borg create borg@backupHost:/backup::archive -"
#   push => ssh borg@backupHost "ssh root@client "mysqldump" | borg create /backup::archive -"
#
# pgsql
#   pull => ssh root@client "pg_dumpall|pg_dump | borg create borg@backupHost:/backup::archive -"
#   push => ssh borg@backupHost "ssh root@client "pg_dumpall|pg_dump" | borg create /backup::archive -"
########


def build_borg_cmd(job, data_dir):
    policy_type = job.policy.policy_type
    job_date_string = job.created.strftime("%Y-%m-%d_%H-%M")
    client_user = _get_client_user()
    args = _initialize_args(client_user)
    repository_path = _get_repository_path(job)
    archive_client_name = job.client.hostname

    path, excluded_dirs, piped = _get_backup_paths_and_commands(policy_type, job)
    args += _build_borg_create_args(repository_path, policy_type, archive_client_name, job_date_string, path,
                                    excluded_dirs, data_dir, job.policy.mode_pull)

    if job.policy.mode_pull:
        client, client_user, args = _build_pull_command(job, policy_type, path, args, job_date_string, piped)
    else:
        client = job.client.hostname

    return client, client_user, args


def _get_client_user():
    try:
        setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
        return setting_client_user.value
    except Exception:
        return 'root'


def _initialize_args(client_user):
    args = []
    if client_user != 'root':
        args = ['sudo', '-E']
    args += ['borg', 'create', '--debug', '-v', '--stats']
    return args


def _get_repository_path(job):
    if not job.policy.mode_pull:
        return job.policy.repository.path
    return ''


def _get_backup_paths_and_commands(policy_type, job):
    if policy_type == 'rootfs':
        return _build_borg_cmd_for_rootfs() + ('',)
    if policy_type == 'config':
        return _build_borg_cmd_for_config() + ('',)
    if policy_type == 'folders':
        return _build_borg_cmd_for_folders(job) + ('',)
    if policy_type == 'mail':
        return _build_borg_cmd_for_mail() + ('',)
    if policy_type in ('mysql', 'postgresql', 'piped', 'vm', 'proxmox'):
        return '-', [], _build_borg_cmd_for_piped(policy_type, job)
    raise JobCommandBuilderException('Unsupported policy type')


def _build_borg_create_args(repository_path, policy_type, archive_client_name, job_date_string, path, excluded_dirs,
                            data_dir, mode_pull):
    args = ['{}::{}-{}-{}'.format(repository_path, policy_type, archive_client_name, job_date_string)]
    if mode_pull and policy_type in ('rootfs', 'config', 'mail'):
        path = '.' + path
    args.append(path)
    excluded_dirs.append(data_dir)
    keyword = '--exclude '
    if mode_pull:
        keyword += '.'
    args += (keyword + (' ' + keyword).join(excluded_dirs)).split(' ')
    return args


def _build_pull_command(job, policy_type, path, args, job_date_string, piped):
    client_uri, _ = job.policy.repository.path.split(':')
    client = client_uri.split('@')[1]
    client_user = client_uri.split('@')[0]
    if policy_type in ('rootfs', 'config', 'mail', 'folders'):
        sshfs_directory = '/var/tmp/cyborgbackup/sshfs_{}_{}'.format(client, job_date_string)
        pull_cmd = ['mkdir', '-p', sshfs_directory, '&&', 'sshfs', 'root@{}:{}'.format(client, path[1:]),
                    sshfs_directory, '&&', 'cd', sshfs_directory, '&&'] + args
        args = pull_cmd
    if policy_type in ('mysql', 'postgresql', 'piped', 'vm'):
        pull_cmd = ['ssh', '{}@{}'.format(client_user, client)]
        if client_user != 'root':
            piped = 'sudo -E ' + piped
        pull_cmd += ["'" + piped + "'|" + ' '.join(args)]
        args = pull_cmd
    return client, client_user, args


# def build_borg_cmd(job, data_dir):
#     policy_type = job.policy.policy_type
#     job_date = job.created
#     job_date_string = job_date.strftime("%Y-%m-%d_%H-%M")
#     excluded_dirs = []
#     args = []
#     piped = ''
#     path = ''
#     client = job.client.hostname
#     client_hostname = client
#     try:
#         setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
#         client_user = setting_client_user.value
#     except Exception:
#         client_user = 'root'
#     if client_user != 'root':
#         args = ['sudo', '-E'] + args
#     args += ['borg']
#     args += ['create']
#     repository_path = ''
#     if not job.policy.mode_pull:
#         repository_path = job.policy.repository.path
#     args += ['--debug', '-v', '--stats']
#     archive_client_name = job.client.hostname
#     if policy_type == 'rootfs':
#         path, excluded_dirs = _build_borg_cmd_for_rootfs()
#     if policy_type == 'config':
#         path, excluded_dirs = _build_borg_cmd_for_config()
#     if policy_type == 'folders':
#         path, excluded_dirs = _build_borg_cmd_for_folders(job)
#     if policy_type in ('rootfs', 'config', 'folders'):
#         obj_folders = json.loads(job.policy.extra_vars)
#         if 'exclude' in obj_folders.keys():
#             for item in obj_folders['exclude']:
#                 if item not in excluded_dirs:
#                     excluded_dirs.append(item)
#     if policy_type == 'mail':
#         path, excluded_dirs = _build_borg_cmd_for_mail()
#     if policy_type in ('mysql', 'postgresql', 'piped', 'vm', 'proxmox'):
#         path = '-'
#         piped = _build_borg_cmd_for_piped(policy_type, job)
#         if not job.policy.mode_pull:
#             args = [piped, '|'] + args
#
#     args += ['{}::{}-{}-{}'.format(repository_path, policy_type, archive_client_name, job_date_string)]
#
#     if job.policy.mode_pull and policy_type in ('rootfs', 'config', 'mail'):
#         path = '.' + path
#     args += [path]
#
#     excluded_dirs.append(data_dir)
#     keyword = '--exclude '
#     if job.policy.mode_pull:
#         keyword += '.'
#     args += (keyword + (' ' + keyword).join(excluded_dirs)).split(' ')
#
#     if job.policy.mode_pull:
#         (client_uri, repository_path) = job.policy.repository.path.split(':')
#         client = client_uri.split('@')[1]
#         client_user = client_uri.split('@')[0]
#         if policy_type in ('rootfs', 'config', 'mail', 'folders'):
#             sshfs_directory = '/var/tmp/cyborgbackup/sshfs_{}_{}'.format(client_hostname, job_date_string)
#             pull_cmd = ['mkdir', '-p', sshfs_directory]
#             pull_cmd += ['&&', 'sshfs', 'root@{}:{}'.format(client_hostname, path[1::]), sshfs_directory]
#             pull_cmd += ['&&', 'cd', sshfs_directory]
#             pull_cmd += ['&&'] + args
#             args = pull_cmd
#         if policy_type in ('mysql', 'postgresql', 'piped', 'vm'):
#             pull_cmd = ['ssh', '{}@{}'.format(client_user, client_hostname)]
#             if client_user != 'root':
#                 piped = 'sudo -E ' + piped
#             pull_cmd += ["'" + piped + "'|" + ' '.join(args)]
#             args = pull_cmd
#
#     return client, client_user, args


def _build_args_for_backup(job, **kwargs):
    env = build_env(job, **kwargs)
    (client, client_user, args) = build_borg_cmd(job, data_dir=env['PRIVATE_DATA_DIR'])
    extra_vars = {}
    if job.policy.extra_vars != '':
        try:
            extra_vars = json.loads(job.policy.extra_vars)
        except json.JSONDecodeError:
            pass

    handle_env, path_env = tempfile.mkstemp()
    f = os.fdopen(handle_env, 'w')
    for key, var in env.items():
        f.write('export {}="{}"\n'.format(key, var))
    f.close()

    new_args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
    new_args += ['{}@{}'.format(client_user, client)]
    if job.client.port != 22:
        new_args += ['-p', job.client.port]

    new_args += ['\"', 'mkdir', '-p', env['PRIVATE_DATA_DIR'], '\"', '&&']
    new_args += ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']

    if job.client.port != 22:
        new_args += ['-P' + job.client.port]

    path = None
    if (job.policy.policy_type == 'rootfs' and 'with_partition_table' in extra_vars.keys()
            and extra_vars['with_partition_table']):
        handle, path = tempfile.mkstemp()
        f = os.fdopen(handle, 'w')
        base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'dump_partition_table')
        with open(base_script) as fs:
            script = fs.read()
        f.write(script)
        f.close()

        new_args += [path]

    new_args += [path_env, '{}@{}:{}/'.format(client_user, client, env['PRIVATE_DATA_DIR'])]
    new_args += ['&&', 'rm', '-f', path_env, '&&']
    new_args += ['ssh', '-Ao', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
    new_args += ['{}@{}'.format(client_user, client)]

    if job.client.port != 22:
        args += ['-p', job.client.port]

    # Source Env File
    new_args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']

    # Delete Env File
    new_args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']

    # Run Pre-Hook
    # new_args += []

    # Dump Partition Table
    if (job.policy.policy_type == 'rootfs' and 'with_partition_table' in extra_vars.keys()
            and extra_vars['with_partition_table']):
        new_args += ['bash', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)), '&&',
                     'rm', '-f', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)), '&&']

    # Backup Command
    new_args += [' '.join(args), '; exitcode=$?;']

    # Delete temporary directory
    new_args += ['rm', '-rf', env['PRIVATE_DATA_DIR'], '/var/tmp/cyborgbackup/cyborg_partitioning.tgz']

    # Run Post-Hook
    # new_args += []

    # Exit with Backup Exit Code
    new_args += ['; exit $exitcode\"']

    return new_args
