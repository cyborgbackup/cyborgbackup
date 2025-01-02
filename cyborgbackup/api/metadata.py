from collections import OrderedDict

# Django
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.encoding import force_str, smart_str
# Django REST Framework
from rest_framework import exceptions
from rest_framework import metadata
from rest_framework import serializers
from rest_framework.relations import RelatedField, ManyRelatedField
from rest_framework.request import clone_request


class Metadata(metadata.SimpleMetadata):

    def get_field_info(self, field):
        field_info = OrderedDict()
        field_info['type'] = self.label_lookup[field]
        field_info['required'] = getattr(field, 'required', False)

        self._add_text_attributes(field, field_info)
        self._add_placeholder(field, field_info)
        self._update_help_text(field, field_info)
        self._add_default_value(field, field_info)
        self._add_child_info(field, field_info)
        self._add_choices(field, field_info)
        self._add_write_only(field, field_info)
        self._update_field_type(field, field_info)

        return field_info

    def _add_text_attributes(self, field, field_info):
        text_attrs = [
            'read_only', 'label', 'help_text',
            'min_length', 'max_length',
            'min_value', 'max_value',
            'category', 'category_slug',
            'defined_in_file'
        ]
        for attr in text_attrs:
            value = getattr(field, attr, None)
            if value is not None and value != '':
                field_info[attr] = force_str(value, strings_only=True)

    def _add_placeholder(self, field, field_info):
        placeholder = getattr(field, 'placeholder', serializers.empty)
        if placeholder is not serializers.empty:
            field_info['placeholder'] = placeholder

    def _update_help_text(self, field, field_info):
        serializer = getattr(field, 'parent', None)
        if serializer:
            field_help_text = {
                'id': 'Database ID for this {}.',
                'name': 'Name of this {}.',
                'description': 'Optional description of this {}.',
                'type': 'Data type for this {}.',
                'url': 'URL for this {}.',
                'related': 'Data structure with URLs of related resources.',
                'summary_fields': 'Data structure with name/description for related resources.',
                'created': 'Timestamp when this {} was created.',
                'modified': 'Timestamp when this {} was last modified.',
            }
            if field.field_name in field_help_text:
                if hasattr(serializer, 'Meta') and hasattr(serializer.Meta, 'model'):
                    opts = serializer.Meta.model._meta.concrete_model._meta
                    verbose_name = smart_str(opts.verbose_name)
                    field_info['help_text'] = field_help_text[field.field_name].format(verbose_name)

    def _add_default_value(self, field, field_info):
        try:
            default = field.get_default()
            field_info['default'] = default
        except serializers.SkipField:
            pass

    def _add_child_info(self, field, field_info):
        if getattr(field, 'child', None):
            field_info['child'] = self.get_field_info(field.child)
        elif getattr(field, 'fields', None):
            field_info['children'] = self.get_serializer_info(field)

    def _add_choices(self, field, field_info):
        if not isinstance(field, (RelatedField, ManyRelatedField)) and hasattr(field, 'choices'):
            field_info['choices'] = [(choice_v, choice_n) for choice_v, choice_n in field.choices.items()]

    def _add_write_only(self, field, field_info):
        if getattr(field, 'write_only', False):
            field_info['write_only'] = True

    def _update_field_type(self, field, field_info):
        if field.field_name == 'type':
            field_info['type'] = 'choice'
        elif field.field_name == 'url':
            field_info['type'] = 'string'
        elif field.field_name in ('related', 'summary_fields'):
            field_info['type'] = 'object'
        elif field.field_name in ('created', 'modified'):
            field_info['type'] = 'datetime'

    def get_serializer_info(self, serializer, method=None):
        filterer = getattr(serializer, 'filter_field_metadata', lambda fields, method: fields)
        return filterer(
            super(Metadata, self).get_serializer_info(serializer),
            method
        )

    def determine_actions(self, request, view):
        actions = {}
        for method in {'GET', 'PUT', 'POST'} & set(view.allowed_methods):
            view.request = clone_request(request, method)
            obj = self._check_permissions(view, method)
            if obj is not None:
                serializer = view.get_serializer(instance=obj)
                actions[method] = self.get_serializer_info(serializer, method=method)
                self._process_action_fields(actions, method, serializer, view)
            view.request = request
        return actions

    def _check_permissions(self, view, method):
        try:
            if hasattr(view, 'check_permissions'):
                view.check_permissions(view.request)
            if method == 'PUT' and hasattr(view, 'get_object'):
                return view.get_object()
        except (exceptions.APIException, PermissionDenied, Http404):
            return None
        return None

    def _process_action_fields(self, actions, method, serializer, view):
        for field, meta in list(actions[method].items()):
            if not isinstance(meta, dict):
                continue
            self._handle_type_field(field, meta, serializer)
            if method == 'GET':
                self._handle_get_method(actions, field, meta)
            elif method in ('PUT', 'POST'):
                self._handle_put_post_methods(actions, field, meta, view)

    def _handle_type_field(self, field, meta, serializer):
        if field == 'type' and hasattr(serializer, 'get_type_choices'):
            meta['choices'] = serializer.get_type_choices()

    def _handle_get_method(self, actions, field, meta):
        self._remove_read_only_meta(meta)
        if meta.pop('write_only', False):
            actions['GET'].pop(field)

    def _handle_put_post_methods(self, actions, field, meta, view):
        meta.pop('defined_in_file', False)
        if meta.pop('read_only', False):
            if field == 'id' and hasattr(view, 'attach'):
                return
            actions[view.request.method].pop(field)

    def _remove_read_only_meta(self, meta):
        attrs_to_remove = ('required', 'read_only', 'default', 'min_length', 'max_length', 'placeholder')
        for attr in attrs_to_remove:
            meta.pop(attr, None)
            meta.get('child', {}).pop(attr, None)

    def determine_metadata(self, request, view):
        # store request on self so we can use it to generate field defaults
        self.request = request

        try:
            setattr(view, '_request', request)
            metadata = super(Metadata, self).determine_metadata(request, view)
        finally:
            delattr(view, '_request')

        # Add type(s) handled by this view/serializer.
        if hasattr(view, 'get_serializer'):
            serializer = view.get_serializer()
            if hasattr(serializer, 'get_types'):
                metadata['types'] = serializer.get_types()

        # Add search fields if available from the view.
        if getattr(view, 'search_fields', None):
            metadata['search_fields'] = view.search_fields

        # Add related search fields if available from the view.
        if getattr(view, 'related_search_fields', None):
            metadata['related_search_fields'] = view.related_search_fields

        from rest_framework import generics
        if isinstance(view, generics.ListAPIView) and hasattr(view, 'paginator'):
            metadata['max_page_size'] = view.paginator.max_page_size

        return metadata


class SublistAttachDetatchMetadata(Metadata):

    def determine_actions(self, request, view):
        actions = super(SublistAttachDetatchMetadata, self).determine_actions(request, view)
        method = 'POST'
        if method in actions:
            for field in actions[method]:
                if field == 'id':
                    continue
                actions[method].pop(field)
        return actions
