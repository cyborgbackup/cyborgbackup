# Python
import copy
import logging
from collections import OrderedDict

# Django
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import models
from django.utils.encoding import force_str
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
# Django REST Framework
from rest_framework import fields
from rest_framework import serializers
from rest_framework import validators
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

# cyborgbackup
from cyborgbackup.api.fields import BooleanNullField, CharNullField, ChoiceNullField, VerbatimField
from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.models.clients import Client
from cyborgbackup.main.models.policies import Policy
from cyborgbackup.main.models.repositories import Repository
from cyborgbackup.main.models.schedules import Schedule
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.models.users import User
from cyborgbackup.main.utils.common import (
    get_type_for_model, get_model_for_type, camelcase_to_underscore,
    has_model_field_prefetched, prefetch_page_capabilities)
from cyborgbackup.main.validators import vars_validate_or_raise

logger = logging.getLogger('cyborgbackup.api.serializers.base')

DEPRECATED = 'This resource has been deprecated and will be removed in a future release'

# Fields that should be summarized regardless of object type.
DEFAULT_SUMMARY_FIELDS = ('id', 'name', 'created_by', 'modified_by')

# Keys are fields (foreign keys) where, if found on an instance, summary info
# should be added to the serialized data.  Values are a tuple of field names on
# the related object to include in the summary data (if the field is present on
# the related object).
SUMMARIZABLE_FK_FIELDS = {
    'user': ('id', 'email', 'first_name', 'last_name'),
    'application': ('id', 'name', 'client_id'),
    'job': ('id', 'name', 'status', 'failed', 'elapsed'),
    'policy': ('id', 'name', 'policy_type'),
    'client': ('id', 'hostname', 'bandwidth_limit'),
    'repository': ('id', 'name', 'path', 'enabled'),
    'schedule': ('id', 'name', 'crontab', 'enabled')
}


def reverse_gfk(content_object, request):
    """
    Computes a reverse for a GenericForeignKey field.

    Returns a dictionary of the form
        { '<type>': reverse(<type detail>) }
    for example
        { 'organization': '/api/v1/organizations/1/' }
    """
    if content_object is None or not hasattr(content_object, 'get_absolute_url'):
        return {}

    return {
        camelcase_to_underscore(content_object.__class__.__name__): content_object.get_absolute_url(request=request)
    }


class DynamicFieldsSerializerMixin:
    """
    A serializer mixin that takes an additional `fields` argument that controls
    which fields should be displayed.
    """

    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        fields: list | None = kwargs.pop('fields', None)

        # Instantiate the superclass normally
        super(DynamicFieldsSerializerMixin, self).__init__(*args, **kwargs)

        if fields:
            allowed = set(fields)
            existing = set(self.fields.keys())
            for field_name in existing - allowed:
                self.fields.pop(field_name)


class BaseSerializerMetaclass(serializers.SerializerMetaclass):
    """
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

    """

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
            if cls._is_list_of_strings(val) and cls._is_list_of_strings(meta_val or []):
                val = cls._merge_string_lists(base, val, meta_val)
            elif cls._is_extra_kwargs(val) and cls._is_extra_kwargs(meta_val or {}):
                val = cls._merge_extra_kwargs(base, val, meta_val)
            else:
                val = copy.deepcopy(val)
            if attr == 'fields':
                setattr(meta, 'optionals', cls._extract_optionals(val))
            setattr(meta, attr, val)

    @staticmethod
    def _merge_string_lists(base, val, meta_val):
        meta_val = meta_val or []
        new_vals = []
        except_vals = []
        optionals = []
        if base:
            new_vals.extend([x for x in meta_val])
        for v in val:
            if not base and v == '*':
                new_vals.extend([x for x in meta_val])
            elif not base and v.startswith('-'):
                except_vals.append(v[1:])
            else:
                if v.startswith('+'):
                    new_vals.append(v[1:])
                    optionals.append(v[1:])
                else:
                    new_vals.append(v)
        val = [v for v in new_vals if v not in except_vals]
        return tuple(val)

    @staticmethod
    def _merge_extra_kwargs(base, val, meta_val):
        meta_val = meta_val or {}
        new_val = {}
        if base:
            for k, v in meta_val.items():
                new_val[k] = copy.deepcopy(v)
        for k, v in val.items():
            new_val.setdefault(k, {}).update(copy.deepcopy(v))
        return new_val

    @staticmethod
    def _extract_optionals(val):
        optionals = [v[1:] for v in val if v.startswith('+')]
        return tuple(optionals)

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
        return 1

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
            'repository': 'Repository',
            'user': 'User'
        }
        choices = []
        for t in self.get_types():
            name = type_name_map.get(t, force_str(get_model_for_type(t)._meta.verbose_name).title())
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
        if getattr(obj, 'created_by', None):
            res['created_by'] = self.reverse('api:user_detail', kwargs={'pk': obj.created_by.pk})
        if getattr(obj, 'modified_by', None):
            res['modified_by'] = self.reverse('api:user_detail', kwargs={'pk': obj.modified_by.pk})
        return res

    def _get_summary_fields(self, obj):
        return {} if obj is None else self.get_summary_fields(obj)

    def get_summary_fields(self, obj):
        summary_fields = OrderedDict()
        self._add_fk_summary_fields(obj, summary_fields)
        self._add_created_by_summary(obj, summary_fields)
        self._add_modified_by_summary(obj, summary_fields)
        return summary_fields

    def _add_fk_summary_fields(self, obj, summary_fields):
        for fk, related_fields in SUMMARIZABLE_FK_FIELDS.items():
            try:
                fkval = getattr(obj, fk, None)
                if fkval is None or fkval == obj:
                    continue
                summary_fields[fk] = self._get_related_fields_summary(fk, fkval, related_fields)
            except ObjectDoesNotExist:
                pass

    def _get_related_fields_summary(self, fk, fkval, related_fields):
        related_summary = OrderedDict()
        for field in related_fields:
            if self.version < 2 and field == 'credential_type_id' and fk in ['credential', 'vault_credential']:
                continue
            fval = getattr(fkval, field, None)
            if fval is None and field == 'type':
                fval = get_type_for_model(fkval)
            if fval is not None:
                related_summary[field] = fval
        return related_summary

    def _add_created_by_summary(self, obj, summary_fields):
        if getattr(obj, 'created_by', None):
            summary_fields['created_by'] = self._get_user_summary(obj.created_by)

    def _add_modified_by_summary(self, obj, summary_fields):
        if getattr(obj, 'modified_by', None):
            summary_fields['modified_by'] = self._get_user_summary(obj.modified_by)

    def _get_user_summary(self, user):
        user_summary = OrderedDict()
        for field in SUMMARIZABLE_FK_FIELDS['user']:
            user_summary[field] = getattr(user, field)
        return user_summary

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
            return {parent_obj, capabilities_cache}
            # return get_user_capabilities(
            #     view.request.user, obj, method_list=self.show_capabilities, parent_obj=parent_obj,
            #     capabilities_cache=capabilities_cache
            # )
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
            return obj.last_login
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
        was_editable, model_field = self._handle_choices_editable(model_field)
        field_class, field_kwargs = super(BaseSerializer, self).build_standard_field(field_name, model_field)
        field_kwargs = self._restore_choices_editable(model_field, was_editable, field_kwargs)
        field_kwargs = self._set_field_defaults(model_field, field_kwargs)
        field_class, field_kwargs = self._enforce_min_value(model_field, field_class, field_kwargs)
        field_class, field_kwargs = self._use_custom_boolean_field(model_field, field_class, field_kwargs)
        field_class, field_kwargs = self._use_custom_char_field(model_field, field_class, field_kwargs)
        self._update_unique_validator_message(model_field, field_kwargs)
        return field_class, field_kwargs

    def _handle_choices_editable(self, model_field):
        if hasattr(model_field, 'choices') and model_field.choices:
            was_editable = model_field.editable
            model_field.editable = True
            return was_editable, model_field
        return False, model_field

    def _restore_choices_editable(self, model_field, was_editable, field_kwargs):
        if hasattr(model_field, 'choices') and model_field.choices:
            model_field.editable = was_editable
            if was_editable is False:
                field_kwargs['read_only'] = True
        return field_kwargs

    def _set_field_defaults(self, model_field, field_kwargs):
        if model_field.has_default() and not field_kwargs.get('read_only', False):
            field_kwargs['default'] = field_kwargs['initial'] = model_field.get_default()
        return field_kwargs

    def _enforce_min_value(self, model_field, field_class, field_kwargs):
        if isinstance(model_field, (
                models.PositiveIntegerField, models.PositiveSmallIntegerField)) and 'choices' not in field_kwargs:
            field_kwargs['min_value'] = 0
        return field_class, field_kwargs

    def _use_custom_boolean_field(self, model_field, field_class, field_kwargs):
        if isinstance(model_field, models.BooleanField) and not field_kwargs.get('read_only', False):
            field_class = BooleanNullField
        return field_class, field_kwargs

    def _use_custom_char_field(self, model_field, field_class, field_kwargs):
        if isinstance(model_field, (models.CharField, models.TextField)) and not field_kwargs.get('read_only', False):
            if 'choices' in field_kwargs:
                field_class = ChoiceNullField
            else:
                field_class = CharNullField
        return field_class, field_kwargs

    def _update_unique_validator_message(self, model_field, field_kwargs):
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
            exclusions = self.get_validation_exclusions(self.instance)
            obj = self._create_or_update_instance(attrs, exclusions)
            self._copy_instance_changes_to_attrs(obj, attrs, exclusions)
        except DjangoValidationError as exc:
            raise self._convert_django_validation_error(exc)
        return attrs

    def _create_or_update_instance(self, attrs, exclusions):
        obj = self.instance or self.Meta.model()
        for k, v in attrs.items():
            if k not in exclusions:
                setattr(obj, k, v)
        obj.full_clean(exclude=exclusions)
        return obj

    def _copy_instance_changes_to_attrs(self, obj, attrs, exclusions):
        for k in attrs.keys():
            if k not in exclusions:
                attrs[k] = getattr(obj, k)

    def _convert_django_validation_error(self, exc):
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
            d[k] = map(force_str, v2)
        return ValidationError(d)

    def reverse(self, *args, **kwargs):
        kwargs['request'] = self.context.get('request')
        return reverse(*args, **kwargs)

    @property
    def is_detail_view(self):
        if 'view' in self.context:
            if 'pk' in self.context['view'].kwargs:
                return True
        return False

    def to_representation(self, instance):
        ret = super(BaseSerializer, self).to_representation(instance)

        if hasattr(self.Meta, 'optionals'):
            request = self.context.get('request')
            fields = request.query_params.get('fields', '')
            if request.method == 'GET':
                for field in self.Meta.optionals:
                    if field in self.Meta.fields and field in ret and field not in fields.split(','):
                        logger.info("Delete field %s" % field)
                        del ret[field]

        return ret


class EmptySerializer(serializers.Serializer):
    pass


class UserSerializer(BaseSerializer):
    password = serializers.CharField(required=False, default='', write_only=True,
                                     help_text=_('Write-only field used to change the password.'))
    show_capabilities = ['edit', 'delete']

    class Meta:
        model = User
        fields = ('*', '-name', '-description', '-modified', '-username',
                  'first_name', 'last_name', 'email', 'is_superuser', 'password',
                  '-created_by', '-modified_by', 'notify_backup_daily',
                  'notify_backup_weekly', 'notify_backup_monthly',
                  'notify_backup_success', 'notify_backup_failed',
                  'notify_backup_summary')

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


class SettingSerializer(BaseSerializer):
    """Read-only serializer for activity stream."""

    value = VerbatimField(allow_null=True)

    class Meta:
        model = Setting
        fields = ('id', 'url', 'key', 'type', 'setting_type', 'value', 'group', 'order', 'created', 'modified')

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
        if isinstance(self, SettingListSerializer):
            return ['setting']
        else:
            return super(SettingListSerializer, self).get_types()


class ClientSerializer(BaseSerializer):
    show_capabilities = ['edit', 'delete']

    class Meta:
        model = Client
        fields = ('*', '-name', '-description', 'hostname', 'ip', 'bandwidth_limit',
                  'version', 'ready', 'hypervisor_ready', 'hypervisor_name', 'enabled', 'uuid')

    def get_summary_fields(self, obj):
        summary_dict = super(ClientSerializer, self).get_summary_fields(obj)
        relPolicies = Policy.objects.filter(clients__id=obj.pk)
        if relPolicies.exists():
            summary_dict['policies'] = OrderedDict()
            for pol in relPolicies:
                summary_dict['policies'].append({'id': pol.id, 'name': pol.name})

        return summary_dict


class ClientListSerializer(ClientSerializer):
    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(ClientListSerializer, self).get_field_names(declared_fields, info)
        return tuple(x for x in field_names)

    def get_types(self):
        if isinstance(self, ClientListSerializer):
            return ['client']
        else:
            return super(ClientListSerializer, self).get_types()


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
        if isinstance(self, ScheduleListSerializer):
            return ['schedule']
        else:
            return super(ScheduleListSerializer, self).get_types()


class RepositorySerializer(BaseSerializer):
    """Read-only serializer for activity stream."""

    class Meta:
        model = Repository
        fields = ('id', 'uuid', 'url', 'name', 'path', 'repository_key',
                  'original_size', 'compressed_size', 'deduplicated_size', 'ready', 'enabled', 'created', 'modified')

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
        if isinstance(self, RepositoryListSerializer):
            return ['repository']
        else:
            return super(RepositoryListSerializer, self).get_types()


class PolicySerializer(BaseSerializer):
    class Meta:
        model = Policy
        fields = ('*', 'id', 'uuid', 'url', 'name', 'extra_vars',
                  'clients', 'repository', 'schedule', 'policy_type', 'keep_hourly',
                  'keep_yearly', 'keep_daily', 'keep_weekly', 'keep_monthly',
                  'vmprovider', 'next_run', 'mode_pull', 'enabled', 'created', 'modified',
                  'prehook', 'posthook')

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
        if isinstance(self, PolicyListSerializer):
            return ['policy']
        else:
            return super(PolicyListSerializer, self).get_types()


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


class PolicyCalendarSerializer(EmptySerializer):
    events = serializers.ListField(child=serializers.DateTimeField())


class PolicyVMModuleSerializer(EmptySerializer):
    modules = serializers.SerializerMethodField()


class PolicyModuleSerializer(EmptySerializer):
    modules = serializers.SerializerMethodField()


class StatsSerializer(EmptySerializer):
    stats = serializers.ListField()


class CyborgTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Add custom claims
        token['email'] = user.email
        token['first_name'] = user.first_name
        token['last_name'] = user.last_name

        return token
