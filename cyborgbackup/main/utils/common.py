# Python
import json
import logging
import os
import re
import subprocess
from functools import reduce
from io import StringIO
from itertools import chain

import yaml
# Django
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.db import connection
# Django database
from django.db.migrations.loader import MigrationLoader
from django.db.models import Q
from django.db.models.fields.related import ForeignObjectRel, ManyToManyField
from django.db.models.query import QuerySet
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _
# Django REST Framework
from rest_framework.exceptions import ParseError, PermissionDenied

logger = logging.getLogger('cyborgbackup.main.utils')

__all__ = ['get_object_or_400', 'get_object_or_403', 'to_python_boolean', 'get_module_provider',
           'camelcase_to_underscore', 'get_type_for_model', 'get_model_for_type',
           'timestamp_apiformat', 'getattrd', 'has_model_field_prefetched', 'get_all_field_names',
           'prefetch_page_capabilities', 'copy_model_by_class', 'copy_m2m_relationships',
           'get_cyborgbackup_version', 'get_search_fields', 'could_be_script',
           'model_instance_diff', 'model_to_dict', 'OutputEventFilter', 'get_ssh_version',
           'parse_yaml_or_json', 'load_module_provider']


def get_module_provider():
    import importlib.util
    import pkgutil
    importlib.invalidate_caches()
    provider_dir = settings.PROVIDER_DIR
    data = []
    if os.path.isdir(provider_dir):
        for p in os.listdir(provider_dir):
            try:
                if os.path.isfile(os.path.join(provider_dir, p, '__init__.py')):
                    spec = importlib.util.spec_from_file_location(p, os.path.join(provider_dir, p, '__init__.py'))
                    loadedmodule = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(loadedmodule)
                    if hasattr(loadedmodule, 'module_name') and hasattr(loadedmodule, 'module_type'):
                        if loadedmodule.module_type() == 'vm':
                            module_name = loadedmodule.module_name()
                            extra_vars = ''
                            if hasattr(loadedmodule, 'module_extra_vars'):
                                extra_vars = loadedmodule.module_extra_vars()
                            data.append({'module': p, 'name': module_name, 'extra_vars': extra_vars})
                    del loadedmodule
            except Exception:
                pass
    del importlib
    del pkgutil
    return data


def load_module_provider(name):
    import importlib.util
    import pkgutil
    importlib.invalidate_caches()
    provider_dir = settings.PROVIDER_DIR
    the_module = None
    try:
        logger.debug(os.path.isfile(os.path.join(provider_dir, name, '__init__.py')))
        if os.path.isfile(os.path.join(provider_dir, name, '__init__.py')):
            spec = importlib.util.spec_from_file_location(name, os.path.join(provider_dir, name, '__init__.py'))
            loadedmodule = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loadedmodule)
            if hasattr(loadedmodule, 'module_name') and hasattr(loadedmodule, 'module_type'):
                if loadedmodule.module_type() == 'vm':
                    the_module = loadedmodule
    except Exception as e:
        logger.debug(e)
        pass
    del importlib
    del pkgutil
    return the_module


def model_instance_diff(old, new, serializer_mapping=None):
    """
    Calculate the differences between two model instances. One of the instances may be None (i.e., a newly
    created model or deleted model). This will cause all fields with a value to have changed (from None).
    serializer_mapping are used to determine read-only fields.
    When provided, read-only fields will not be included in the resulting dictionary
    """
    from django.db.models import Model

    if not (old is None or isinstance(old, Model)):
        raise TypeError('The supplied old instance is not a valid model instance.')
    if not (new is None or isinstance(new, Model)):
        raise TypeError('The supplied new instance is not a valid model instance.')
    old_password_fields = set(getattr(type(old), 'PASSWORD_FIELDS', [])) | {'password'}
    new_password_fields = set(getattr(type(new), 'PASSWORD_FIELDS', [])) | {'password'}

    diff = {}

    allowed_fields = get_allowed_fields(new, serializer_mapping)

    for field in allowed_fields:
        old_value = getattr(old, field, None)
        new_value = getattr(new, field, None)
        if old_value != new_value:
            diff[field] = (
                _convert_model_field_for_display(old, field, password_fields=old_password_fields),
                _convert_model_field_for_display(new, field, password_fields=new_password_fields),
            )

    if len(diff) == 0:
        diff = None

    return diff


def get_allowed_fields(obj, serializer_mapping):
    if serializer_mapping is not None and obj.__class__ in serializer_mapping:
        serializer_actual = serializer_mapping[obj.__class__]()
        allowed_fields = [x for x in serializer_actual.fields if not serializer_actual.fields[x].read_only] + ['id']
    else:
        allowed_fields = [x.name for x in obj._meta.fields]
    if obj._meta.model_name == 'user':
        field_blacklist = ['last_login']
        allowed_fields = [f for f in allowed_fields if f not in field_blacklist]
    return allowed_fields


def _convert_model_field_for_display(obj, field_name, password_fields=None):
    # NOTE: Careful modifying the value of field_val, as it could modify
    # underlying model object field value also.
    try:
        field_val = getattr(obj, field_name, None)
    except ObjectDoesNotExist:
        return '<missing {}>-{}'.format(obj._meta.verbose_name, getattr(obj, '{}_id'.format(field_name)))
    if password_fields is None:
        password_fields = set(getattr(type(obj), 'PASSWORD_FIELDS', [])) | {'password'}
    if field_name in password_fields or (
            isinstance(field_val, str) and
            field_val.startswith('$encrypted$')
    ):
        return u'hidden'
    if hasattr(obj, 'display_%s' % field_name):
        field_val = getattr(obj, 'display_%s' % field_name)()
    if isinstance(field_val, (list, dict)):
        try:
            field_val = json.dumps(field_val, ensure_ascii=False)
        except Exception:
            pass
    if type(field_val) not in (bool, int, type(None)):
        field_val = smart_str(field_val)
    return field_val


def model_to_dict(obj, serializer_mapping=None):
    """
    Serialize a model instance to a dictionary as best as possible
    serializer_mapping are used to determine read-only fields.
    When provided, read-only fields will not be included in the resulting dictionary
    """
    password_fields = set(getattr(type(obj), 'PASSWORD_FIELDS', [])) | {'password'}
    attr_d = {}

    allowed_fields = get_allowed_fields(obj, serializer_mapping)

    for field in obj._meta.fields:
        if field.name not in allowed_fields:
            continue
        attr_d[field.name] = _convert_model_field_for_display(obj, field.name, password_fields=password_fields)

    return attr_d


def get_object_or_400(klass, *args, **kwargs):
    """
    Return a single object from the given model or queryset based on the query
    params, otherwise raise an exception that will return in a 400 response.
    """
    from django.shortcuts import _get_queryset
    queryset = _get_queryset(klass)
    try:
        return queryset.get(*args, **kwargs)
    except queryset.model.DoesNotExist as e:
        raise ParseError(*e.args)
    except queryset.model.MultipleObjectsReturned as e:
        raise ParseError(*e.args)


def get_object_or_403(klass, *args, **kwargs):
    """
    Return a single object from the given model or queryset based on the query
    params, otherwise raise an exception that will return in a 403 response.
    """
    from django.shortcuts import _get_queryset
    queryset = _get_queryset(klass)
    try:
        return queryset.get(*args, **kwargs)
    except queryset.model.DoesNotExist as e:
        raise PermissionDenied(*e.args)
    except queryset.model.MultipleObjectsReturned as e:
        raise PermissionDenied(*e.args)


def to_python_boolean(value, allow_none=False):
    value = str(value)
    if value.lower() in ('true', '1', 't'):
        return True
    elif value.lower() in ('false', '0', 'f'):
        return False
    elif allow_none and value.lower() in ('none', 'null'):
        return None
    else:
        raise ValueError(_(u'Unable to convert "%s" to boolean') % str(value))


def camelcase_to_underscore(s):
    """
    Convert CamelCase names to lowercase_with_underscore.
    """
    s = re.sub(r'(((?<=[a-z])[A-Z])|([A-Z](?![A-Z]|$)))', '_\\1', s)
    return s.lower().strip('_')


def get_type_for_model(model):
    """
    Return type name for a given model class.
    """
    opts = model._meta.concrete_model._meta
    return camelcase_to_underscore(opts.object_name)


def get_all_field_names(model):
    # Implements compatibility with _meta.get_all_field_names
    # See: https://docs.djangoproject.com/en/1.11/ref/models/meta/#migrating-from-the-old-api
    return list(set(chain.from_iterable(
        (field.name, field.attname) if hasattr(field, 'attname') else (field.name,)
        for field in model._meta.get_fields()
        # For complete backwards compatibility, you may want to exclude
        # GenericForeignKey from the results.
        if not (field.many_to_one and field.related_model is None)
    )))


def get_search_fields(model):
    fields = []
    for field in model._meta.fields:
        if field.name in ('username', 'first_name', 'last_name', 'email',
                          'name', 'description'):
            fields.append(field.name)
    return fields


def validate_vars_type(vars_obj):
    if not isinstance(vars_obj, dict):
        vars_type = type(vars_obj)
        if hasattr(vars_type, '__name__'):
            data_type = vars_type.__name__
        else:
            data_type = str(vars_type)
        raise AssertionError(
            _('Input type `{data_type}` is not a dictionary').format(
                data_type=data_type)
        )


def parse_yaml_or_json(vars_str, silent_failure=True):
    """
    Attempt to parse a string of variables.
    First, with JSON parser, if that fails, then with PyYAML.
    If both attempts fail, return an empty dictionary if `silent_failure`
    is True, re-raise combination error if `silent_failure` if False.
    """
    if isinstance(vars_str, dict):
        return vars_str
    elif isinstance(vars_str, str) and vars_str == '""':
        return {}

    try:
        vars_dict = json.loads(vars_str)
        validate_vars_type(vars_dict)
    except (ValueError, TypeError, AssertionError) as json_err:
        try:
            vars_dict = yaml.safe_load(vars_str)
            # Can be None if '---'
            if vars_dict is None:
                return {}
            validate_vars_type(vars_dict)
        except (yaml.YAMLError, TypeError, AttributeError, AssertionError) as yaml_err:
            if silent_failure:
                return {}
            raise ParseError(_(
                'Cannot parse as JSON (error: {json_error}) or '
                'YAML (error: {yaml_error}).').format(
                json_error=str(json_err), yaml_error=str(yaml_err)))
    return vars_dict


def get_cyborgbackup_version():
    """
    Return CyBorgBackup version as reported by setuptools.
    """
    from cyborgbackup import __version__
    try:
        from importlib.metadata import version
        return version('cyborgbackup')
    except Exception:
        return __version__


def get_cyborgbackup_migration_version():
    loader = MigrationLoader(connection, ignore_no_migrations=True)
    v = '000'
    for app_name, migration_name in loader.applied_migrations:
        if app_name == 'main':
            version_captures = re.findall('^[0-9]{4}_v([0-9]{3})_', migration_name)
            if len(version_captures) == 1:
                migration_version = version_captures[0]
                if migration_version > v:
                    v = migration_version
    return v


def filter_insights_api_response(json):
    new_json = {}
    '''
    'last_check_in',
    'reports.[].rule.severity',
    'reports.[].rule.description',
    'reports.[].rule.category',
    'reports.[].rule.summary',
    'reports.[].maintenance_actions.[].maintenance_plan.name',
    'reports.[].maintenance_actions.[].maintenance_plan.maintenance_id',
    '''

    if 'last_check_in' in json:
        new_json['last_check_in'] = json['last_check_in']
    if 'reports' in json:
        new_json['reports'] = []
        for rep in json['reports']:
            new_report = {
                'rule': {},
                'maintenance_actions': []
            }
            if 'rule' in rep:
                for k in ['severity', 'description', 'category', 'summary']:
                    if k in rep['rule']:
                        new_report['rule'][k] = rep['rule'][k]

            for action in rep.get('maintenance_actions', []):
                new_action = {'maintenance_plan': {}}
                if 'maintenance_plan' in action:
                    for k in ['name', 'maintenance_id']:
                        if k in action['maintenance_plan']:
                            new_action['maintenance_plan'][k] = action['maintenance_plan'][k]
                new_report['maintenance_actions'].append(new_action)

            new_json['reports'].append(new_report)
    return new_json


def get_model_for_type(type):
    """
    Return model class for a given type name.
    """
    from django.contrib.contenttypes.models import ContentType
    for ct in ContentType.objects.filter(Q(app_label='main') | Q(app_label='auth', model='user')):
        ct_model = ct.model_class()
        if not ct_model:
            continue
        ct_type = get_type_for_model(ct_model)
        if type == ct_type:
            return ct_model
    else:
        raise DatabaseError('"{}" is not a valid CyBorgBackup model.'.format(type))


def timestamp_apiformat(timestamp):
    timestamp = timestamp.isoformat()
    if timestamp.endswith('+00:00'):
        timestamp = timestamp[:-6] + 'Z'
    return timestamp


class NoDefaultProvided(object):
    pass


def getattrd(obj, name, default=NoDefaultProvided):
    """
    Same as getattr(), but allows dot notation lookup
    Discussed in:
    https://stackoverflow.com/questions/11975781
    """

    try:
        return reduce(getattr, name.split("."), obj)
    except AttributeError:
        if default != NoDefaultProvided:
            return default
        raise


def has_model_field_prefetched(model_obj, field_name):
    # NOTE: Update this function if django internal implementation changes.
    return getattr(getattr(model_obj, field_name, None),
                   'prefetch_cache_name', '') in getattr(model_obj, '_prefetched_objects_cache', {})


def prefetch_page_capabilities(model, page, prefetch_list, user):
    """
    Given a `page` list of objects, a nested dictionary of user_capabilities
    are returned by id, ex.
    {
        4: {'edit': True, 'start': True},
        6: {'edit': False, 'start': False}
    }
    Each capability is produced for all items in the page in a single query

    Examples of prefetch language:
    prefetch_list = ['admin', 'execute']
      --> prefetch the admin (edit) and execute (start) permissions for
          items in list for current user
    prefetch_list = ['inventory.admin']
      --> prefetch the related inventory FK permissions for current user,
          and put it into the object's cache
    prefetch_list = [{'copy': ['inventory.admin', 'project.admin']}]
      --> prefetch logical combination of admin permission to inventory AND
          project, put into cache dictionary as "copy"
    """
    page_ids = [obj.id for obj in page]
    mapping = {}
    for obj in page:
        mapping[obj.id] = {}

    for prefetch_entry in prefetch_list:

        display_method = None
        if type(prefetch_entry) is dict:
            display_method = prefetch_entry.keys()[0]
            paths = prefetch_entry[display_method]
        else:
            paths = prefetch_entry

        if type(paths) is not list:
            paths = [paths]

        # Build the query for accessible_objects according the user & role(s)
        filter_args = []
        role_type = None
        for role_path in paths:
            if '.' in role_path:
                res_path = '__'.join(role_path.split('.')[:-1])
                role_type = role_path.split('.')[-1]
                parent_model = model
                for subpath in role_path.split('.')[:-1]:
                    parent_model = parent_model._meta.get_field(subpath).related_model
                filter_args.append(Q(
                    Q(**{'%s__pk__in' % res_path: parent_model.accessible_pk_qs(user, '%s_role' % role_type)}) |
                    Q(**{'%s__isnull' % res_path: True})))
            else:
                role_type = role_path
                filter_args.append(Q(**{'pk__in': model.accessible_pk_qs(user, '%s_role' % role_type)}))

        if display_method is None:
            # Role name translation to UI names for methods
            display_method = role_type
            if role_type == 'admin':
                display_method = 'edit'
            elif role_type in ['execute', 'update']:
                display_method = 'start'

        # Union that query with the list of items on page
        filter_args.append(Q(pk__in=page_ids))
        ids_with_role = set(model.objects.filter(*filter_args).values_list('pk', flat=True))

        # Save data item-by-item
        for obj in page:
            mapping[obj.pk][display_method] = bool(obj.pk in ids_with_role)

    return mapping


def copy_model_by_class(obj1, Class2, fields, kwargs):
    """
    Creates a new unsaved object of type Class2 using the fields from obj1
    values in kwargs can override obj1
    """
    create_kwargs = {}
    for field_name in fields:
        # Foreign keys can be specified as field_name or field_name_id.
        id_field_name = '%s_id' % field_name
        if hasattr(obj1, id_field_name):
            if field_name in kwargs:
                value = kwargs[field_name]
            elif id_field_name in kwargs:
                value = kwargs[id_field_name]
            else:
                value = getattr(obj1, id_field_name)
            if hasattr(value, 'id'):
                value = value.id
            create_kwargs[id_field_name] = value
        elif field_name in kwargs:
            if field_name == 'extra_vars' and isinstance(kwargs[field_name], dict):
                create_kwargs[field_name] = json.dumps(kwargs['extra_vars'])
            elif not isinstance(Class2._meta.get_field(field_name), (ForeignObjectRel, ManyToManyField)):
                create_kwargs[field_name] = kwargs[field_name]
        elif hasattr(obj1, field_name):
            field_obj = obj1._meta.get_field(field_name)
            if not isinstance(field_obj, ManyToManyField):
                create_kwargs[field_name] = getattr(obj1, field_name)

    # Apply class-specific extra processing for origination of jobs
    if hasattr(obj1, '_update_job_kwargs') and obj1.__class__ != Class2:
        new_kwargs = obj1._update_job_kwargs(create_kwargs, kwargs)
    else:
        new_kwargs = create_kwargs

    return Class2(**new_kwargs)


def copy_m2m_relationships(obj1, obj2, fields, kwargs=None):
    """
    In-place operation.
    Given two saved objects, copies related objects from obj1
    to obj2 to field of same name, if field occurs in `fields`
    """
    for field_name in fields:
        if hasattr(obj1, field_name):
            field_obj = obj1._meta.get_field(field_name)
            if isinstance(field_obj, ManyToManyField):
                # Many to Many can be specified as field_name
                src_field_value = getattr(obj1, field_name)
                if kwargs and field_name in kwargs:
                    override_field_val = kwargs[field_name]
                    if isinstance(override_field_val, (set, list, QuerySet)):
                        getattr(obj2, field_name).add(*override_field_val)
                        continue
                    if override_field_val.__class__.__name__ == 'ManyRelatedManager':
                        src_field_value = override_field_val
                dest_field = getattr(obj2, field_name)
                dest_field.add(*list(src_field_value.all().values_list('id', flat=True)))


def could_be_script(scripts_path, dir_path, filename):
    if os.path.splitext(filename)[-1] not in ['.py']:
        return None
    script_path = os.path.join(dir_path, filename)
    matchedLib = False
    matchedFunc = False
    try:
        for n, line in enumerate(open(script_path)):
            if 'from cyborgbackup.main.utils.params import Parameters' in line:
                matchedLib = True
            if 'def mainJob(' in line:
                matchedFunc = True
        source = open(script_path, 'r').read() + '\n'
        compile(source, filename, 'exec')
    except IOError:
        return None
    if not matchedLib and not matchedFunc:
        return None
    return os.path.relpath(str(script_path), str(scripts_path))


class OutputEventFilter(object):
    """
    File-like object that looks for encoded job events in stdout data.
    """

    EVENT_DATA_RE = re.compile(r'\x1b\[K((?:[A-Za-z0-9+/=]+\x1b\[\d+D)+)\x1b\[K')

    def __init__(self, event_callback):
        self._event_callback = event_callback
        self._event_ct = 0
        self._counter = 1
        self._start_line = 0
        self._buffer = StringIO()
        self._last_chunk = ''
        self._current_event_data = None

    def flush(self):
        # pexpect wants to flush the file it writes to, but we're not
        # actually capturing stdout to a raw file; we're just
        # implementing a custom `write` method to discover and emit events from
        # the stdout stream
        pass

    def write(self, data):
        self._buffer.write(data)
        self._emit_event(data)
        self._buffer = StringIO()

    def close(self):
        value = self._buffer.getvalue()
        if value:
            self._emit_event(value)
            self._buffer = StringIO()
        self._event_callback(dict(event='EOF'))

    def _emit_event(self, buffered_stdout, next_event_data=None):
        next_event_data = next_event_data or {}
        event_data = {}
        if self._current_event_data:
            event_data = self._current_event_data
            stdout_chunks = [buffered_stdout]
        elif buffered_stdout:
            event_data = dict(event='verbose')
            stdout_chunks = buffered_stdout.splitlines(True)
        else:
            stdout_chunks = []

        for stdout_chunk in stdout_chunks:
            event_data['counter'] = self._counter
            self._counter += 1
            event_data['stdout'] = stdout_chunk[:-2] if len(stdout_chunk) > 2 else ""
            n_lines = stdout_chunk.count('\n')
            event_data['start_line'] = self._start_line
            event_data['end_line'] = self._start_line + n_lines
            self._start_line += n_lines
            if self._event_callback:
                self._event_callback(event_data)
                self._event_ct += 1

        if next_event_data.get('uuid', None):
            self._current_event_data = next_event_data
        else:
            self._current_event_data = None


def get_ssh_version():
    """
    Return SSH version installed.
    """
    try:
        proc = subprocess.Popen(['ssh', '-V'],
                                stderr=subprocess.PIPE)
        result = proc.communicate()[1].decode('utf-8')
        return result.split(" ")[0].split("_")[1]
    except Exception:
        return 'unknown'
