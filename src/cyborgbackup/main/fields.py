# Python
import copy
import json
import re
import six
import urllib

# Python
from urllib.parse import urlparse
from collections import OrderedDict

# Django
from django.core.validators import URLValidator
from django.utils.translation import ugettext_lazy as _

# Django REST Framework
from rest_framework.fields import CharField, IntegerField, ListField, NullBooleanField, DictField

from jinja2 import Environment, StrictUndefined
from jinja2.exceptions import UndefinedError

# Django
from django.core import exceptions as django_exceptions
from django.db import models
from django.db.models.fields.related_descriptors import ReverseOneToOneDescriptor

# jsonschema
from jsonschema import Draft4Validator, FormatChecker
import jsonschema.exceptions

# Django-JSONField
from jsonfield import JSONField as upstream_JSONField

# DRF
from rest_framework import serializers

# CyBorgBackup
from cyborgbackup.main.utils.filters import SmartFilter
from cyborgbackup.main.validators import validate_ssh_private_key
from cyborgbackup.main import utils


# Provide a (better) custom error message for enum jsonschema validation
def __enum_validate__(validator, enums, instance, schema):
    if instance not in enums:
        yield jsonschema.exceptions.ValidationError(
            _("'%s' is not one of ['%s']") % (instance, "', '".join(enums))
        )


Draft4Validator.VALIDATORS['enum'] = __enum_validate__


class CharField(CharField):

    def to_representation(self, value):
        if value is None:
            return None
        return super(CharField, self).to_representation(value)


class IntegerField(IntegerField):

    def get_value(self, dictionary):
        ret = super(IntegerField, self).get_value(dictionary)
        # Handle UI corner case
        if ret == '' and self.allow_null and not getattr(self, 'allow_blank', False):
            return None
        return ret


class StringListField(ListField):

    child = CharField()

    def to_representation(self, value):
        if value is None and self.allow_null:
            return None
        return super(StringListField, self).to_representation(value)


class StringListBooleanField(ListField):

    default_error_messages = {
        'type_error': _('Expected None, True, False, a string or list of strings but got {input_type} instead.'),
    }
    child = CharField()

    def to_representation(self, value):
        try:
            if isinstance(value, (list, tuple)):
                return super(StringListBooleanField, self).to_representation(value)
            elif value in NullBooleanField.TRUE_VALUES:
                return True
            elif value in NullBooleanField.FALSE_VALUES:
                return False
            elif value in NullBooleanField.NULL_VALUES:
                return None
            elif isinstance(value, basestring):
                return self.child.to_representation(value)
        except TypeError:
            pass

        self.fail('type_error', input_type=type(value))

    def to_internal_value(self, data):
        try:
            if isinstance(data, (list, tuple)):
                return super(StringListBooleanField, self).to_internal_value(data)
            elif data in NullBooleanField.TRUE_VALUES:
                return True
            elif data in NullBooleanField.FALSE_VALUES:
                return False
            elif data in NullBooleanField.NULL_VALUES:
                return None
            elif isinstance(data, basestring):
                return self.child.run_validation(data)
        except TypeError:
            pass
        self.fail('type_error', input_type=type(data))


class URLField(CharField):

    def __init__(self, **kwargs):
        schemes = kwargs.pop('schemes', None)
        self.allow_plain_hostname = kwargs.pop('allow_plain_hostname', False)
        super(URLField, self).__init__(**kwargs)
        validator_kwargs = dict(message=_('Enter a valid URL'))
        if schemes is not None:
            validator_kwargs['schemes'] = schemes
        self.validators.append(URLValidator(**validator_kwargs))

    def to_representation(self, value):
        if value is None:
            return ''
        return super(URLField, self).to_representation(value)

    def run_validators(self, value):
        if self.allow_plain_hostname:
            try:
                url_parts = urlparse.urlsplit(value)
                if url_parts.hostname and '.' not in url_parts.hostname:
                    netloc = '{}.local'.format(url_parts.hostname)
                    if url_parts.port:
                        netloc = '{}:{}'.format(netloc, url_parts.port)
                    if url_parts.username:
                        if url_parts.password:
                            netloc = '{}:{}@{}' % (url_parts.username, url_parts.password, netloc)
                        else:
                            netloc = '{}@{}' % (url_parts.username, netloc)
                    value = urlparse.urlunsplit([url_parts.scheme,
                                                 netloc,
                                                 url_parts.path,
                                                 url_parts.query,
                                                 url_parts.fragment])
            except Exception:
                raise  # If something fails here, just fall through and let the validators check it.
        super(URLField, self).run_validators(value)


class KeyValueField(DictField):
    child = CharField()
    default_error_messages = {
        'invalid_child': _('"{input}" is not a valid string.')
    }

    def to_internal_value(self, data):
        ret = super(KeyValueField, self).to_internal_value(data)
        for value in data.values():
            if not isinstance(value, six.string_types + six.integer_types + (float,)):
                if isinstance(value, OrderedDict):
                    value = dict(value)
                self.fail('invalid_child', input=value)
        return ret


class ListTuplesField(ListField):
    default_error_messages = {
        'type_error': _('Expected a list of tuples of max length 2 but got {input_type} instead.'),
    }

    def to_representation(self, value):
        if isinstance(value, (list, tuple)):
            return super(ListTuplesField, self).to_representation(value)
        else:
            self.fail('type_error', input_type=type(value))

    def to_internal_value(self, data):
        if isinstance(data, list):
            for x in data:
                if not isinstance(x, (list, tuple)) or len(x) > 2:
                    self.fail('type_error', input_type=type(x))

            return super(ListTuplesField, self).to_internal_value(data)
        else:
            self.fail('type_error', input_type=type(data))


class JSONField(upstream_JSONField):

    def db_type(self, connection):
        return 'text'

    def _get_val_from_obj(self, obj):
        return self.value_from_object(obj)

    def from_db_value(self, value, expression, connection, context):
        if value in {'', None} and not self.null:
            return {}
        if isinstance(value, six.string_types):
            return json.loads(value)
        return value

# Based on AutoOneToOneField from django-annoying:
# https://bitbucket.org/offline/django-annoying/src/a0de8b294db3/annoying/fields.py


class AutoSingleRelatedObjectDescriptor(ReverseOneToOneDescriptor):
    """Descriptor for access to the object from its related class."""

    def __get__(self, instance, instance_type=None):
        try:
            return super(AutoSingleRelatedObjectDescriptor,
                         self).__get__(instance, instance_type)
        except self.related.related_model.DoesNotExist:
            obj = self.related.related_model(**{self.related.field.name: instance})
            if self.related.field.rel.parent_link:
                raise NotImplementedError('not supported with polymorphic!')
                for f in instance._meta.local_fields:
                    setattr(obj, f.name, getattr(instance, f.name))
            obj.save()
            return obj


class AutoOneToOneField(models.OneToOneField):
    """OneToOneField that creates related object if it doesn't exist."""

    def contribute_to_related_class(self, cls, related):
        setattr(cls, related.get_accessor_name(),
                AutoSingleRelatedObjectDescriptor(related))


class SmartFilterField(models.TextField):
    def get_prep_value(self, value):
        # Change any false value to none.
        # https://docs.python.org/2/library/stdtypes.html#truth-value-testing
        if not value:
            return None
        value = urllib.unquote(value)
        try:
            SmartFilter().query_from_string(value)
        except RuntimeError as e:
            raise models.base.ValidationError(e)
        return super(SmartFilterField, self).get_prep_value(value)


class AskForField(models.BooleanField):
    """
    Denotes whether to prompt on launch for another field on the same template
    """
    def __init__(self, allows_field=None, **kwargs):
        super(AskForField, self).__init__(**kwargs)
        self._allows_field = allows_field

    @property
    def allows_field(self):
        if self._allows_field is None:
            try:
                return self.name[len('ask_'):-len('_on_launch')]
            except AttributeError:
                # self.name will be set by the model metaclass, not this field
                raise Exception('Corresponding allows_field cannot be accessed until model is initialized.')
        return self._allows_field
