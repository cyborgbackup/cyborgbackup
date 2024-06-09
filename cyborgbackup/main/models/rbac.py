# Python
import re
import threading

from django.contrib.auth.models import User  # noqa
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# CyBorgBackup
from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.models.base import *  # noqa

__all__ = [
    'Role',
    'get_roles_on_resource',
    'ROLE_SINGLETON_SYSTEM_ADMINISTRATOR',
    'ROLE_SINGLETON_SYSTEM_AUDITOR',
    'role_summary_fields_generator'
]

ROLE_SINGLETON_SYSTEM_ADMINISTRATOR = 'system_administrator'
ROLE_SINGLETON_SYSTEM_AUDITOR = 'system_auditor'

role_names = {
    'system_administrator': _('System Administrator'),
    'system_auditor': _('System Auditor'),
    'admin_role': _('Admin'),
    'client_admin_role': _('Client Admin'),
    'policy_admin_role': _('Policy Admin'),
    'schedules_admin_role': _('Schedules Admin'),
    'auditor_role': _('Auditor'),
    'execute_role': _('Execute'),
    'member_role': _('Member'),
    'read_role': _('Read'),
    'update_role': _('Update'),
    'use_role': _('Use'),
}

role_descriptions = {
    'system_administrator': _('Can manage all aspects of the system'),
    'system_auditor': _('Can view all settings on the system'),
    'admin_role': _('Can manage all aspects of the %s'),
    'client_admin_role': _('Can manage all clients of the %s'),
    'policy_admin_role': _('Can manage all policies of the %s'),
    'schedules_admin_role': _('Can manage all schedules of the %s'),
    'auditor_role': _('Can view all settings for the %s'),
    'execute_role': {
        'organization': _('May run any executable resources in the organization'),
        'default': _('May run the %s'),
    },
    'member_role': _('User is a member of the %s'),
    'read_role': _('May view settings for the %s'),
    'update_role': _('May update project or inventory or group using the configured source update system'),
    'use_role': _('Can use the %s in a job template'),
}

tls = threading.local()  # thread local storage


def check_singleton(func):
    """
    check_singleton is a decorator that checks if a user given
    to a `visible_roles` method is in either of our singleton roles (Admin, Auditor)
    and if so, returns their full list of roles without filtering.
    """

    def wrapper(*args, **kwargs):
        sys_admin = Role.singleton(ROLE_SINGLETON_SYSTEM_ADMINISTRATOR)
        sys_audit = Role.singleton(ROLE_SINGLETON_SYSTEM_AUDITOR)
        user = args[0]
        if user in sys_admin or user in sys_audit:
            if len(args) == 2:
                return args[1]
            return Role.objects.all()
        return func(*args, **kwargs)

    return wrapper


class Role(models.Model):
    """
    Role model
    """

    class Meta:
        app_label = 'main'
        verbose_name_plural = _('roles')
        db_table = 'main_rbac_roles'
        index_together = [
            ("content_type", "object_id")
        ]

    role_field = models.TextField(null=False)
    singleton_name = models.TextField(null=True, default=None, db_index=True, unique=True)
    parents = models.ManyToManyField('Role', related_name='children')
    implicit_parents = models.TextField(null=False, default='[]')
    members = models.ManyToManyField('auth.User', related_name='roles')
    content_type = models.ForeignKey(ContentType, null=True, default=None, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(null=True, default=None)
    content_object = GenericForeignKey('content_type', 'object_id')

    def __unicode__(self):
        if 'role_field' in self.__dict__:
            return u'%s-%s' % (self.name, self.pk)
        else:
            return u'%s-%s' % (self._meta.verbose_name, self.pk)

    def save(self, *args, **kwargs):
        super(Role, self).save(*args, **kwargs)

    def get_absolute_url(self, request=None):
        return reverse('api:role_detail', kwargs={'pk': self.pk}, request=request)

    def __contains__(self, accessor):
        if type(accessor) == User:
            return self.ancestors.filter(members=accessor).exists()
        elif accessor.__class__.__name__ == 'Team':
            return self.ancestors.filter(pk=accessor.member_role.id).exists()
        elif type(accessor) == Role:
            return self.ancestors.filter(pk=accessor).exists()
        else:
            accessor_type = ContentType.objects.get_for_model(accessor)
            roles = Role.objects.filter(content_type__pk=accessor_type.id,
                                        object_id=accessor.id)
            return self.ancestors.filter(pk__in=roles).exists()

    @property
    def name(self):
        global role_names
        return role_names[self.role_field]

    @property
    def description(self):
        global role_descriptions
        description = role_descriptions[self.role_field]
        content_type = self.content_type

        model_name = None
        if content_type:
            model = content_type.model_class()
            model_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', model.__name__).lower()

        value = description
        if type(description) == dict:
            value = description.get(model_name)
            if value is None:
                value = description.get('default')

        if '%s' in value and content_type:
            value = value % model_name

        return value

    @staticmethod
    def visible_roles(user):
        return Role.filter_visible_roles(user, Role.objects.all())

    @staticmethod
    def singleton(name):
        role, _ = Role.objects.get_or_create(singleton_name=name, role_field=name)
        return role

    def is_ancestor_of(self, role):
        return role.ancestors.filter(id=self.id).exists()

    def is_singleton(self):
        return self.singleton_name in [ROLE_SINGLETON_SYSTEM_ADMINISTRATOR, ROLE_SINGLETON_SYSTEM_AUDITOR]


def role_summary_fields_generator(content_object, role_field):
    global role_descriptions
    global role_names
    summary = {}
    description = role_descriptions[role_field]

    model_name = None
    content_type = ContentType.objects.get_for_model(content_object)
    if content_type:
        model = content_object.__class__
        model_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', model.__name__).lower()

    value = description
    if type(description) == dict:
        value = None
        if model_name:
            value = description.get(model_name)
        if value is None:
            value = description.get('default')

    if '%s' in value and model_name:
        value = value % model_name

    summary['description'] = value
    summary['name'] = role_names[role_field]
    summary['id'] = getattr(content_object, '{}_id'.format(role_field))
    return summary


def get_roles_on_resource(resource, accessor):
    """
    Returns a string list of the roles a accessor has for a given resource.
    An accessor can be either a User, Role, or an arbitrary resource that
    contains one or more Roles associated with it.
    """

    if type(accessor) == User:
        roles = accessor.roles.all()
    elif type(accessor) == Role:
        roles = [accessor]
    else:
        accessor_type = ContentType.objects.get_for_model(accessor)
        roles = Role.objects.filter(content_type__pk=accessor_type.id,
                                    object_id=accessor.id)

    return [
        role_field for role_field in
        RoleAncestorEntry.objects.filter(
            ancestor__in=roles,
            content_type_id=ContentType.objects.get_for_model(resource).id,
            object_id=resource.id
        ).values_list('role_field', flat=True).distinct()
    ]
