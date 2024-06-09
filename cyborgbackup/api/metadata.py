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

        placeholder = getattr(field, 'placeholder', serializers.empty)
        if placeholder is not serializers.empty:
            field_info['placeholder'] = placeholder

        # Update help text for common fields.
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

        # Indicate if a field has a default value.
        # FIXME: Still isn't showing all default values?
        try:
            default = field.get_default()
            field_info['default'] = default
        except serializers.SkipField:
            pass

        if getattr(field, 'child', None):
            field_info['child'] = self.get_field_info(field.child)
        elif getattr(field, 'fields', None):
            field_info['children'] = self.get_serializer_info(field)

        if not isinstance(field, (RelatedField, ManyRelatedField)) and hasattr(field, 'choices'):
            field_info['choices'] = [(choice_v, choice_n) for choice_v, choice_n in field.choices.items()]

        # Indicate if a field is write-only.
        if getattr(field, 'write_only', False):
            field_info['write_only'] = True

        # Update type of fields returned...
        if field.field_name == 'type':
            field_info['type'] = 'choice'
        elif field.field_name == 'url':
            field_info['type'] = 'string'
        elif field.field_name in ('related', 'summary_fields'):
            field_info['type'] = 'object'
        elif field.field_name in ('created', 'modified'):
            field_info['type'] = 'datetime'

        return field_info

    def get_serializer_info(self, serializer, method=None):
        filterer = getattr(serializer, 'filter_field_metadata', lambda fields, method: fields)
        return filterer(
            super(Metadata, self).get_serializer_info(serializer),
            method
        )

    def determine_actions(self, request, view):
        # Add field information for GET requests (so field names/labels are
        # available even when we can't POST/PUT).
        actions = {}
        for method in {'GET', 'PUT', 'POST'} & set(view.allowed_methods):
            view.request = clone_request(request, method)
            obj = None
            try:
                # Test global permissions
                if hasattr(view, 'check_permissions'):
                    view.check_permissions(view.request)
                # Test object permissions
                if method == 'PUT' and hasattr(view, 'get_object'):
                    obj = view.get_object()
            except (exceptions.APIException, PermissionDenied, Http404):
                continue
            else:
                # If user has appropriate permissions for the view, include
                # appropriate metadata about the fields that should be supplied.
                serializer = view.get_serializer(instance=obj)
                actions[method] = self.get_serializer_info(serializer, method=method)
            finally:
                view.request = request

            for field, meta in list(actions[method].items()):
                if not isinstance(meta, dict):
                    continue

                # Add type choices if available from the serializer.
                if field == 'type' and hasattr(serializer, 'get_type_choices'):
                    meta['choices'] = serializer.get_type_choices()

                # For GET method, remove meta attributes that aren't relevant
                # when reading a field and remove write-only fields.
                if method == 'GET':
                    attrs_to_remove = ('required', 'read_only', 'default', 'min_length', 'max_length', 'placeholder')
                    for attr in attrs_to_remove:
                        meta.pop(attr, None)
                        meta.get('child', {}).pop(attr, None)
                    if meta.pop('write_only', False):
                        actions['GET'].pop(field)

                # For PUT/POST methods, remove read-only fields.
                if method in ('PUT', 'POST'):
                    # This value should always be False for PUT/POST, so don't
                    # show it (file-based read-only settings can't be updated)
                    meta.pop('defined_in_file', False)

                    if meta.pop('read_only', False):
                        if field == 'id' and hasattr(view, 'attach'):
                            continue
                        actions[method].pop(field)

        return actions

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
