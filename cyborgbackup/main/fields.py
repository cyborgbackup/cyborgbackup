# Python
import copy
import json
import re
import six
import urllib

# Python
import logging
from urllib.parse import urlparse
from collections import OrderedDict

# Django
from django.core.validators import URLValidator
from django.utils.translation import ugettext_lazy as _

# Django REST Framework
from rest_framework.fields import *  # noqa

from jinja2 import Environment, StrictUndefined
from jinja2.exceptions import UndefinedError

# Django
from django.core import exceptions as django_exceptions
from django.db.models.signals import (
    post_save,
    post_delete,
)
from django.db.models.signals import m2m_changed
from django.db import models
from django.db.models.fields.related_descriptors import (
    ReverseOneToOneDescriptor,
    ForwardManyToOneDescriptor,
    ManyToManyDescriptor,
    ReverseManyToOneDescriptor,
)
from django.utils.encoding import smart_text
from django.utils.translation import ugettext_lazy as _

# jsonschema
from jsonschema import Draft4Validator, FormatChecker
import jsonschema.exceptions

# Django-JSONField
from jsonfield import JSONField as upstream_JSONField
from jsonbfield.fields import JSONField as upstream_JSONBField

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
        # django_rest_frameworks' default CharField implementation casts `None`
        # to a string `"None"`:
        #
        # https://github.com/tomchristie/django-rest-framework/blob/cbad236f6d817d992873cd4df6527d46ab243ed1/rest_framework/fields.py#L761
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
                    value = urlparse.urlunsplit([url_parts.scheme, netloc, url_parts.path, url_parts.query, url_parts.fragment])
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


class JSONBField(upstream_JSONBField):
    def get_prep_lookup(self, lookup_type, value):
        if isinstance(value, six.string_types) and value == "null":
            return 'null'
        return super(JSONBField, self).get_prep_lookup(lookup_type, value)

    def get_db_prep_value(self, value, connection, prepared=False):
        if connection.vendor == 'sqlite':
            # sqlite (which we use for tests) does not support jsonb;
            return json.dumps(value)
        return super(JSONBField, self).get_db_prep_value(
            value, connection, prepared
        )

    def from_db_value(self, value, expression, connection, context):
        # Work around a bug in django-jsonfield
        # https://bitbucket.org/schinckel/django-jsonfield/issues/57/cannot-use-in-the-same-project-as-djangos
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


class JSONSchemaField(JSONBField):
    """
    A JSONB field that self-validates against a defined JSON schema
    (http://json-schema.org).  This base class is intended to be overwritten by
    defining `self.schema`.
    """

    format_checker = FormatChecker()

    # If an empty {} is provided, we still want to perform this schema
    # validation
    empty_values = (None, '')

    def get_default(self):
        return copy.deepcopy(super(JSONBField, self).get_default())

    def schema(self, model_instance):
        raise NotImplementedError()

    def validate(self, value, model_instance):
        super(JSONSchemaField, self).validate(value, model_instance)
        errors = []
        for error in Draft4Validator(
                self.schema(model_instance),
                format_checker=self.format_checker
        ).iter_errors(value):
            # strip Python unicode markers from jsonschema validation errors
            error.message = re.sub(r'\bu(\'|")', r'\1', error.message)

            if error.validator == 'pattern' and 'error' in error.schema:
                error.message = error.schema['error'] % error.instance
            errors.append(error)

        if errors:
            raise django_exceptions.ValidationError(
                [e.message for e in errors],
                code='invalid',
                params={'value': value},
            )

    def get_db_prep_value(self, value, connection, prepared=False):
        if connection.vendor == 'sqlite':
            # sqlite (which we use for tests) does not support jsonb;
            return json.dumps(value)
        return super(JSONSchemaField, self).get_db_prep_value(
            value, connection, prepared
        )

    def from_db_value(self, value, expression, connection, context):
        # Work around a bug in django-jsonfield
        # https://bitbucket.org/schinckel/django-jsonfield/issues/57/cannot-use-in-the-same-project-as-djangos
        if isinstance(value, six.string_types):
            return json.loads(value)
        return value


@JSONSchemaField.format_checker.checks('vault_id')
def format_vault_id(value):
    if '@' in value:
        raise jsonschema.exceptions.FormatError('@ is not an allowed character')
    return True


@JSONSchemaField.format_checker.checks('ssh_private_key')
def format_ssh_private_key(value):
    # Sanity check: GCE, in particular, provides JSON-encoded private
    # keys, which developers will be tempted to copy and paste rather
    # than JSON decode.
    #
    # These end in a unicode-encoded final character that gets double
    # escaped due to being in a Python 2 bytestring, and that causes
    # Python's key parsing to barf. Detect this issue and correct it.
    if not value or value == '$encrypted$':
        return True
    if r'\u003d' in value:
        value = value.replace(r'\u003d', '=')
    try:
        validate_ssh_private_key(value)
    except django_exceptions.ValidationError as e:
        raise jsonschema.exceptions.FormatError(e.message)
    return True


class CredentialInputField(JSONSchemaField):
    """
    Used to validate JSON for
    `awx.main.models.credential:Credential().inputs`.

    Input data for credentials is represented as a dictionary e.g.,
    {'api_token': 'abc123', 'api_secret': 'SECRET'}

    For the data to be valid, the keys of this dictionary should correspond
    with the field names (and datatypes) defined in the associated
    CredentialType e.g.,

    {
        'fields': [{
            'id': 'api_token',
            'label': 'API Token',
            'type': 'string'
        }, {
            'id': 'api_secret',
            'label': 'API Secret',
            'type': 'string'
        }]
    }
    """

    def schema(self, model_instance):
        # determine the defined fields for the associated credential type
        properties = {}
        for field in model_instance.credential_type.inputs.get('fields', []):
            field = field.copy()
            properties[field['id']] = field
            if field.get('choices', []):
                field['enum'] = field['choices'][:]
        return {
            'type': 'object',
            'properties': properties,
            'dependencies': model_instance.credential_type.inputs.get('dependencies', {}),
            'additionalProperties': False,
        }

    def validate(self, value, model_instance):
        # decrypt secret values so we can validate their contents (i.e.,
        # ssh_key_data format)

        if not isinstance(value, dict):
            return super(CredentialInputField, self).validate(value,
                                                              model_instance)

        # Backwards compatability: in prior versions, if you submit `null` for
        # a credential field value, it just considers the value an empty string
        for unset in [key for key, v in model_instance.inputs.items() if not v]:
            default_value = model_instance.credential_type.default_for_field(unset)
            if default_value is not None:
                model_instance.inputs[unset] = default_value

        decrypted_values = {}
        for k, v in value.items():
            if all([
                    k in model_instance.credential_type.secret_fields,
                    v != '$encrypted$',
                    model_instance.pk
            ]):
                if not isinstance(getattr(model_instance, k), six.string_types):
                    raise django_exceptions.ValidationError(
                        _('secret values must be of type string, not {}').format(type(v).__name__),
                        code='invalid',
                        params={'value': v},
                    )
                decrypted_values[k] = utils.decrypt_field(model_instance, k)
            else:
                decrypted_values[k] = v

        super(JSONSchemaField, self).validate(decrypted_values, model_instance)
        errors = {}
        for error in Draft4Validator(
                self.schema(model_instance),
                format_checker=self.format_checker
        ).iter_errors(decrypted_values):
            if error.validator == 'pattern' and 'error' in error.schema:
                error.message = error.schema['error'] % error.instance
            if error.validator == 'dependencies':
                # replace the default error messaging w/ a better i18n string
                # I wish there was a better way to determine the parameters of
                # this validation failure, but the exception jsonschema raises
                # doesn't include them as attributes (just a hard-coded error
                # string)
                match = re.search(
                    # 'foo' is a dependency of 'bar'
                    "'"         # apostrophe
                    "([^']+)"   # one or more non-apostrophes (first group)
                    "'[\w ]+'"  # one or more words/spaces
                    "([^']+)",  # second group
                    error.message,
                )
                if match:
                    label, extraneous = match.groups()
                    if error.schema['properties'].get(label):
                        label = error.schema['properties'][label]['label']
                    errors[extraneous] = [
                        _('cannot be set unless "%s" is set') % label
                    ]
                    continue
            if 'id' not in error.schema:
                # If the error is not for a specific field, it's specific to
                # `inputs` in general
                raise django_exceptions.ValidationError(
                    error.message,
                    code='invalid',
                    params={'value': value},
                )
            errors[error.schema['id']] = [error.message]

        inputs = model_instance.credential_type.inputs
        for field in inputs.get('required', []):
            if not value.get(field, None):
                errors[field] = [_('required for %s') % (
                    model_instance.credential_type.name
                )]

        # `ssh_key_unlock` requirements are very specific and can't be
        # represented without complicated JSON schema
        if (
                model_instance.credential_type.managed_by_cyborgbackup is True and
                'ssh_key_unlock' in model_instance.credential_type.defined_fields
        ):

            # in order to properly test the necessity of `ssh_key_unlock`, we
            # need to know the real value of `ssh_key_data`; for a payload like:
            # {
            #   'ssh_key_data': '$encrypted$',
            #   'ssh_key_unlock': 'do-you-need-me?',
            # }
            # ...we have to fetch the actual key value from the database
            if model_instance.pk and model_instance.ssh_key_data == '$encrypted$':
                model_instance.ssh_key_data = model_instance.__class__.objects.get(
                    pk=model_instance.pk
                ).ssh_key_data

            if model_instance.has_encrypted_ssh_key_data and not value.get('ssh_key_unlock'):
                errors['ssh_key_unlock'] = [_('must be set when SSH key is encrypted.')]
            if all([
                    model_instance.ssh_key_data,
                    value.get('ssh_key_unlock'),
                    not model_instance.has_encrypted_ssh_key_data
            ]):
                errors['ssh_key_unlock'] = [_('should not be set when SSH key is not encrypted.')]

        if errors:
            raise serializers.ValidationError({
                'inputs': errors
            })


class CredentialTypeInputField(JSONSchemaField):
    """
    Used to validate JSON for
    `awx.main.models.credential:CredentialType().inputs`.
    """

    def schema(self, model_instance):
        return {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'required': {
                    'type': 'array',
                    'items': {'type': 'string'}
                },
                'fields':  {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'type': {'enum': ['string', 'boolean']},
                            'format': {'enum': ['ssh_private_key']},
                            'choices': {
                                'type': 'array',
                                'minItems': 1,
                                'items': {'type': 'string'},
                                'uniqueItems': True
                            },
                            'id': {
                                'type': 'string',
                                'pattern': '^[a-zA-Z_]+[a-zA-Z0-9_]*$',
                                'error': '%s is an invalid variable name',
                            },
                            'label': {'type': 'string'},
                            'help_text': {'type': 'string'},
                            'multiline': {'type': 'boolean'},
                            'secret': {'type': 'boolean'},
                            'ask_at_runtime': {'type': 'boolean'},
                        },
                        'additionalProperties': False,
                        'required': ['id', 'label'],
                    }
                }
            }
        }

    def validate(self, value, model_instance):
        if isinstance(value, dict) and 'dependencies' in value and \
                not model_instance.managed_by_cyborgbackup:
            raise django_exceptions.ValidationError(
                _("'dependencies' is not supported for custom credentials."),
                code='invalid',
                params={'value': value},
            )

        super(CredentialTypeInputField, self).validate(
            value, model_instance
        )

        ids = {}
        for field in value.get('fields', []):
            id_ = field.get('id')
            if id_ == 'cyborgbackup':
                raise django_exceptions.ValidationError(
                    _('"cyborgbackup" is a reserved field name'),
                    code='invalid',
                    params={'value': value},
                )

            if id_ in ids:
                raise django_exceptions.ValidationError(
                    _('field IDs must be unique (%s)' % id_),
                    code='invalid',
                    params={'value': value},
                )
            ids[id_] = True

            if 'type' not in field:
                # If no type is specified, default to string
                field['type'] = 'string'

            for key in ('choices', 'multiline', 'format', 'secret',):
                if key in field and field['type'] != 'string':
                    raise django_exceptions.ValidationError(
                        _('%s not allowed for %s type (%s)' % (key, field['type'], field['id'])),
                        code='invalid',
                        params={'value': value},
                    )



class CredentialTypeInjectorField(JSONSchemaField):
    """
    Used to validate JSON for
    `cyborgbackup.main.models.credential:CredentialType().injectors`.
    """

    def schema(self, model_instance):
        return {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'file': {
                    'type': 'object',
                    'patternProperties': {
                        '^template(\.[a-zA-Z_]+[a-zA-Z0-9_]*)?$': {'type': 'string'},
                    },
                    'additionalProperties': False,
                },
                'env': {
                    'type': 'object',
                    'patternProperties': {
                        # http://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap08.html
                        # In the shell command language, a word consisting solely
                        # of underscores, digits, and alphabetics from the portable
                        # character set. The first character of a name is not
                        # a digit.
                        '^[a-zA-Z_]+[a-zA-Z0-9_]*$': {'type': 'string'},
                    },
                    'additionalProperties': False,
                },
                'extra_vars': {
                    'type': 'object',
                    'patternProperties': {
                        '^[a-zA-Z_]+[a-zA-Z0-9_]*$': {'type': 'string'},
                    },
                    'additionalProperties': False,
                },
            },
            'additionalProperties': False
        }

    def validate(self, value, model_instance):
        super(CredentialTypeInjectorField, self).validate(
            value, model_instance
        )

        # make sure the inputs are valid first
        try:
            CredentialTypeInputField().validate(model_instance.inputs, model_instance)
        except django_exceptions.ValidationError:
            # If `model_instance.inputs` itself is invalid, we can't make an
            # estimation as to whether our Jinja templates contain valid field
            # names; don't continue
            return

        # In addition to basic schema validation, search the injector fields
        # for template variables and make sure they match the fields defined in
        # the inputs
        valid_namespace = dict(
            (field, 'EXAMPLE')
            for field in model_instance.defined_fields
        )

        class MilkyprovisionNamespace:
            filename = None
        valid_namespace['cyborgbackup'] = MilkyprovisionNamespace()

        # ensure either single file or multi-file syntax is used (but not both)
        template_names = [x for x in value.get('file', {}).keys() if x.startswith('template')]
        if 'template' in template_names and len(template_names) > 1:
            raise django_exceptions.ValidationError(
                _('Must use multi-file syntax when injecting multiple files'),
                code='invalid',
                params={'value': value},
            )
        if 'template' not in template_names:
            valid_namespace['cyborgbackup'].filename = MilkyprovisionNamespace()
            for template_name in template_names:
                template_name = template_name.split('.')[1]
                setattr(valid_namespace['cyborgbackup'].filename, template_name, 'EXAMPLE')

        for type_, injector in value.items():
            for key, tmpl in injector.items():
                try:
                    Environment(
                        undefined=StrictUndefined
                    ).from_string(tmpl).render(valid_namespace)
                except UndefinedError as e:
                    raise django_exceptions.ValidationError(
                        _('%s uses an undefined field (%s)') % (key, e),
                        code='invalid',
                        params={'value': value},
                    )


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
