import io
import json
import logging
import os
import re
import shutil
import stat
import tempfile

try:
    import psutil
except Exception:
    psutil = None

from django.conf import settings
from cyborgbackup.main.expect import run
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.utils.encryption import decrypt_field

logger = logging.getLogger('cyborgbackup.main.modules.queriers')


class Querier:
    client = None
    client_user = 'root'

    def querier(self, module, client, params):
        try:
            setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
            self.client_user = setting_client_user.value
        except Exception:
            self.client_user = 'root'
        self.client = client
        if hasattr(self, 'querier_%s' % module):
            return getattr(self, 'querier_%s' % module)(params)
        else:
            return {}

    def querier_proxmox(self, args):
        cmd = ["/usr/bin/pvesh", "get", "/cluster/resources", "--type", "vm", "--output-format=json"]
        output, rc = self._run(cmd, sudo=True)
        vms = []
        if rc == 0:
            objs = json.loads(output[0])
            for obj in objs:
                vms.append({
                    'vmid': obj['vmid'],
                    'name': obj['name'],
                    'type': obj['type'],
                    'node': obj['node'],
                    'status': obj['status']
                })
            return vms
        else:
            return -1

    def querier_mysql(self, args):
        cmd = ['mysql', '-NBe', '\'SHOW DATABASES\'']
        # cmd = ['echo', '\'\n\nshow databases;\nshow tables;\'', '|', 'mysql']
        queryargs = {}
        if 'user' in args.keys():
            cmd += ['-u{}'.format(args['user'])]
        if 'password' in args.keys():
            cmd += ['-p']
            queryargs['password'] = args['password']
        if 'port' in args.keys():
            cmd += ['-P{}'.format(args['port'])]
        output, rc = self._run(cmd, queryargs=queryargs)
        dbs = []
        if rc == 0:
            for line in output:
                dbs.append({'name': line})
            return dbs
        else:
            return -1

    def querier_postgresql(self, args):
        cmd = ['psql', '-F\',\'', '-t', '-A', '-c', '\'SELECT datname FROM pg_database;\'']
        if self.client_user == 'root':
            cmd = ['cd', '/var/tmp/cyborgbackup', '&&', 'sudo', '-u', 'postgres'] + cmd
        output, rc = self._run(cmd)
        dbs = []
        if rc == 0:
            for line in output:
                dbs.append({'name': line})
            return dbs
        else:
            return -1

    def _run(self, cmd, sudo=False, queryargs=None):
        args = []
        rc = -1
        finalOutput = []

        if self.client_user != 'root' and sudo:
            args = ['sudo', '-E'] + args
        args += cmd

        kwargs = {}
        try:
            env = {}
            for attr in dir(settings):
                if attr == attr.upper() and attr.startswith('CYBORGBACKUP_'):
                    env[attr] = str(getattr(settings, attr))

            path = tempfile.mkdtemp(prefix='cyborgbackup_module', dir='/var/tmp/cyborgbackup/')
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            kwargs['private_data_dir'] = path

            if 'private_data_dir' in kwargs.keys():
                env['PRIVATE_DATA_DIR'] = kwargs['private_data_dir']
            passwords = {}
            for setting in Setting.objects.filter(key__contains='ssh_key'):
                set = Setting.objects.get(key=setting.key.replace('ssh_key', 'ssh_password'))
                passwords['credential_{}'.format(setting.key)] = decrypt_field(set, 'value')
            kwargs['passwords'] = passwords

            private_data = {'credentials': {}}
            for sets in Setting.objects.filter(key__contains='ssh_key'):
                # If we were sent SSH credentials, decrypt them and send them
                # back (they will be written to a temporary file).
                private_data['credentials'][sets] = decrypt_field(sets, 'value') or ''
            private_data_files = {'credentials': {}}
            if private_data is not None:
                listpaths = []
                for sets, data in private_data.get('credentials', {}).items():
                    # OpenSSH formatted keys must have a trailing newline to be
                    # accepted by ssh-add.
                    if 'OPENSSH PRIVATE KEY' in data and not data.endswith('\n'):
                        data += '\n'
                    # For credentials used with ssh-add, write to a named pipe which
                    # will be read then closed, instead of leaving the SSH key on disk.
                    if sets:
                        name = 'credential_{}'.format(sets.key)
                        path = os.path.join(kwargs['private_data_dir'], name)
                        run.open_fifo_write(path, data)
                        listpaths.append(path)
                if len(listpaths) > 1:
                    private_data_files['credentials']['ssh'] = listpaths
                elif len(listpaths) == 1:
                    private_data_files['credentials']['ssh'] = listpaths[0]

            # May have to serialize the value
            kwargs['private_data_files'] = private_data_files
            cwd = '/var/tmp/cyborgbackup'

            new_args = []
            new_args += ['ssh', '-Ao', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            new_args += ['{}@{}'.format(self.client_user, self.client.hostname)]
            new_args += ['\"echo \'####CYBMOD#####\';', ' '.join(args),
                         '; exitcode=\$?; echo \'####CYBMOD#####\'; exit \$exitcode\"']
            args = new_args

            # If there is an SSH key path defined, wrap args with ssh-agent.
            private_data_files = kwargs.get('private_data_files', {})
            if 'ssh' in private_data_files.get('credentials', {}):
                ssh_key_path = private_data_files['credentials']['ssh']
            else:
                ssh_key_path = ''
            if ssh_key_path:
                ssh_auth_sock = os.path.join(kwargs['private_data_dir'], 'ssh_auth.sock')
                args = run.wrap_args_with_ssh_agent(args, ssh_key_path, ssh_auth_sock)
            # args = cmd

            expect_passwords = {}
            d = {}

            for k, v in kwargs['passwords'].items():
                d[re.compile(r'Enter passphrase for .*' + k + r':\s*?$', re.M)] = k
                d[re.compile(r'Enter passphrase for .*' + k, re.M)] = k
            d[re.compile(r'Bad passphrase, try again for .*:\s*?$', re.M)] = ''

            for k, v in d.items():
                expect_passwords[k] = kwargs['passwords'].get(v, '') or ''

            if queryargs and 'password' in queryargs.keys():
                expect_passwords[re.compile(r'Enter password: \s*?$', re.M)] = queryargs['password']

            stdout_handle = io.StringIO()

            _kw = dict(
                expect_passwords=expect_passwords,
                job_timeout=120,
                idle_timeout=None,
                pexpect_timeout=getattr(settings, 'PEXPECT_TIMEOUT', 5),
            )
            status, rc = run.run_pexpect(
                args, cwd, env, stdout_handle, **_kw
            )
            stdout_handle.flush()
            output = stdout_handle.getvalue().split('\r\n')
            finalOutput = []
            start = False
            for line in output:
                if 'Enter password: ' in line:
                    line = line.replace('Enter password: ', '')
                if line == '####CYBMOD#####' and not start:
                    start = True
                if start and line != '####CYBMOD#####' and line != '':
                    finalOutput += [line]

            shutil.rmtree(kwargs['private_data_dir'])
        except Exception:
            if settings.DEBUG:
                logger.exception('Exception occurred while running task')
        finally:
            try:
                logger.info('finished running, producing  events.')
            except Exception:
                logger.exception('Error flushing stdout and saving event count.')
        return finalOutput, rc
