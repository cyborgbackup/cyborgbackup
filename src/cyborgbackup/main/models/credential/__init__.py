from collections import OrderedDict
import functools
import json
import logging
import operator
import os
import re
import stat
import tempfile

# Jinja2
from jinja2 import Template

# Django
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils.encoding import force_text

# CyBorgBackup
from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.fields import (CredentialInputField,
                                      CredentialTypeInputField,
                                      CredentialTypeInjectorField)
from cyborgbackup.main.utils.encryption import encrypt_field, decrypt_field
from cyborgbackup.main.validators import validate_ssh_private_key
from cyborgbackup.main.models.base import *

__all__ = ['Credential', 'CredentialType', 'V1Credential', 'build_safe_env']

logger = logging.getLogger('cyborgbackup.main.models.credential')

HIDDEN_PASSWORD = '**********'


def build_safe_env(env):
    '''
    Build environment dictionary, hiding potentially sensitive information
    such as passwords or keys.
    '''
    hidden_re = re.compile(r'API|TOKEN|KEY|SECRET|PASS', re.I)
    urlpass_re = re.compile(r'^.*?://[^:]+:(.*?)@.*?$')
    safe_env = dict(env)
    for k, v in safe_env.items():
        if hidden_re.search(k):
            safe_env[k] = HIDDEN_PASSWORD
        elif type(v) == str and urlpass_re.match(v):
            safe_env[k] = urlpass_re.sub(HIDDEN_PASSWORD, v)
    return safe_env


class V1Credential(object):

    #
    # API v1 backwards compat; as long as we continue to support the
    # /api/v1/credentials/ endpoint, we'll keep these definitions around.
    # The credential serializers are smart enough to detect the request
    # version and use *these* fields for constructing the serializer if the URL
    # starts with /api/v1/
    #
    PASSWORD_FIELDS = ('password', 'security_token', 'ssh_key_data',
                       'ssh_key_unlock', 'become_password',
                       'vault_password', 'secret', 'authorize_password')
    KIND_CHOICES = [
        ('ssh', 'Machine'),
        ('net', 'Network'),
        ('scm', 'Source Control'),
        ('aws', 'Amazon Web Services'),
        ('vmware', 'VMware vCenter'),
        ('satellite6', 'Red Hat Satellite 6'),
        ('cloudforms', 'Red Hat CloudForms'),
        ('gce', 'Google Compute Engine'),
        ('azure_rm', 'Microsoft Azure Resource Manager'),
        ('openstack', 'OpenStack'),
        ('rhv', 'Red Hat Virtualization'),
        ('insights', 'Insights'),
    ]
    FIELDS = {
        'kind': models.CharField(
            max_length=32,
            choices=[
                (kind[0], _(kind[1]))
                for kind in KIND_CHOICES
            ],
            default='ssh',
        ),
        'cloud': models.BooleanField(
            default=False,
            editable=False,
        ),
        'host': models.CharField(
            blank=True,
            default='',
            max_length=1024,
            verbose_name=_('Host'),
            help_text=_('The hostname or IP address to use.'),
        ),
        'username': models.CharField(
            blank=True,
            default='',
            max_length=1024,
            verbose_name=_('Username'),
            help_text=_('Username for this credential.'),
        ),
        'password': models.CharField(
            blank=True,
            default='',
            max_length=1024,
            verbose_name=_('Password'),
            help_text=_('Password for this credential (or "ASK" to prompt the '
                        'user for machine credentials).'),
        ),
        'security_token': models.CharField(
            blank=True,
            default='',
            max_length=1024,
            verbose_name=_('Security Token'),
            help_text=_('Security Token for this credential'),
        ),
        'project': models.CharField(
            blank=True,
            default='',
            max_length=100,
            verbose_name=_('Project'),
            help_text=_('The identifier for the project.'),
        ),
        'domain': models.CharField(
            blank=True,
            default='',
            max_length=100,
            verbose_name=_('Domain'),
            help_text=_('The identifier for the domain.'),
        ),
        'ssh_key_data': models.TextField(
            blank=True,
            default='',
            verbose_name=_('SSH private key'),
            help_text=_('RSA or DSA private key to be used instead of password.'),
        ),
        'ssh_key_unlock': models.CharField(
            max_length=1024,
            blank=True,
            default='',
            verbose_name=_('SSH key unlock'),
            help_text=_('Passphrase to unlock SSH private key if encrypted (or '
                        '"ASK" to prompt the user for machine credentials).'),
        ),
        'vault_password': models.CharField(
            max_length=1024,
            blank=True,
            default='',
            help_text=_('Vault password (or "ASK" to prompt the user).'),
        ),
        'authorize': models.BooleanField(
            default=False,
            help_text=_('Whether to use the authorize mechanism.'),
        ),
        'authorize_password': models.CharField(
            max_length=1024,
            blank=True,
            default='',
            help_text=_('Password used by the authorize mechanism.'),
        ),
        'client': models.CharField(
            max_length=128,
            blank=True,
            default='',
            help_text=_('Client Id or Application Id for the credential'),
        ),
        'secret': models.CharField(
            max_length=1024,
            blank=True,
            default='',
            help_text=_('Secret Token for this credential'),
        ),
    }



class Credential(PasswordFieldsModel, CommonModelNameNotUnique, models.Model):
    '''
    A credential contains information about how to talk to a remote resource
    Usually this is a SSH key location, and possibly an unlock password.
    If used with sudo, a sudo password should be set if required.
    '''

    class Meta:
        app_label = 'main'
        ordering = ('name',)
        unique_together = (('name', 'credential_type'))

    PASSWORD_FIELDS = ['inputs']

    credential_type = models.ForeignKey(
        'CredentialType',
        related_name='credentials',
        on_delete=models.CASCADE,
        null=False,
        help_text=_('Specify the type of credential you want to create. Refer '
                    'to the Ansible Tower documentation for details on each type.')
    )
    inputs = CredentialInputField(
        blank=True,
        default={},
        help_text=_('Enter inputs using either JSON or YAML syntax. Use the '
                    'radio button to toggle between the two. Refer to the '
                    'Ansible Tower documentation for example syntax.')
    )

    def __getattr__(self, item):
        if item != 'inputs':
            if item in V1Credential.FIELDS:
                return self.inputs.get(item, V1Credential.FIELDS[item].default)
            elif item in self.inputs:
                return self.inputs[item]
        raise AttributeError(item)

    def __setattr__(self, item, value):
        if item in V1Credential.FIELDS and item in self.credential_type.defined_fields:
            if value:
                self.inputs[item] = value
            elif item in self.inputs:
                del self.inputs[item]
            return
        super(Credential, self).__setattr__(item, value)

    @property
    def kind(self):
        type_ = self.credential_type
        if type_.kind != 'cloud':
            return type_.kind
        for field in V1Credential.KIND_CHOICES:
            kind, name = field
            if name == type_.name:
                return kind

    @property
    def cloud(self):
        return self.credential_type.kind == 'cloud'

    def get_absolute_url(self, request=None):
        return reverse('api:credential_detail', kwargs={'pk': self.pk}, request=request)

    @property
    def needs_ssh_password(self):
        return self.credential_type.kind == 'ssh' and self.password == 'ASK'

    @property
    def has_encrypted_ssh_key_data(self):
        if self.pk:
            ssh_key_data = decrypt_field(self, 'ssh_key_data')
        else:
            ssh_key_data = self.ssh_key_data
        try:
            pem_objects = validate_ssh_private_key(ssh_key_data)
            for pem_object in pem_objects:
                if pem_object.get('key_enc', False):
                    return True
        except ValidationError:
            pass
        return False

    @property
    def needs_ssh_key_unlock(self):
        if self.credential_type.kind == 'ssh' and self.ssh_key_unlock in ('ASK', ''):
            return self.has_encrypted_ssh_key_data
        return False

    @property
    def needs_become_password(self):
        return self.credential_type.kind == 'ssh' and self.become_password == 'ASK'

    @property
    def needs_vault_password(self):
        return self.credential_type.kind == 'vault' and self.vault_password == 'ASK'

    @property
    def passwords_needed(self):
        needed = []
        for field in ('ssh_password', 'become_password', 'ssh_key_unlock'):
            if getattr(self, 'needs_%s' % field):
                needed.append(field)
        if self.needs_vault_password:
            if self.inputs.get('vault_id'):
                needed.append('vault_password.{}'.format(self.inputs.get('vault_id')))
            else:
                needed.append('vault_password')
        return needed

    def _password_field_allows_ask(self, field):
        return field in self.credential_type.askable_fields

    def save(self, *args, **kwargs):
        self.PASSWORD_FIELDS = self.credential_type.secret_fields

        if self.pk:
            cred_before = Credential.objects.get(pk=self.pk)
            inputs_before = cred_before.inputs
            # Look up the currently persisted value so that we can replace
            # $encrypted$ with the actual DB-backed value
            for field in self.PASSWORD_FIELDS:
                if self.inputs.get(field) == '$encrypted$':
                    self.inputs[field] = inputs_before[field]

        super(Credential, self).save(*args, **kwargs)

    def encrypt_field(self, field, ask):
        encrypted = encrypt_field(self, field, ask=ask)
        if encrypted:
            self.inputs[field] = encrypted
        elif field in self.inputs:
            del self.inputs[field]

    def mark_field_for_save(self, update_fields, field):
        if field in self.credential_type.secret_fields:
            # If we've encrypted a v1 field, we actually want to persist
            # self.inputs
            field = 'inputs'
        super(Credential, self).mark_field_for_save(update_fields, field)

    def display_inputs(self):
        field_val = self.inputs.copy()
        for k, v in field_val.items():
            if force_text(v).startswith('$encrypted$'):
                field_val[k] = '$encrypted$'
        return field_val

    def unique_hash(self, display=False):
        '''
        Credential exclusivity is not defined solely by the related
        credential type (due to vault), so this produces a hash
        that can be used to evaluate exclusivity
        '''
        if display:
            type_alias = self.credential_type.name
        else:
            type_alias = self.credential_type_id
        if self.kind == 'vault' and self.inputs.get('vault_id', None):
            if display:
                fmt_str = '{} (id={})'
            else:
                fmt_str = '{}_{}'
            return fmt_str.format(type_alias, self.inputs.get('vault_id'))
        return str(type_alias)

    @staticmethod
    def unique_dict(cred_qs):
        ret = {}
        for cred in cred_qs:
            ret[cred.unique_hash()] = cred
        return ret


class CredentialType(CommonModelNameNotUnique):
    '''
    A reusable schema for a credential.

    Used to define a named credential type with fields (e.g., an API key) and
    output injectors (i.e., an environment variable that uses the API key).
    '''

    defaults = OrderedDict()

    ENV_BLACKLIST = set((
        'VIRTUAL_ENV', 'PATH', 'PYTHONPATH', 'PROOT_TMP_DIR', 'JOB_ID',
        'INVENTORY_ID', 'INVENTORY_SOURCE_ID', 'INVENTORY_UPDATE_ID',
        'AD_HOC_COMMAND_ID', 'REST_API_URL', 'REST_API_TOKEN', 'MAX_EVENT_RES',
        'CALLBACK_QUEUE', 'CALLBACK_CONNECTION', 'CACHE',
        'JOB_CALLBACK_DEBUG', 'INVENTORY_HOSTVARS', 'FACT_QUEUE',
    ))

    class Meta:
        app_label = 'main'
        ordering = ('kind', 'name')
        unique_together = (('name', 'kind'),)

    KIND_CHOICES = (
        ('ssh', _('Machine')),
        ('net', _('Network')),
        ('scm', _('Source Control')),
        ('cloud', _('Cloud')),
        ('insights', _('Insights')),
    )

    kind = models.CharField(
        max_length=32,
        choices=KIND_CHOICES
    )
    inputs = CredentialTypeInputField(
        blank=True,
        default={},
        help_text=_('Enter inputs using either JSON or YAML syntax. Use the '
                    'radio button to toggle between the two. Refer to the '
                    'Ansible Tower documentation for example syntax.')
    )
    injectors = CredentialTypeInjectorField(
        blank=True,
        default={},
        help_text=_('Enter injectors using either JSON or YAML syntax. Use the '
                    'radio button to toggle between the two. Refer to the '
                    'Ansible Tower documentation for example syntax.')
    )

    def get_absolute_url(self, request=None):
        return reverse('api:credential_type_detail', kwargs={'pk': self.pk}, request=request)

    @property
    def unique_by_kind(self):
        return self.kind != 'cloud'

    @property
    def defined_fields(self):
        return [field.get('id') for field in self.inputs.get('fields', [])]

    @property
    def secret_fields(self):
        return [
            field['id'] for field in self.inputs.get('fields', [])
            if field.get('secret', False) is True
        ]

    @property
    def askable_fields(self):
        return [
            field['id'] for field in self.inputs.get('fields', [])
            if field.get('ask_at_runtime', False) is True
        ]

    def default_for_field(self, field_id):
        for field in self.inputs.get('fields', []):
            if field['id'] == field_id:
                if 'choices' in field:
                    return field['choices'][0]
                return {'string': '', 'boolean': False}[field['type']]

    @classmethod
    def default(cls, f):
        func = functools.partial(f, cls)
        cls.defaults[f.__name__] = func
        return func

    @classmethod
    def setup_cyborgbackup_managed_defaults(cls, persisted=True):
        for default in cls.defaults.values():
            default_ = default()
            if persisted:
                if CredentialType.objects.filter(name=default_.name, kind=default_.kind).count():
                    continue
                logger.debug(_(
                    "adding %s credential type" % default_.name
                ))
                default_.save()

    @classmethod
    def from_v1_kind(cls, kind, data={}):
        match = None
        kind = kind or 'ssh'
        kind_choices = dict(V1Credential.KIND_CHOICES)
        requirements = {}
        if kind == 'ssh':
            if data.get('vault_password'):
                requirements['kind'] = 'vault'
            else:
                requirements['kind'] = 'ssh'
        elif kind in ('net', 'scm', 'insights'):
            requirements['kind'] = kind
        elif kind in kind_choices:
            requirements.update(dict(
                kind='cloud',
                name=kind_choices[kind]
            ))
        if requirements:
            requirements['managed_by_cyborgbackup'] = True
            match = cls.objects.filter(**requirements)[:1].get()
        return match


@CredentialType.default
def ssh(cls):
    return cls(
        kind='ssh',
        name='Machine',
        managed_by_cyborgbackup=True,
        inputs={
            'fields': [{
                'id': 'username',
                'label': 'Username',
                'type': 'string'
            }, {
                'id': 'password',
                'label': 'Password',
                'type': 'string',
                'secret': True,
                'ask_at_runtime': True
            }, {
                'id': 'ssh_key_data',
                'label': 'SSH Private Key',
                'type': 'string',
                'format': 'ssh_private_key',
                'secret': True,
                'multiline': True
            }, {
                'id': 'ssh_key_unlock',
                'label': 'Private Key Passphrase',
                'type': 'string',
                'secret': True,
                'ask_at_runtime': True
            }, {
                'id': 'become_method',
                'label': 'Privilege Escalation Method',
                'choices': map(operator.itemgetter(0),
                               V1Credential.FIELDS['become_method'].choices),
                'help_text': ('Specify a method for "become" operations. This is '
                              'equivalent to specifying the --become-method '
                              'Ansible parameter.')
            }, {
                'id': 'become_username',
                'label': 'Privilege Escalation Username',
                'type': 'string',
            }, {
                'id': 'become_password',
                'label': 'Privilege Escalation Password',
                'type': 'string',
                'secret': True,
                'ask_at_runtime': True
            }],
            'dependencies': {
                'ssh_key_unlock': ['ssh_key_data'],
            }
        }
    )


@CredentialType.default
def scm(cls):
    return cls(
        kind='scm',
        name='Source Control',
        managed_by_cyborgbackup=True,
        inputs={
            'fields': [{
                'id': 'username',
                'label': 'Username',
                'type': 'string'
            }, {
                'id': 'password',
                'label': 'Password',
                'type': 'string',
                'secret': True
            }, {
                'id': 'ssh_key_data',
                'label': 'SCM Private Key',
                'type': 'string',
                'format': 'ssh_private_key',
                'secret': True,
                'multiline': True
            }, {
                'id': 'ssh_key_unlock',
                'label': 'Private Key Passphrase',
                'type': 'string',
                'secret': True
            }],
            'dependencies': {
                'ssh_key_unlock': ['ssh_key_data'],
            }
        }
    )


@CredentialType.default
def net(cls):
    return cls(
        kind='net',
        name='Network',
        managed_by_cyborgbackup=True,
        inputs={
            'fields': [{
                'id': 'username',
                'label': 'Username',
                'type': 'string'
            }, {
                'id': 'password',
                'label': 'Password',
                'type': 'string',
                'secret': True,
            }, {
                'id': 'ssh_key_data',
                'label': 'SSH Private Key',
                'type': 'string',
                'format': 'ssh_private_key',
                'secret': True,
                'multiline': True
            }, {
                'id': 'ssh_key_unlock',
                'label': 'Private Key Passphrase',
                'type': 'string',
                'secret': True,
            }, {
                'id': 'authorize',
                'label': 'Authorize',
                'type': 'boolean',
            }, {
                'id': 'authorize_password',
                'label': 'Authorize Password',
                'type': 'string',
                'secret': True,
            }],
            'dependencies': {
                'ssh_key_unlock': ['ssh_key_data'],
                'authorize_password': ['authorize'],
            },
            'required': ['username'],
        }
    )
