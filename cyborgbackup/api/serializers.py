# Python
import copy
import json
import logging
import re
import six
import urllib
from collections import OrderedDict
from datetime import timedelta

# Django
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import force_text
from django.utils.text import capfirst
from django.utils.timezone import now
from django.utils.functional import cached_property

# Django REST Framework
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework import fields
from rest_framework import serializers
from rest_framework import validators
from rest_framework.utils.serializer_helpers import ReturnList

# Django-Polymorphic
from polymorphic.models import PolymorphicModel

# cyborgbackup
from cyborgbackup.main.constants import ANSI_SGR_PATTERN
from cyborgbackup.main.models import * # noqa
from cyborgbackup.main.models.credential import *
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.models.users import User
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.constants import ACTIVE_STATES
from cyborgbackup.main.utils.common import (
    get_type_for_model, get_model_for_type, timestamp_apiformat,
    camelcase_to_underscore, getattrd, parse_yaml_or_json,
    has_model_field_prefetched, prefetch_page_capabilities)
from cyborgbackup.main.utils.encryption import encrypt_dict
from cyborgbackup.main.utils.filters import SmartFilter
from cyborgbackup.main.utils.string import REPLACE_STR
from cyborgbackup.main.validators import vars_validate_or_raise
from cyborgbackup.api.versioning import reverse, get_request_version
from cyborgbackup.api.fields import BooleanNullField, CharNullField, ChoiceNullField, VerbatimField

logger = logging.getLogger('cyborgbackup.api.serializers')

DEPRECATED = 'This resource has been deprecated and will be removed in a future release'

# Fields that should be summarized regardless of object type.
DEFAULT_SUMMARY_FIELDS = ('id', 'name', 'created_by', 'modified_by')#, 'type')


# Keys are fields (foreign keys) where, if found on an instance, summary info
# should be added to the serialized data.  Values are a tuple of field names on
# the related object to include in the summary data (if the field is present on
# the related object).
SUMMARIZABLE_FK_FIELDS = {
    'user': ('id', 'username', 'first_name', 'last_name'),
    'application': ('id', 'name', 'client_id'),
    'job': DEFAULT_SUMMARY_FIELDS + ('status', 'failed', 'elapsed'),
    'policy': ('id', 'name', 'policy_type'),
    'client': ('id', 'hostname'),
    'repository': ('id', 'name', 'path'),
    'schedule': ('id', 'name', 'crontab')
}


def reverse_gfk(content_object, request):
    '''
    Computes a reverse for a GenericForeignKey field.

    Returns a dictionary of the form
        { '<type>': reverse(<type detail>) }
    for example
        { 'organization': '/api/v1/organizations/1/' }
    '''
    if content_object is None or not hasattr(content_object, 'get_absolute_url'):
        return {}

    return {
        camelcase_to_underscore(content_object.__class__.__name__): content_object.get_absolute_url(request=request)
    }


class DynamicFieldsSerializerMixin(object):
    """
    A serializer mixin that takes an additional `fields` argument that controls
    which fields should be displayed.
    """

    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        fields = kwargs.pop('fields', None)

        # Instantiate the superclass normally
        super(DynamicFieldsSerializerMixin, self).__init__(*args, **kwargs)

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields.keys())
            for field_name in existing - allowed:
                self.fields.pop(field_name)


class BaseSerializerMetaclass(serializers.SerializerMetaclass):
    '''
    Custom metaclass to enable attribute inheritance from Meta objects on
    serializer base classes.

    Also allows for inheriting or updating field lists from base class(es):

        class Meta:

            # Inherit all fields from base class.
            fields = ('*',)

            # Inherit all fields from base class and add 'foo'.
            fields = ('*', 'foo')

            # Inherit all fields from base class except 'bar'.
            fields = ('*', '-bar')

            # Define fields as 'foo' and 'bar'; ignore base class fields.
            fields = ('foo', 'bar')

            # Extra field kwargs dicts are also merged from base classes.
            extra_kwargs = {
                'foo': {'required': True},
                'bar': {'read_only': True},
            }

            # If a subclass were to define extra_kwargs as:
            extra_kwargs = {
                'foo': {'required': False, 'default': ''},
                'bar': {'label': 'New Label for Bar'},
            }

            # The resulting value of extra_kwargs would be:
            extra_kwargs = {
                'foo': {'required': False, 'default': ''},
                'bar': {'read_only': True, 'label': 'New Label for Bar'},
            }

            # Extra field kwargs cannot be removed in subclasses, only replaced.

    '''

    @staticmethod
    def _is_list_of_strings(x):
        return isinstance(x, (list, tuple)) and all([isinstance(y, str) for y in x])

    @staticmethod
    def _is_extra_kwargs(x):
        return isinstance(x, dict) and all([isinstance(k, str) and isinstance(v, dict) for k, v in x.items()])

    @classmethod
    def _update_meta(cls, base, meta, other=None):
        for attr in dir(other):
            if attr.startswith('_'):
                continue
            val = getattr(other, attr)
            meta_val = getattr(meta, attr, None)
            # Special handling for lists/tuples of strings (field names).
            if cls._is_list_of_strings(val) and cls._is_list_of_strings(meta_val or []):
                meta_val = meta_val or []
                new_vals = []
                except_vals = []
                if base: # Merge values from all bases.
                    new_vals.extend([x for x in meta_val])
                for v in val:
                    if not base and v == '*': # Inherit all values from previous base(es).
                        new_vals.extend([x for x in meta_val])
                    elif not base and v.startswith('-'): # Except these values.
                        except_vals.append(v[1:])
                    else:
                        new_vals.append(v)
                val = []
                for v in new_vals:
                    if v not in except_vals and v not in val:
                        val.append(v)
                val = tuple(val)
            # Merge extra_kwargs dicts from base classes.
            elif cls._is_extra_kwargs(val) and cls._is_extra_kwargs(meta_val or {}):
                meta_val = meta_val or {}
                new_val = {}
                if base:
                    for k, v in meta_val.items():
                        new_val[k] = copy.deepcopy(v)
                for k, v in val.items():
                    new_val.setdefault(k, {}).update(copy.deepcopy(v))
                val = new_val
            # Any other values are copied in case they are mutable objects.
            else:
                val = copy.deepcopy(val)
            setattr(meta, attr, val)

    def __new__(cls, name, bases, attrs):
        meta = type('Meta', (object,), {})
        for base in bases[::-1]:
            cls._update_meta(base, meta, getattr(base, 'Meta', None))
        cls._update_meta(None, meta, attrs.get('Meta', meta))
        attrs['Meta'] = meta
        return super(BaseSerializerMetaclass, cls).__new__(cls, name, bases, attrs)


class BaseSerializer(serializers.ModelSerializer, metaclass=BaseSerializerMetaclass):

    class Meta:
        ordering = ('id',)
        fields = ('id', 'type', 'url', 'related', 'summary_fields', 'created',
                  'modified', 'name', 'created_by', 'modified_by')
        summary_fields = ()
        summarizable_fields = ()

    # add the URL and related resources
    type = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    related = serializers.SerializerMethodField('_get_related')
    summary_fields = serializers.SerializerMethodField('_get_summary_fields')

    # make certain fields read only
    created = serializers.SerializerMethodField()
    modified = serializers.SerializerMethodField()

    @property
    def version(self):
        """
        The request version component of the URL as an integer i.e., 1 or 2
        """
        return get_request_version(self.context.get('request'))

    def get_type(self, obj):
        return get_type_for_model(self.Meta.model)

    def get_types(self):
        return [self.get_type(None)]

    def get_type_choices(self):
        type_name_map = {
            'job': 'Job',
            'image': 'Image',
            'client': 'Client',
            'schedule': 'Schedule',
            'repository': 'Repository'
        }
        choices = []
        for t in self.get_types():
            name = type_name_map.get(t, force_text(get_model_for_type(t)._meta.verbose_name).title())
            choices.append((t, name))
        return choices

    def get_url(self, obj):
        if isinstance(obj, User):
            return self.reverse('api:user_detail', kwargs={'pk': obj.pk})
        elif obj is None or not hasattr(obj, 'get_absolute_url'):
            return ''
        else:
            return obj.get_absolute_url(request=self.context.get('request'))

    def filter_field_metadata(self, fields, method):
        """
        Filter field metadata based on the request method.
        This it intended to be extended by subclasses.
        """
        return fields

    def _get_related(self, obj):
        return {} if obj is None else self.get_related(obj)

    def _generate_named_url(self, url_path, obj, node):
        url_units = url_path.split('/')
        named_url = node.generate_named_url(obj)
        url_units[4] = named_url
        return '/'.join(url_units)

    def get_related(self, obj):
        res = OrderedDict()
        view = self.context.get('view', None)
        if getattr(obj, 'created_by', None):
            res['created_by'] = self.reverse('api:user_detail', kwargs={'pk': obj.created_by.pk})
        if getattr(obj, 'modified_by', None):
            res['modified_by'] = self.reverse('api:user_detail', kwargs={'pk': obj.modified_by.pk})
        return res

    def _get_summary_fields(self, obj):
        return {} if obj is None else self.get_summary_fields(obj)

    def get_summary_fields(self, obj):
        # Return values for certain fields on related objects, to simplify
        # displaying lists of items without additional API requests.
        summary_fields = OrderedDict()
        for fk, related_fields in SUMMARIZABLE_FK_FIELDS.items():
            try:
                fkval = getattr(obj, fk, None)
                if fkval is None:
                    continue
                if fkval == obj:
                    continue
                summary_fields[fk] = OrderedDict()
                for field in related_fields:
                    if (
                            self.version < 2 and field == 'credential_type_id' and
                            fk in ['credential', 'vault_credential']):
                        continue

                    fval = getattr(fkval, field, None)

                    if fval is None and field == 'type':
                        if isinstance(fkval, PolymorphicModel):
                            fkval = fkval.get_real_instance()
                        fval = get_type_for_model(fkval)
                    if fval is not None:
                        summary_fields[fk][field] = fval
            # Can be raised by the reverse accessor for a OneToOneField.
            except ObjectDoesNotExist:
                pass
        if getattr(obj, 'created_by', None):
            summary_fields['created_by'] = OrderedDict()
            for field in SUMMARIZABLE_FK_FIELDS['user']:
                summary_fields['created_by'][field] = getattr(obj.created_by, field)
        if getattr(obj, 'modified_by', None):
            summary_fields['modified_by'] = OrderedDict()
            for field in SUMMARIZABLE_FK_FIELDS['user']:
                summary_fields['modified_by'][field] = getattr(obj.modified_by, field)


        return summary_fields

    def _obj_capability_dict(self, obj):
        """
        Returns the user_capabilities dictionary for a single item
        If inside of a list view, it runs the prefetching algorithm for
        the entire current page, saves it into context
        """
        view = self.context.get('view', None)
        parent_obj = None
        if view and hasattr(view, 'parent_model') and hasattr(view, 'get_parent_object'):
            parent_obj = view.get_parent_object()
        if view and view.request and view.request.user:
            capabilities_cache = {}
            # if serializer has parent, it is ListView, apply page capabilities prefetch
            if self.parent and hasattr(self, 'capabilities_prefetch') and self.capabilities_prefetch:
                qs = self.parent.instance
                if 'capability_map' not in self.context:
                    model = self.Meta.model
                    prefetch_list = self.capabilities_prefetch
                    self.context['capability_map'] = prefetch_page_capabilities(
                        model, qs, prefetch_list, view.request.user
                    )
                if obj.id in self.context['capability_map']:
                    capabilities_cache = self.context['capability_map'][obj.id]
            return get_user_capabilities(
                view.request.user, obj, method_list=self.show_capabilities, parent_obj=parent_obj,
                capabilities_cache=capabilities_cache
            )
        else:
            # Contextual information to produce user_capabilities doesn't exist
            return {}

    def get_created(self, obj):
        if obj is None:
            return None
        elif isinstance(obj, User):
            return obj.date_joined
        elif hasattr(obj, 'created'):
            return obj.created
        return None

    def get_modified(self, obj):
        if obj is None:
            return None
        elif isinstance(obj, User):
            return obj.last_login # Not actually exposed for User.
        elif hasattr(obj, 'modified'):
            return obj.modified
        return None

    def get_extra_kwargs(self):
        extra_kwargs = super(BaseSerializer, self).get_extra_kwargs()
        if self.instance:
            read_only_on_update_fields = getattr(self.Meta, 'read_only_on_update_fields', tuple())
            for field_name in read_only_on_update_fields:
                kwargs = extra_kwargs.get(field_name, {})
                kwargs['read_only'] = True
                extra_kwargs[field_name] = kwargs
        return extra_kwargs

    def build_standard_field(self, field_name, model_field):
        # DRF 3.3 serializers.py::build_standard_field() -> utils/field_mapping.py::get_field_kwargs() short circuits
        # when a Model's editable field is set to False. The short circuit skips choice rendering.
        #
        # This logic is to force rendering choice's on an uneditable field.
        # Note: Consider expanding this rendering for more than just choices fields
        # Note: This logic works in conjuction with
        if hasattr(model_field, 'choices') and model_field.choices:
            was_editable = model_field.editable
            model_field.editable = True

        field_class, field_kwargs = super(BaseSerializer, self).build_standard_field(field_name, model_field)
        if hasattr(model_field, 'choices') and model_field.choices:
            model_field.editable = was_editable
            if was_editable is False:
                field_kwargs['read_only'] = True

        # Pass model field default onto the serializer field if field is not read-only.
        if model_field.has_default() and not field_kwargs.get('read_only', False):
            field_kwargs['default'] = field_kwargs['initial'] = model_field.get_default()

        # Enforce minimum value of 0 for PositiveIntegerFields.
        if isinstance(model_field, (models.PositiveIntegerField, models.PositiveSmallIntegerField)) and 'choices' not in field_kwargs:
            field_kwargs['min_value'] = 0

        # Use custom boolean field that allows null and empty string as False values.
        if isinstance(model_field, models.BooleanField) and not field_kwargs.get('read_only', False):
            field_class = BooleanNullField

        # Use custom char or choice field that coerces null to an empty string.
        if isinstance(model_field, (models.CharField, models.TextField)) and not field_kwargs.get('read_only', False):
            if 'choices' in field_kwargs:
                field_class = ChoiceNullField
            else:
                field_class = CharNullField

        # Update the message used for the unique validator to use capitalized
        # verbose name; keeps unique message the same as with DRF 2.x.
        opts = self.Meta.model._meta.concrete_model._meta
        for validator in field_kwargs.get('validators', []):
            if isinstance(validator, validators.UniqueValidator):
                unique_error_message = model_field.error_messages.get('unique', None)
                if unique_error_message:
                    unique_error_message = unique_error_message % {
                        'model_name': capfirst(opts.verbose_name),
                        'field_label': capfirst(model_field.verbose_name),
                    }
                    validator.message = unique_error_message

        return field_class, field_kwargs

    def build_relational_field(self, field_name, relation_info):
        field_class, field_kwargs = super(BaseSerializer, self).build_relational_field(field_name, relation_info)
        # Don't include choices for foreign key fields.
        field_kwargs.pop('choices', None)
        return field_class, field_kwargs

    def get_unique_together_validators(self):
        # Allow the model's full_clean method to handle the unique together validation.
        return []

    def run_validation(self, data=fields.empty):
        try:
            return super(BaseSerializer, self).run_validation(data)
        except ValidationError as exc:
            # Avoid bug? in DRF if exc.detail happens to be a list instead of a dict.
            raise ValidationError(detail=serializers.as_serializer_error(exc))

    def get_validation_exclusions(self, obj=None):
        # Borrowed from DRF 2.x - return model fields that should be excluded
        # from model validation.
        cls = self.Meta.model
        opts = cls._meta.concrete_model._meta
        exclusions = [field.name for field in opts.fields]
        for field_name, field in self.fields.items():
            field_name = field.source or field_name
            if field_name not in exclusions:
                continue
            if field.read_only:
                continue
            if isinstance(field, serializers.Serializer):
                continue
            exclusions.remove(field_name)
        # The clean_ methods cannot be ran on many-to-many models
        exclusions.extend([field.name for field in opts.many_to_many])
        return exclusions

    def validate(self, attrs):
        attrs = super(BaseSerializer, self).validate(attrs)
        try:
            # Create/update a model instance and run it's full_clean() method to
            # do any validation implemented on the model class.
            exclusions = self.get_validation_exclusions(self.instance)
            obj = self.instance or self.Meta.model()
            for k, v in attrs.items():
                if k not in exclusions:
                    setattr(obj, k, v)
            obj.full_clean(exclude=exclusions)
            # full_clean may modify values on the instance; copy those changes
            # back to attrs so they are saved.
            for k in attrs.keys():
                if k not in exclusions:
                    attrs[k] = getattr(obj, k)
        except DjangoValidationError as exc:
            # DjangoValidationError may contain a list or dict; normalize into a
            # dict where the keys are the field name and the values are a list
            # of error messages, then raise as a DRF ValidationError.  DRF would
            # normally convert any DjangoValidationError to a non-field specific
            # error message; here we preserve field-specific errors raised from
            # the model's full_clean method.
            d = exc.update_error_dict({})
            for k, v in d.items():
                v = v if isinstance(v, list) else [v]
                v2 = []
                for e in v:
                    if isinstance(e, DjangoValidationError):
                        v2.extend(list(e))
                    elif isinstance(e, list):
                        v2.extend(e)
                    else:
                        v2.append(e)
                d[k] = map(force_text, v2)
            raise ValidationError(d)
        return attrs

    def reverse(self, *args, **kwargs):
        kwargs['request'] = self.context.get('request')
        return reverse(*args, **kwargs)

    @property
    def is_detail_view(self):
        if 'view' in self.context:
            if 'pk' in self.context['view'].kwargs:
                return True
        return False


class EmptySerializer(serializers.Serializer):
    pass


class BaseFactSerializer(BaseSerializer):

    __metaclass__ = BaseSerializerMetaclass

    def get_fields(self):
        ret = super(BaseFactSerializer, self).get_fields()
        if 'module' in ret:
            modules = Fact.objects.all().values_list('module', flat=True).distinct()
            choices = [(o, o.title()) for o in modules]
            ret['module'] = serializers.ChoiceField(choices=choices, read_only=True, required=False)
        return ret

class UserSerializer(BaseSerializer):

    password = serializers.CharField(required=False, default='', write_only=True,
                                     help_text=_('Write-only field used to change the password.'))
    show_capabilities = ['edit', 'delete']

    class Meta:
        model = User
        fields = ('*', '-name', '-description', '-modified',
                  '-username', 'first_name', 'last_name',
                  'email', 'is_superuser', 'password', '-created_by', '-modified_by')

    def to_representation(self, obj):
        ret = super(UserSerializer, self).to_representation(obj)
        ret.pop('password', None)
        return ret

    def get_validation_exclusions(self, obj=None):
        ret = super(UserSerializer, self).get_validation_exclusions(obj)
        ret.append('password')
        return ret

    def validate_password(self, value):
        if not self.instance and value in (None, ''):
            raise serializers.ValidationError(_('Password required for new User.'))
        return value

    def _update_password(self, obj, new_password):
        # For now we're not raising an error, just not saving password for
        # users managed by LDAP who already have an unusable password set.
        if new_password:
            obj.set_password(new_password)
            obj.save(update_fields=['password'])
            #UserSessionMembership.clear_session_for_user(obj)
        elif not obj.password:
            obj.set_unusable_password()
            obj.save(update_fields=['password'])

    def create(self, validated_data):
        new_password = validated_data.pop('password', None)
        obj = super(UserSerializer, self).create(validated_data)
        self._update_password(obj, new_password)
        return obj

    def update(self, obj, validated_data):
        new_password = validated_data.pop('password', None)
        obj = super(UserSerializer, self).update(obj, validated_data)
        self._update_password(obj, new_password)
        return obj


class BaseSerializerWithVariables(BaseSerializer):

    def validate_variables(self, value):
        return vars_validate_or_raise(value)


class CredentialTypeSerializer(BaseSerializer):
    show_capabilities = ['edit', 'delete']
    managed_by_cyborgbackup = serializers.ReadOnlyField()

    class Meta:
        model = CredentialType
        fields = ('*', 'kind', 'name', 'inputs',
                  'injectors')

    def validate(self, attrs):
        if self.instance and self.instance.credentials.exists():
            if 'inputs' in attrs and attrs['inputs'] != self.instance.inputs:
                raise PermissionDenied(
                    detail=_("Modifications to inputs are not allowed for credential types that are in use")
                )
        ret = super(CredentialTypeSerializer, self).validate(attrs)

        if 'kind' in attrs and attrs['kind'] not in ('cloud', 'net'):
            raise serializers.ValidationError({
                "kind": _("Must be 'cloud' or 'net', not %s") % attrs['kind']
            })

        fields = attrs.get('inputs', {}).get('fields', [])
        for field in fields:
            if field.get('ask_at_runtime', False):
                raise serializers.ValidationError({"inputs": _("'ask_at_runtime' is not supported for custom credentials.")})

        return ret

    def get_related(self, obj):
        res = super(CredentialTypeSerializer, self).get_related(obj)
        res['credentials'] = self.reverse(
            'api:credential_type_credential_list',
            kwargs={'pk': obj.pk}
        )
        res['activity_stream'] = self.reverse(
            'api:credential_type_activity_stream_list',
            kwargs={'pk': obj.pk}
        )
        return res

    def to_representation(self, data):
        value = super(CredentialTypeSerializer, self).to_representation(data)

        # translate labels and help_text for credential fields "managed by cyborgbackup"
        if value.get('managed_by_cyborgbackup'):
            for field in value.get('inputs', {}).get('fields', []):
                field['label'] = _(field['label'])
                if 'help_text' in field:
                    field['help_text'] = _(field['help_text'])
        return value

    def filter_field_metadata(self, fields, method):
        # API-created/modified CredentialType kinds are limited to
        # `cloud` and `net`
        if method in ('PUT', 'POST'):
            fields['kind']['choices'] = filter(
                lambda choice: choice[0] in ('cloud', 'net'),
                fields['kind']['choices']
            )
        return fields


@six.add_metaclass(BaseSerializerMetaclass)
class V1CredentialFields(BaseSerializer):

    class Meta:
        model = Credential
        fields = ('*', 'kind', 'cloud', 'host', 'username',
                  'password', 'security_token', 'project', 'domain',
                  'ssh_key_data', 'ssh_key_unlock', 'become_method',
                  'become_username', 'become_password', 'vault_password',
                  'subscription', 'tenant', 'secret', 'client', 'authorize',
                  'authorize_password')

    def build_field(self, field_name, info, model_class, nested_depth):
        if field_name in V1Credential.FIELDS:
            return self.build_standard_field(field_name,
                                             V1Credential.FIELDS[field_name])
        return super(V1CredentialFields, self).build_field(field_name, info, model_class, nested_depth)


@six.add_metaclass(BaseSerializerMetaclass)
class V2CredentialFields(BaseSerializer):

    class Meta:
        model = Credential
        fields = ('*', 'credential_type', 'inputs')


class CredentialSerializer(BaseSerializer):
    show_capabilities = ['edit', 'delete', 'copy']
    capabilities_prefetch = ['admin', 'use']

    class Meta:
        model = Credential
        fields = ('*', 'organization')

    def get_fields(self):
        fields = super(CredentialSerializer, self).get_fields()
        fields.update(V1CredentialFields().get_fields())
        return fields

    def to_representation(self, data):
        value = super(CredentialSerializer, self).to_representation(data)

        if value.get('kind') == 'vault':
            value['kind'] = 'ssh'
        for field in V1Credential.PASSWORD_FIELDS:
            if field in value and force_text(value[field]).startswith('$encrypted$'):
                value[field] = '$encrypted$'

        if 'inputs' in value:
            value['inputs'] = data.display_inputs()
        return value

    def get_related(self, obj):
        res = super(CredentialSerializer, self).get_related(obj)

        if obj.organization:
            res['organization'] = self.reverse('api:organization_detail', kwargs={'pk': obj.organization.pk})

        res.update(dict(
            activity_stream=self.reverse('api:credential_activity_stream_list', kwargs={'pk': obj.pk}),
            access_list=self.reverse('api:credential_access_list', kwargs={'pk': obj.pk}),
            object_roles=self.reverse('api:credential_object_roles_list', kwargs={'pk': obj.pk}),
            owner_users=self.reverse('api:credential_owner_users_list', kwargs={'pk': obj.pk}),
            owner_teams=self.reverse('api:credential_owner_teams_list', kwargs={'pk': obj.pk}),
            copy=self.reverse('api:credential_copy', kwargs={'pk': obj.pk}),
        ))

        parents = [role for role in obj.admin_role.parents.all() if role.object_id is not None]
        if parents:
            res.update({parents[0].content_type.name:parents[0].content_object.get_absolute_url(self.context.get('request'))})
        elif len(obj.admin_role.members.all()) > 0:
            user = obj.admin_role.members.all()[0]
            res.update({'user': self.reverse('api:user_detail', kwargs={'pk': user.pk})})

        return res

    def get_summary_fields(self, obj):
        summary_dict = super(CredentialSerializer, self).get_summary_fields(obj)
        summary_dict['owners'] = []

        for user in obj.admin_role.members.all():
            summary_dict['owners'].append({
                'id': user.pk,
                'type': 'user',
                'name': user.username,
                'description': ' '.join([user.first_name, user.last_name]),
                'url': self.reverse('api:user_detail', kwargs={'pk': user.pk}),
            })

        for parent in [role for role in obj.admin_role.parents.all() if role.object_id is not None]:
            summary_dict['owners'].append({
                'id': parent.content_object.pk,
                'type': camelcase_to_underscore(parent.content_object.__class__.__name__),
                'name': parent.content_object.name,
                'description': parent.content_object.description,
                'url': parent.content_object.get_absolute_url(self.context.get('request')),
            })

        return summary_dict

    def get_validation_exclusions(self, obj=None):
        # CredentialType is now part of validation; legacy v1 fields (e.g.,
        # 'username', 'password') in JSON POST payloads use the
        # CredentialType's inputs definition to determine their validity
        ret = super(CredentialSerializer, self).get_validation_exclusions(obj)
        for field in ('credential_type', 'inputs'):
            if field in ret:
                ret.remove(field)
        return ret

    def to_internal_value(self, data):
        if 'credential_type' not in data:
            # If `credential_type` is not provided, assume the payload is a
            # v1 credential payload that specifies a `kind` and a flat list
            # of field values
            #
            # In this scenario, we should automatically detect the proper
            # CredentialType based on the provided values
            kind = data.get('kind', 'ssh')
            credential_type = CredentialType.from_v1_kind(kind, data)
            if credential_type is None:
                raise serializers.ValidationError({"kind": _('"%s" is not a valid choice' % kind)})
            data['credential_type'] = credential_type.pk
            value = OrderedDict(
                {'credential_type': credential_type}.items() +
                super(CredentialSerializer, self).to_internal_value(data).items()
            )

            # Make a set of the keys in the POST/PUT payload
            # - Subtract real fields (name, organization, inputs)
            # - Subtract virtual v1 fields defined on the determined credential
            #   type (username, password, etc...)
            # - Any leftovers are invalid for the determined credential type
            valid_fields = set(super(CredentialSerializer, self).get_fields().keys())
            valid_fields.update(V2CredentialFields().get_fields().keys())
            valid_fields.update(['kind', 'cloud'])

            for field in set(data.keys()) - valid_fields - set(credential_type.defined_fields):
                if data.get(field):
                    raise serializers.ValidationError(
                        {"detail": _("'%s' is not a valid field for %s") % (field, credential_type.name)}
                    )
            value.pop('kind', None)
            return value
        return super(CredentialSerializer, self).to_internal_value(data)

    def validate_credential_type(self, credential_type):
        if self.instance and credential_type.pk != self.instance.credential_type.pk:
            for rel in (
                    'ad_hoc_commands',
                    'insights_inventories',
                    'unifiedjobs',
                    'unifiedjobtemplates',
                    'projects',
                    'projectupdates',
                    'workflowjobnodes'
            ):
                if getattr(self.instance, rel).count() > 0:
                    raise ValidationError(
                        _('You cannot change the credential type of the credential, as it may break the functionality'
                          ' of the resources using it.'),
                    )

        return credential_type


class CredentialSerializerCreate(CredentialSerializer):

    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False, default=None, write_only=True, allow_null=True,
        help_text=_('Write-only field used to add user to owner role. If provided, '
                    'do not give either team or organization. Only valid for creation.'))

    class Meta:
        model = Credential
        fields = ('*', 'user')

    def validate(self, attrs):
        owner_fields = set()
        for field in ('user'):
            if field in attrs:
                if attrs[field]:
                    owner_fields.add(field)
                else:
                    attrs.pop(field)
        if not owner_fields:
            raise serializers.ValidationError({"detail": _("Missing 'user'.")})

        try:
            return super(CredentialSerializerCreate, self).validate(attrs)
        except ValidationError as e:
            # If we have an `inputs` error on `/api/v1/`:
            # {'inputs': {'username': [...]}}
            # ...instead, send back:
            # {'username': [...]}
            if self.version == 1 and isinstance(e.detail.get('inputs'), dict):
                e.detail = e.detail['inputs']+'toto'
                raise e
            else:
                raise

    def create(self, validated_data):
        user = validated_data.pop('user', None)
        team = validated_data.pop('team', None)

        # If our payload contains v1 credential fields, translate to the new
        # model
        for attr in (
                set(V1Credential.FIELDS) & set(validated_data.keys())  # set intersection
        ):
            validated_data.setdefault('inputs', {})
            value = validated_data.pop(attr)
            if value:
                validated_data['inputs'][attr] = value
        credential = super(CredentialSerializerCreate, self).create(validated_data)

        return credential


class UserCredentialSerializerCreate(CredentialSerializerCreate):

    class Meta:
        model = Credential
        fields = ('*', '-team', '-organization')

class LabelsListMixin(object):

    def _summary_field_labels(self, obj):
        label_list = [{'id': x.id, 'name': x.name} for x in obj.labels.all()[:10]]
        if has_model_field_prefetched(obj, 'labels'):
            label_ct = len(obj.labels.all())
        else:
            if len(label_list) < 10:
                label_ct = len(label_list)
            else:
                label_ct = obj.labels.count()
        return {'count': label_ct, 'results': label_list}

    def get_summary_fields(self, obj):
        res = super(LabelsListMixin, self).get_summary_fields(obj)
        res['labels'] = self._summary_field_labels(obj)
        return res


@six.add_metaclass(BaseSerializerMetaclass)
class LegacyCredentialFields(BaseSerializer):

    class Meta:
        model = Credential
        fields = ('*', 'credential', 'vault_credential')

    LEGACY_FIELDS = {
        'credential': models.PositiveIntegerField(blank=True, null=True, default=None, help_text=DEPRECATED),
        'vault_credential': models.PositiveIntegerField(blank=True, null=True, default=None, help_text=DEPRECATED),
    }

    def build_field(self, field_name, info, model_class, nested_depth):
        if field_name in self.LEGACY_FIELDS:
            return self.build_standard_field(field_name,
                                             self.LEGACY_FIELDS[field_name])
        return super(LegacyCredentialFields, self).build_field(field_name, info, model_class, nested_depth)


class JobOptionsSerializer(BaseSerializer):

    class Meta:
        fields = ('*', 'job_type', 'verbosity', 'timeout',)

    def get_fields(self):
        fields = super(JobOptionsSerializer, self).get_fields()
        fields.update(V1JobOptionsSerializer().get_fields())
        fields.update(LegacyCredentialFields().get_fields())
        return fields

    def to_representation(self, obj):
        ret = super(JobOptionsSerializer, self).to_representation(obj)
        if obj is None:
            return ret
        #ret['credential'] = obj.credential
        #ret['vault_credential'] = obj.vault_credential
        #ret['cloud_credential'] = obj.cloud_credential
        #ret['network_credential'] = obj.network_credential
        return ret

    def create(self, validated_data):
        deprecated_fields = {}
        for key in ('credential', 'vault_credential', 'cloud_credential', 'network_credential'):
            if key in validated_data:
                deprecated_fields[key] = validated_data.pop(key)
        obj = super(JobOptionsSerializer, self).create(validated_data)
        if deprecated_fields:
            self._update_deprecated_fields(deprecated_fields, obj)
        return obj

    def update(self, obj, validated_data):
        deprecated_fields = {}
        for key in ('credential', 'vault_credential', 'cloud_credential', 'network_credential'):
            if key in validated_data:
                deprecated_fields[key] = validated_data.pop(key)
        obj = super(JobOptionsSerializer, self).update(obj, validated_data)
        if deprecated_fields:
            self._update_deprecated_fields(deprecated_fields, obj)
        return obj

    def _update_deprecated_fields(self, fields, obj):
        for key, existing in (
                ('credential', obj.credentials.filter(credential_type__kind='ssh')),
                ('vault_credential', obj.credentials.filter(credential_type__kind='vault')),
                ('cloud_credential', obj.cloud_credentials),
                ('network_credential', obj.network_credentials),
        ):
            if key in fields:
                for cred in existing:
                    obj.credentials.remove(cred)
                if fields[key]:
                    obj.credentials.add(fields[key])
        obj.save()

    def validate(self, attrs):
        v1_credentials = {}
        view = self.context.get('view', None)
        for attr, kind, error in (
                ('cloud_credential', 'cloud', _('You must provide a cloud credential.')),
                ('network_credential', 'net', _('You must provide a network credential.')),
                ('credential', 'ssh', _('You must provide an SSH credential.')),
                ('vault_credential', 'vault', _('You must provide a vault credential.')),
        ):
            if attr in attrs:
                v1_credentials[attr] = None
                pk = attrs.pop(attr)
                if pk:
                    cred = v1_credentials[attr] = Credential.objects.get(pk=pk)
                    if cred.credential_type.kind != kind:
                        raise serializers.ValidationError({attr: error})
                    if ((not self.instance or cred.pk != getattr(self.instance, attr)) and
                            view and view.request and view.request.user not in cred.use_role):
                        raise PermissionDenied()

        ret = super(JobOptionsSerializer, self).validate(attrs)
        ret.update(v1_credentials)
        return ret


class JobSerializer(BaseSerializer):

    show_capabilities = ['start', 'delete']
    event_processing_finished = serializers.BooleanField(
        help_text=_('Indicates whether all of the events generated by this '
                    'unified job have been saved to the database.'),
        read_only=True
    )

    class Meta:
        model = Job
        fields = ('*', 'launch_type', 'status', 'policy',
                  'failed', 'started', 'finished', 'elapsed', 'job_args',
                  'original_size', 'compressed_size', 'deduplicated_size',
                  'job_cwd', 'job_env', 'job_explanation', 'client', 'repository',
                  'dependent_jobs', 'result_traceback', 'event_processing_finished', 'job_type')

    def get_types(self):
        if type(self) is JobSerializer:
            return ['job',]
        else:
            return super(JobSerializer, self).get_types()


    def get_summary_fields(self, obj):
        summary_dict = super(JobSerializer, self).get_summary_fields(obj)
        if obj.policy and obj.policy.repository_id:
            summary_dict['repository'] = {
                'id': obj.policy.repository_id,
                'name': obj.policy.repository.name
            }

        if obj.policy and obj.policy.schedule_id:
            summary_dict['schedule'] = {
                'id': obj.policy.schedule_id,
                'name': obj.policy.schedule.name
            }

        return summary_dict

    def get_related(self, obj):
        res = super(JobSerializer, self).get_related(obj)
        res.update(dict(
            job_events=self.reverse('api:job_job_events_list', kwargs={'pk': obj.pk}),
        ))
        if obj.policy_id:
            res['policy'] = self.reverse('api:policy_detail', kwargs={'pk': obj.policy_id})
        res['stdout'] = self.reverse('api:job_stdout', kwargs={'pk': obj.pk})
        if (obj.can_start or True):
            res['start'] = self.reverse('api:job_start', kwargs={'pk': obj.pk})
        if obj.can_cancel or True:
            res['cancel'] = self.reverse('api:job_cancel', kwargs={'pk': obj.pk})
        res['relaunch'] = self.reverse('api:job_relaunch', kwargs={'pk': obj.pk})
        return res

    def get_artifacts(self, obj):
        if obj:
            return obj.display_artifacts()
        return {}

    def to_internal_value(self, data):
        #if not self.instance and isinstance(data, dict):
        #    data.setdefault('name', job_template.name)
        #    data.setdefault('description', job_template.description)
        #    data.setdefault('job_type', job_template.job_type)
        #    data.setdefault('verbosity', job_template.verbosity)
        return super(JobSerializer, self).to_internal_value(data)

    def to_representation(self, obj):
        ret = super(JobSerializer, self).to_representation(obj)
        serializer_class = None
        #if type(self) is JobSerializer:
        #    if isinstance(obj, Job):
        #        serializer_class = BaseSerializer
        if serializer_class:
            serializer = serializer_class(instance=obj, context=self.context)
            ret = serializer.to_representation(obj)
        else:
            ret = super(JobSerializer, self).to_representation(obj)

        if 'elapsed' in ret:
            if obj and obj.pk and obj.started and not obj.finished:
                td = now() - obj.started
                ret['elapsed'] = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6) / (10 ** 6 * 1.0)
            ret['elapsed'] = float(ret['elapsed'])

        return ret


class JobStdoutSerializer(JobSerializer):

    result_stdout = serializers.SerializerMethodField()

    class Meta:
        fields = ('result_stdout',)

    def get_types(self):
        if type(self) is JobStdoutSerializer:
            return ['job']
        else:
            return super(JobStdoutSerializer, self).get_types()


class JobCancelSerializer(JobSerializer):

    can_cancel = serializers.BooleanField(read_only=True)

    class Meta:
        fields = ('can_cancel',)


class JobRelaunchSerializer(BaseSerializer):

    retry_counts = serializers.SerializerMethodField()
    class Meta:
        model = Job
        fields = ('retry_counts',)

    def to_representation(self, obj):
        res = super(JobRelaunchSerializer, self).to_representation(obj)
        view = self.context.get('view', None)
        return res

    def get_retry_counts(self, obj):
        if obj.status in ACTIVE_STATES:
            return _('Relaunch by host status not available until job finishes running.')
        data = OrderedDict([])
        return data

    def get_validation_exclusions(self, *args, **kwargs):
        r = super(JobRelaunchSerializer, self).get_validation_exclusions(*args, **kwargs)
        return r

    def validate(self, attrs):
        obj = self.instance
        attrs = super(JobRelaunchSerializer, self).validate(attrs)
        return attrs


class JobListSerializer(JobSerializer):

    class Meta:
        fields = ('*', '-job_args', '-job_cwd', '-job_env', '-result_traceback', '-event_processing_finished')

    def get_field_names(self, declared_fields, info):
        field_names = super(JobListSerializer, self).get_field_names(declared_fields, info)
        # Meta multiple inheritance and -field_name options don't seem to be
        # taking effect above, so remove the undesired fields here.
        return tuple(x for x in field_names if x not in ('job_args', 'job_cwd', 'job_env', 'result_traceback', 'event_processing_finished'))

    def get_types(self):
        if type(self) is JobListSerializer:
            return ['job',]
        else:
            return super(JobListSerializer, self).get_types()

    def to_representation(self, obj):
        serializer_class = None
        if type(self) is JobListSerializer:
            if isinstance(obj, Job):
                serializer_class = JobSerializer
        if serializer_class:
            serializer = serializer_class(instance=obj, context=self.context)
            ret = serializer.to_representation(obj)
        else:
            ret = super(JobListSerializer, self).to_representation(obj)
        if 'elapsed' in ret:
            ret['elapsed'] = float(ret['elapsed'])
        return ret


class JobEventSerializer(BaseSerializer):

    event_display = serializers.CharField(source='get_event_display2', read_only=True)
    event_level = serializers.IntegerField(read_only=True)

    class Meta:
        model = JobEvent
        fields = ('*', '-name', '-description', 'job', 'event', 'counter',
                  'event_display', 'event_data', 'event_level', 'failed',
                  'changed', 'uuid', 'task', 'stdout', 'start_line', 'end_line',
                  'verbosity', '-created_by', '-modified_by')

    def get_related(self, obj):
        res = super(JobEventSerializer, self).get_related(obj)
        res.update(dict(
            job=self.reverse('api:job_detail', kwargs={'pk': obj.job_id}),
        ))
        return res

    def get_summary_fields(self, obj):
        d = super(JobEventSerializer, self).get_summary_fields(obj)
        return d

    def to_representation(self, obj):
        ret = super(JobEventSerializer, self).to_representation(obj)
        # Show full stdout for event detail view, truncate only for list view.
        if hasattr(self.context.get('view', None), 'retrieve'):
            return ret
        # Show full stdout for playbook_on_* events.
        if obj and obj.event.startswith('playbook_on'):
            return ret
        max_bytes = 1024
        if max_bytes > 0 and 'stdout' in ret and len(ret['stdout']) >= max_bytes:
            ret['stdout'] = ret['stdout'][:(max_bytes - 1)] + u'\u2026'
            set_count = 0
            reset_count = 0
            for m in ANSI_SGR_PATTERN.finditer(ret['stdout']):
                if m.string[m.start():m.end()] == u'\u001b[0m':
                    reset_count += 1
                else:
                    set_count += 1
            ret['stdout'] += u'\u001b[0m' * (set_count - reset_count)
        return ret


class JobEventWebSocketSerializer(JobEventSerializer):
    created = serializers.SerializerMethodField()
    modified = serializers.SerializerMethodField()
    event_name = serializers.CharField(source='event')
    group_name = serializers.SerializerMethodField()

    class Meta:
        model = JobEvent
        fields = ('*', 'event_name', 'group_name',)

    def get_created(self, obj):
        return obj.created.isoformat()

    def get_modified(self, obj):
        return obj.modified.isoformat()

    def get_group_name(self, obj):
        return 'job_events'


class SettingSerializer(BaseSerializer):
    """Read-only serializer for activity stream."""

    value = VerbatimField(allow_null=True)

    class Meta:
        model = Setting
        fields = ('id', 'url', 'key', 'type', 'setting_type', 'value', 'created', 'modified')

    def update(self, obj, validated_data):
        validated_data.pop('key', None)
        obj = super(SettingSerializer, self).update(obj, validated_data)
        return obj

    def validate(self, attrs):
        attrs.pop('key', None)
        return attrs

class SettingListSerializer(SettingSerializer):

    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(SettingListSerializer, self).get_field_names(declared_fields, info)
        # Meta multiple inheritance and -field_name options don't seem to be
        # taking effect above, so remove the undesired fields here.
        return tuple(x for x in field_names)

    def get_types(self):
        if type(self) is SettingListSerializer:
            return ['setting']
        else:
            return super(SettingListSerializer, self).get_types()

    def to_representation(self, obj):
        serializer_class = None
        if type(self) is SettingListSerializer:
            if isinstance(obj, Setting):
                serializer_class = SettingSerializer
        if serializer_class:
            serializer = serializer_class(instance=obj, context=self.context)
            ret = serializer.to_representation(obj)
        else:
            ret = super(SettingListSerializer, self).to_representation(obj)
        return ret

class ClientSerializer(BaseSerializer):
    show_capabilities = ['edit', 'delete']

    class Meta:
        model = Client
        fields = ('*', '-name', '-description', 'hostname', 'ip', 'version', 'ready', 'hypervisor_ready', 'hypervisor_name', 'enabled', 'uuid')


class ClientListSerializer(ClientSerializer):

    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(ClientListSerializer, self).get_field_names(declared_fields, info)
        return tuple(x for x in field_names)

    def get_types(self):
        if type(self) is ClientListSerializer:
            return ['client']
        else:
            return super(ClientListSerializer, self).get_types()

    def to_representation(self, obj):
        serializer_class = None
        if type(self) is ClientListSerializer:
            if isinstance(obj, Client):
                serializer_class = ClientSerializer
        if serializer_class:
            serializer = serializer_class(instance=obj, context=self.context)
            ret = serializer.to_representation(obj)
        else:
            ret = super(ClientListSerializer, self).to_representation(obj)
        return ret

class ScheduleSerializer(BaseSerializer):
    """Read-only serializer for activity stream."""

    class Meta:
        model = Schedule
        fields = ('id', 'uuid', 'url', 'name', 'crontab', 'enabled', 'created', 'modified')

    def update(self, obj, validated_data):
        obj = super(ScheduleSerializer, self).update(obj, validated_data)
        return obj

    def validate(self, attrs):
        return attrs

class ScheduleListSerializer(ScheduleSerializer):

    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(ScheduleListSerializer, self).get_field_names(declared_fields, info)
        # Meta multiple inheritance and -field_name options don't seem to be
        # taking effect above, so remove the undesired fields here.
        return tuple(x for x in field_names)

    def get_types(self):
        if type(self) is ScheduleListSerializer:
            return ['schedule']
        else:
            return super(ScheduleListSerializer, self).get_types()

    def to_representation(self, obj):
        serializer_class = None
        if type(self) is ScheduleListSerializer:
            if isinstance(obj, Schedule):
                serializer_class = ScheduleSerializer
        if serializer_class:
            serializer = serializer_class(instance=obj, context=self.context)
            ret = serializer.to_representation(obj)
        else:
            ret = super(ScheduleListSerializer, self).to_representation(obj)
        return ret

class RepositorySerializer(BaseSerializer):
    """Read-only serializer for activity stream."""

    class Meta:
        model = Repository
        fields = ('id', 'uuid', 'url', 'name', 'path', 'repository_key', 'original_size', 'compressed_size', 'deduplicated_size', 'ready', 'enabled', 'created', 'modified')

    def update(self, obj, validated_data):
        obj = super(RepositorySerializer, self).update(obj, validated_data)
        return obj

    def validate(self, attrs):
        return attrs

class RepositoryListSerializer(RepositorySerializer):

    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(RepositoryListSerializer, self).get_field_names(declared_fields, info)
        # Meta multiple inheritance and -field_name options don't seem to be
        # taking effect above, so remove the undesired fields here.
        return tuple(x for x in field_names)

    def get_types(self):
        if type(self) is RepositoryListSerializer:
            return ['repository']
        else:
            return super(RepositoryListSerializer, self).get_types()

    def to_representation(self, obj):
        serializer_class = None
        if type(self) is RepositoryListSerializer:
            if isinstance(obj, Repository):
                serializer_class = RepositorySerializer
        if serializer_class:
            serializer = serializer_class(instance=obj, context=self.context)
            ret = serializer.to_representation(obj)
        else:
            ret = super(RepositoryListSerializer, self).to_representation(obj)
        return ret

class PolicySerializer(BaseSerializer):

    class Meta:
        model = Policy
        fields = ('*', 'id', 'uuid', 'url', 'name', 'extra_vars',
        'clients', 'repository', 'schedule', 'policy_type', 'keep_hourly',
        'keep_yearly', 'keep_daily', 'keep_weekly', 'keep_monthly',
        'vmprovider', 'next_run', 'mode_pull', 'enabled', 'created', 'modified')

    def get_related(self, obj):
        res = super(PolicySerializer, self).get_related(obj)
        res['launch'] = self.reverse('api:policy_launch', kwargs={'pk': obj.pk})
        res['calendar'] = self.reverse('api:policy_calendar', kwargs={'pk': obj.pk})
        if obj.schedule:
            res['schedule'] = self.reverse('api:schedule_detail', kwargs={'pk': obj.schedule.pk})
        if obj.repository:
            res['repository'] = self.reverse('api:repository_detail', kwargs={'pk': obj.repository.pk})
        return res

    def to_representation(self, obj):
        ret = super(PolicySerializer, self).to_representation(obj)
        if obj is not None and 'schedule' in ret and not obj.schedule:
            ret['schedule'] = None
        if obj is not None and 'repository' in ret and not obj.repository:
            ret['repository'] = None
        return ret

class PolicyListSerializer(PolicySerializer):

    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(PolicyListSerializer, self).get_field_names(declared_fields, info)
        # Meta multiple inheritance and -field_name options don't seem to be
        # taking effect above, so remove the undesired fields here.
        return tuple(x for x in field_names)

    def get_types(self):
        if type(self) is PolicyListSerializer:
            return ['policy']
        else:
            return super(PolicyListSerializer, self).get_types()

    def to_representation(self, obj):
        serializer_class = None
        if type(self) is PolicyListSerializer:
            if isinstance(obj, Policy):
                serializer_class = PolicySerializer
        if serializer_class:
            serializer = serializer_class(instance=obj, context=self.context)
            ret = serializer.to_representation(obj)
        else:
            ret = super(PolicyListSerializer, self).to_representation(obj)
        return ret


class PolicyLaunchSerializer(BaseSerializer):
    defaults = serializers.SerializerMethodField()
    extra_vars = serializers.JSONField(required=False, write_only=True)
    verbosity = serializers.IntegerField(required=False, initial=0, min_value=0, max_value=4, write_only=True)

    class Meta:
        model = Policy
        fields = ('defaults', 'extra_vars', 'verbosity')

    def get_defaults(self, obj):
        defaults_dict = {'verbosity': 0, 'extra_vars': obj.extra_vars}
        return defaults_dict

    def get_job_template_data(self, obj):
        return dict(name=obj.name, id=obj.id, description=obj.description)

    def validate_extra_vars(self, value):
        return vars_validate_or_raise(value)

    def validate(self, attrs):
        policy = self.context.get('policy')
        return attrs


class PolicyCalendarSerializer(EmptySerializer):
    events = serializers.ListField(child=serializers.DateTimeField())


class PolicyVMModuleSerializer(EmptySerializer):
    modules = serializers.SerializerMethodField()


class CatalogSerializer(BaseSerializer):

    class Meta:
        model = Catalog
        fields = ('id', 'url', 'archive_name', 'path', 'job', 'mode', 'mtime', 'owner', 'group', 'size', 'healthy')

    def get_related(self, obj):
        res = super(CatalogSerializer, self).get_related(obj)
        if obj.job:
            res['job'] = self.reverse('api:job_detail', kwargs={'pk': obj.job.pk})
        return res

    def to_representation(self, obj):
        ret = super(CatalogSerializer, self).to_representation(obj)
        if obj is not None and 'job' in ret and not obj.job:
            ret['job'] = None
        return ret

class CatalogListSerializer(DynamicFieldsSerializerMixin, CatalogSerializer):

    class Meta:
        model = Catalog
        fields = ('id', 'url', 'archive_name', 'path', 'job', 'mode', 'mtime', 'owner', 'group', 'size', 'healthy')
