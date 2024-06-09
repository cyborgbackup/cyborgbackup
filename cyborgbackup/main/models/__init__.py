# Django
from auditlog.registry import auditlog
from django.conf import settings  # noqa
# Monkeypatch Django serializer to ignore django-taggit fields (which break
# the dumpdata command; see https://github.com/alex/django-taggit/issues/155).
from django.core.serializers.python import Serializer as _PythonSerializer

from cyborgbackup.main.models.activity_streams import ActivityStream
# CyBorgBackup
from cyborgbackup.main.models.base import *  # noqa
# CyBorgBackup
from cyborgbackup.main.models.base import *  # noqa
from cyborgbackup.main.models.catalogs import Catalog
from cyborgbackup.main.models.catalogs import Catalog
from cyborgbackup.main.models.channels import ChannelGroup
from cyborgbackup.main.models.channels import ChannelGroup
from cyborgbackup.main.models.clients import Client
from cyborgbackup.main.models.clients import Client
from cyborgbackup.main.models.events import JobEvent
from cyborgbackup.main.models.events import JobEvent
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.models.policies import Policy
from cyborgbackup.main.models.policies import Policy
from cyborgbackup.main.models.repositories import Repository
from cyborgbackup.main.models.repositories import Repository
from cyborgbackup.main.models.schedules import Schedule
from cyborgbackup.main.models.schedules import Schedule
from cyborgbackup.main.models.users import User
from cyborgbackup.main.models.users import User

_original_handle_m2m_field = _PythonSerializer.handle_m2m_field


def _new_handle_m2m_field(self, obj, field):
    try:
        field.rel.through._meta
    except AttributeError:
        return
    return _original_handle_m2m_field(self, obj, field)


_PythonSerializer.handle_m2m_field = _new_handle_m2m_field

# Add custom methods to User model for permissions checks.
from django.contrib.auth.models import User  # noqa


@property
def user_is_system_auditor(user):
    if not hasattr(user, '_is_system_auditor'):
        if user.pk:
            user._is_system_auditor = user.roles.filter(
                singleton_name='system_auditor', role_field='system_auditor').exists()
        else:
            # Odd case where user is unsaved, this should never be relied on
            return False
    return user._is_system_auditor


auditlog.register(Client)
auditlog.register(User)
auditlog.register(Repository)
auditlog.register(Schedule)
auditlog.register(Policy)
# prevent API filtering on certain Django-supplied sensitive fields
prevent_search(User._meta.get_field('password'))
