# Python
import inspect
import logging
import time

# Django
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.core.exceptions import FieldDoesNotExist
from django.db import connection
from django.db.models.fields.related import OneToOneRel
from django.http import QueryDict
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _
from rest_framework import generics
from rest_framework import status
from rest_framework import views
# Django REST Framework
from rest_framework.authentication import get_authorization_header
from rest_framework.exceptions import PermissionDenied, AuthenticationFailed
from rest_framework.response import Response

# CyBorgBackup
from cyborgbackup.api.filters import FieldLookupBackend
from cyborgbackup.api.helpers import get_default_schema
from cyborgbackup.api.metadata import SublistAttachDetatchMetadata
from cyborgbackup.api.mixins import LoggingViewSetMixin
from cyborgbackup.main.utils.common import (get_object_or_400, camelcase_to_underscore,
                                            getattrd, get_all_field_names, get_search_fields)

logger = logging.getLogger('cyborgbackup.api.views.generics')


class LoggedLoginView(auth_views.LoginView):

    def post(self, request, *args, **kwargs):
        original_user = getattr(request, 'user', None)
        ret = super(LoggedLoginView, self).post(request, *args, **kwargs)
        current_user = getattr(request, 'user', None)
        if current_user and getattr(current_user, 'pk', None) and current_user != original_user:
            logger.info("User {} logged in.".format(current_user.email))
        if request.user.is_authenticated:
            return ret
        else:
            ret.status_code = 401
            return ret


class LoggedLogoutView(auth_views.LogoutView):

    def dispatch(self, request, *args, **kwargs):
        original_user = getattr(request, 'user', None)
        ret = super(LoggedLogoutView, self).dispatch(request, *args, **kwargs)
        current_user = getattr(request, 'user', None)
        if (not current_user or not getattr(current_user, 'pk', True)) \
                and current_user != original_user:
            logger.info("User {} logged out.".format(original_user.email))
        return ret


class APIView(views.APIView):
    schema = get_default_schema()

    def initialize_request(self, request, *args, **kwargs):
        """
        Store the Django REST Framework Request object as an attribute on the
        normal Django request, store time the request started.
        """
        self.time_started = time.time()
        if getattr(settings, 'SQL_DEBUG', True):
            self.queries_before = len(connection.queries)

        for custom_header in ['REMOTE_ADDR', 'REMOTE_HOST']:
            if custom_header.startswith('HTTP_'):
                request.environ.pop(custom_header, None)

        drf_request = super(APIView, self).initialize_request(request, *args, **kwargs)
        request.drf_request = drf_request
        try:
            request.drf_request_user = getattr(drf_request, 'user', False)
        except AuthenticationFailed:
            request.drf_request_user = None
        return drf_request

    def finalize_response(self, request, response, *args, **kwargs):
        """
        Log warning for 400 requests.  Add header with elapsed time.
        """
        if response.status_code >= 400:
            status_msg = "status %s received by user %s attempting to access %s from %s" % \
                         (response.status_code, request.user, request.path, request.META.get('REMOTE_ADDR', None))
            if response.status_code == 401:
                logger.info(status_msg)
            else:
                logger.warning(status_msg)
        response = super(APIView, self).finalize_response(request, response, *args, **kwargs)
        time_started = getattr(self, 'time_started', None)
        if time_started:
            time_elapsed = time.time() - self.time_started
            response['X-API-Time'] = '%0.3fs' % time_elapsed
        if getattr(settings, 'SQL_DEBUG', False):
            queries_before = getattr(self, 'queries_before', 0)
            for q in connection.queries:
                logger.debug(q)
            q_times = [float(q['time']) for q in connection.queries[queries_before:]]
            response['X-API-Query-Count'] = len(q_times)
            response['X-API-Query-Time'] = '%0.3fs' % sum(q_times)

        return response

    def get_authenticate_header(self, request):
        """
        Determine the WWW-Authenticate header to use for 401 responses.  Try to
        use the request header as an indication for which authentication method
        was attempted.
        """
        authenticator = None
        for authenticator in self.get_authenticators():
            resp_hdr = authenticator.authenticate_header(request)
            if not resp_hdr:
                continue
            req_hdr = get_authorization_header(request)
            if not req_hdr:
                continue
            if resp_hdr.split()[0] and resp_hdr.split()[0] == req_hdr.split()[0]:
                return resp_hdr
        # If it can't be determined from the request, use the last
        # authenticator (should be Basic).
        try:
            return authenticator.authenticate_header(request)
        except NameError:
            pass

    def get_view_description(self, html=False):
        """
        Return some descriptive text for the view, as used in OPTIONS responses
        and in the browsable API.
        """
        func = self.settings.VIEW_DESCRIPTION_FUNCTION
        return func(self.__class__, getattr(self, '_request', None), html)

    def get_description_context(self):
        return {
            'view': self,
            'docstring': type(self).__doc__ or '',
            'deprecated': getattr(self, 'deprecated', False),
            'swagger_method': getattr(self.request, 'swagger_method', None),
        }

    def get_description(self, request, html=False):
        self.request = request
        template_list = []
        for klass in inspect.getmro(type(self)):
            template_basename = camelcase_to_underscore(klass.__name__)
            template_list.append('api/%s.md' % template_basename)
        context = self.get_description_context()

        description = render_to_string(template_list, context)
        if context.get('deprecated') and context.get('swagger_method') is None:
            # render deprecation messages at the very top
            description = '\n'.join([render_to_string('api/_deprecated.md', context), description])
        return description

    def update_raw_data(self, data):
        # Remove the parent key if the view is a sublist, since it will be set
        # automatically.
        parent_key = getattr(self, 'parent_key', None)
        if parent_key:
            data.pop(parent_key, None)

        # Use request data as-is when original request is an update and the
        # submitted data was rejected.
        request_method = getattr(self, '_raw_data_request_method', None)
        response_status = getattr(self, '_raw_data_response_status', 0)
        if request_method in ('POST', 'PUT', 'PATCH') and response_status in range(400, 500):
            return self.request.data.copy()

        return data


class GenericAPIView(LoggingViewSetMixin, generics.GenericAPIView, APIView):
    # Base class for all model-based views.

    # Subclasses should define:
    #   model = ModelClass
    #   serializer_class = SerializerClass

    def get_serializer(self, *args, **kwargs):

        serializer_class = self.get_serializer_class()

        fields = None
        if self.request and self.request.method == 'GET':
            query_fields = self.request.query_params.get("fields", None)

            if query_fields:
                fields = tuple(query_fields.split(','))

        kwargs['context'] = self.get_serializer_context()
        if fields:
            kwargs['fields'] = fields

        serializer = serializer_class(*args, **kwargs)
        # Override when called from browsable API to generate raw data form;
        # update serializer "validated" data to be displayed by the raw data
        # form.
        if hasattr(self, '_raw_data_form_marker'):
            # Always remove read only fields from serializer.
            for name, field in list(serializer.fields.items()):
                if getattr(field, 'read_only', None):
                    del serializer.fields[name]
            serializer._data = self.update_raw_data(serializer.data)
        return serializer

    def get_queryset(self):
        if self.queryset is not None:
            return self.queryset._clone()
        elif self.model is not None:
            qs = self.model._default_manager.all()
            return qs
        else:
            return super(GenericAPIView, self).get_queryset()

    def get_description_context(self):
        # Set instance attributes needed to get serializer metadata.
        if not hasattr(self, 'request'):
            self.request = None
        if not hasattr(self, 'format_kwarg'):
            self.format_kwarg = 'format'
        d = super(GenericAPIView, self).get_description_context()
        if hasattr(self.model, "_meta"):
            if hasattr(self.model._meta, "verbose_name"):
                d.update({
                    'model_verbose_name': smart_str(self.model._meta.verbose_name),
                    'model_verbose_name_plural': smart_str(self.model._meta.verbose_name_plural),
                })
            serializer = self.get_serializer()
            for method, key in [
                ('GET', 'serializer_fields'),
                ('POST', 'serializer_create_fields'),
                ('PUT', 'serializer_update_fields')
            ]:
                d[key] = self.metadata_class().get_serializer_info(serializer, method=method)
        d['settings'] = settings
        return d


class SimpleListAPIView(generics.ListAPIView, GenericAPIView):

    def get_queryset(self):
        return self.request.user.get_queryset(self.model)


class ListAPIView(generics.ListAPIView, GenericAPIView):
    # Base class for a read-only list view.

    def get_description_context(self):
        if 'username' in get_all_field_names(self.model):
            order_field = 'username'
        else:
            order_field = 'name'
        d = super(ListAPIView, self).get_description_context()
        d.update({
            'order_field': order_field,
        })
        return d

    @property
    def search_fields(self):
        return get_search_fields(self.model)

    def get_queryset(self):
        queryset = self.model.objects.all()
        fields = self.request.query_params.get('fields', None)
        if fields:
            list_field = fields.split(',')
            queryset = queryset.values(*list_field).distinct()
        order = self.request.query_params.get('order', '-id')
        if order and order in ('-id', 'foo', 'bar'):
            queryset = queryset.order_by(order)
        return queryset

    @property
    def related_search_fields(self):
        def skip_related_name(name):
            return (
                    name is None or name.endswith('_role') or name.startswith('_') or
                    name.startswith('deprecated_') or name.endswith('_set') or
                    name == 'polymorphic_ctype')

        fields = set([])
        for field in self.model._meta.fields:
            if skip_related_name(field.name):
                continue
            if getattr(field, 'related_model', None):
                fields.add('{}__search'.format(field.name))
        for rel in self.model._meta.related_objects:
            name = rel.related_name
            if isinstance(rel, OneToOneRel) and self.model._meta.verbose_name.startswith('unified'):
                # Add underscores for polymorphic subclasses for user utility
                name = rel.related_model._meta.verbose_name.replace(" ", "_")
            if skip_related_name(name) or name.endswith('+'):
                continue
            fields.add('{}__search'.format(name))
        m2m_rel = []
        m2m_rel += self.model._meta.local_many_to_many
        for relationship in m2m_rel:
            if skip_related_name(relationship.name):
                continue
            if relationship.related_model._meta.app_label != 'main':
                continue
            fields.add('{}__search'.format(relationship.name))
        fields = list(fields)

        allowed_fields = []
        for field in fields:
            try:
                FieldLookupBackend().get_field_from_lookup(self.model, field)
            except PermissionDenied:
                pass
            except FieldDoesNotExist:
                allowed_fields.append(field)
            else:
                allowed_fields.append(field)
        return allowed_fields


class ListCreateAPIView(ListAPIView, generics.ListCreateAPIView):
    # Base class for a list view that allows creating new objects.
    pass


class ParentMixin(object):
    parent_object = None

    def get_parent_object(self):
        if self.parent_object is not None:
            return self.parent_object
        parent_filter = {
            self.lookup_field: self.kwargs.get(self.lookup_field, None),
        }
        self.parent_object = get_object_or_404(self.parent_model, **parent_filter)
        return self.parent_object

    def check_parent_access(self, parent=None):
        parent = parent or self.get_parent_object()
        parent_access = getattr(self, 'parent_access', 'read')
        if parent_access in ('read', 'delete'):
            args = (self.parent_model, parent_access, parent)
        else:
            args = (self.parent_model, parent_access, parent, None)
        return args


class SubListAPIView(ParentMixin, ListAPIView):
    # Base class for a read-only sublist view.

    # Subclasses should define at least:
    #   model = ModelClass
    #   serializer_class = SerializerClass
    #   parent_model = ModelClass
    #   relationship = 'rel_name_from_parent_to_model'
    # And optionally (user must have given access permission on parent object
    # to view sublist):
    #   parent_access = 'read'

    def get_description_context(self):
        d = super(SubListAPIView, self).get_description_context()
        d.update({
            'parent_model_verbose_name': smart_str(self.parent_model._meta.verbose_name),
            'parent_model_verbose_name_plural': smart_str(self.parent_model._meta.verbose_name_plural),
        })
        return d

    def get_queryset(self):
        parent = self.get_parent_object()
        sublist_qs = getattrd(parent, self.relationship).distinct()
        return sublist_qs


class SubListLoopAPIView(ParentMixin, ListAPIView):
    # Base class for a read-only sublist view.

    # Subclasses should define at least:
    #   model = ModelClass
    #   serializer_class = SerializerClass
    #   parent_model = ModelClass
    #   relationship = 'rel_name_from_parent_to_model'
    # And optionally (user must have given access permission on parent object
    # to view sublist):
    #   parent_access = 'read'

    def get_description_context(self):
        d = super(SubListLoopAPIView, self).get_description_context()
        d.update({
            'parent_model_verbose_name': smart_str(self.parent_model._meta.verbose_name),
            'parent_model_verbose_name_plural': smart_str(self.parent_model._meta.verbose_name_plural),
        })
        return d

    def get_queryset(self):
        parent = self.get_parent_object()
        sublist_qs = getattrd(parent, self.relationship).distinct()
        return sublist_qs


class SubListDestroyAPIView(generics.DestroyAPIView, SubListAPIView):
    """
    Concrete view for deleting everything related by `relationship`.
    """
    check_sub_obj_permission = True

    def destroy(self, request, *args, **kwargs):
        instance_list = self.get_queryset()
        if (not self.check_sub_obj_permission and
                not request.user.can_access(self.parent_model, 'delete', self.get_parent_object())):
            raise PermissionDenied()
        self.perform_list_destroy(instance_list)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_list_destroy(self, instance_list):
        if self.check_sub_obj_permission:
            # Check permissions for all before deleting, avoiding half-deleted lists
            for instance in instance_list:
                if self.has_delete_permission(instance):
                    raise PermissionDenied()
        for instance in instance_list:
            self.perform_destroy(instance)


class SubListCreateAPIView(SubListAPIView, ListCreateAPIView):
    # Base class for a sublist view that allows for creating subobjects
    # associated with the parent object.

    # In addition to SubListAPIView properties, subclasses may define (if the
    # sub_obj requires a foreign key to the parent):
    #   parent_key = 'field_on_model_referring_to_parent'

    def get_description_context(self):
        d = super(SubListCreateAPIView, self).get_description_context()
        d.update({
            'parent_key': getattr(self, 'parent_key', None),
        })
        return d

    def create(self, request, *args, **kwargs):
        # If the object ID was not specified, it probably doesn't exist in the
        # DB yet. We want to see if we can create it.  The URL may choose to
        # inject it's primary key into the object because we are posting to a
        # subcollection. Use all the normal access control mechanisms.

        # Make a copy of the data provided (since it's readonly) in order to
        # inject additional data.
        if hasattr(request.data, 'copy'):
            data = request.data.copy()
        else:
            data = QueryDict('')
            data.update(request.data)

        # add the parent key to the post data using the pk from the URL
        parent_key = getattr(self, 'parent_key', None)
        if parent_key:
            data[parent_key] = self.kwargs['pk']

        # attempt to deserialize the object
        serializer = self.get_serializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)

        # Verify we have permission to add the object as given.
        if not request.user.can_access(self.model, 'add', serializer.initial_data):
            raise PermissionDenied()

        # save the object through the serializer, reload and returned the saved
        # object deserialized
        obj = serializer.save()
        serializer = self.get_serializer(instance=obj)

        headers = {'Location': obj.get_absolute_url(request)}
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class SubListCreateAttachDetachAPIView(SubListCreateAPIView):
    # Base class for a sublist view that allows for creating subobjects and
    # attaching/detaching them from the parent.

    def is_valid_relation(self, parent, sub, created=False):
        return None

    def get_description_context(self):
        d = super(SubListCreateAttachDetachAPIView, self).get_description_context()
        d.update({
            "has_attach": True,
        })
        return d

    def attach_validate(self, request):
        sub_id = request.data.get('id', None)
        res = None
        if sub_id and not isinstance(sub_id, int):
            data = dict(msg=_('"id" field must be an integer.'))
            res = Response(data, status=status.HTTP_400_BAD_REQUEST)
        return sub_id, res

    def attach(self, request, *args, **kwargs):
        created = False
        parent = self.get_parent_object()
        relationship = getattrd(parent, self.relationship)
        data = request.data
        location = None

        sub_id, res = self.attach_validate(request)
        if res:
            return res

        # Create the sub object if an ID is not provided.
        if not sub_id:
            response = self.create(request, *args, **kwargs)
            if response.status_code != status.HTTP_201_CREATED:
                return response
            sub_id = response.data['id']
            data = response.data
            try:
                location = response['Location']
            except KeyError:
                location = None
            created = True

        # Retrive the sub object (whether created or by ID).
        sub = get_object_or_400(self.model, pk=sub_id)

        # Verify that the relationship to be added is valid.
        attach_errors = self.is_valid_relation(parent, sub, created=created)
        if attach_errors is not None:
            if created:
                sub.delete()
            return Response(attach_errors, status=status.HTTP_400_BAD_REQUEST)

        # Attach the object to the collection.
        if sub not in relationship.all():
            relationship.add(sub)

        if created:
            headers = {}
            if location:
                headers['Location'] = location
            return Response(data, status=status.HTTP_201_CREATED, headers=headers)
        else:
            return Response(status=status.HTTP_204_NO_CONTENT)

    def unattach_validate(self, request):
        sub_id = request.data.get('id', None)
        res = None
        if not sub_id:
            data = dict(msg=_('"id" is required to disassociate'))
            res = Response(data, status=status.HTTP_400_BAD_REQUEST)
        elif not isinstance(sub_id, int):
            data = dict(msg=_('"id" field must be an integer.'))
            res = Response(data, status=status.HTTP_400_BAD_REQUEST)
        return sub_id, res

    def unattach_by_id(self, request, sub_id):
        parent = self.get_parent_object()
        parent_key = getattr(self, 'parent_key', None)
        relationship = getattrd(parent, self.relationship)
        sub = get_object_or_400(self.model, pk=sub_id)

        if parent_key:
            sub.delete()
        else:
            relationship.remove(sub)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def unattach(self, request, *args, **kwargs):
        (sub_id, res) = self.unattach_validate(request)
        if res:
            return res
        return self.unattach_by_id(request, sub_id)

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            return Response('invalid type for post data',
                            status=status.HTTP_400_BAD_REQUEST)
        if 'disassociate' in request.data:
            return self.unattach(request, *args, **kwargs)
        else:
            return self.attach(request, *args, **kwargs)


class SubListAttachDetachAPIView(SubListCreateAttachDetachAPIView):
    """
    Derived version of SubListCreateAttachDetachAPIView that prohibits creation
    """
    metadata_class = SublistAttachDetatchMetadata

    def post(self, request, *args, **kwargs):
        sub_id = request.data.get('id', None)
        if not sub_id:
            return Response(
                dict(msg=_("{} 'id' field is missing.".format(
                    self.model._meta.verbose_name.title()))),
                status=status.HTTP_400_BAD_REQUEST)
        return super(SubListAttachDetachAPIView, self).post(request, *args, **kwargs)

    def update_raw_data(self, data):
        request_method = getattr(self, '_raw_data_request_method', None)
        response_status = getattr(self, '_raw_data_response_status', 0)
        if request_method == 'POST' and response_status in range(400, 500):
            return super(SubListAttachDetachAPIView, self).update_raw_data(data)
        return {'id': None}


class DeleteLastUnattachLabelMixin(object):
    """
    Models for which you want the last instance to be deleted from the database
    when the last disassociate is called should inherit from this class. Further,
    the model should implement is_detached()
    """

    def unattach(self, request, *args, **kwargs):
        (sub_id, res) = super(DeleteLastUnattachLabelMixin, self).unattach_validate(request)
        if res:
            return res

        res = super(DeleteLastUnattachLabelMixin, self).unattach_by_id(request, sub_id)

        obj = self.model.objects.get(id=sub_id)

        if obj.is_detached():
            obj.delete()

        return res


class SubDetailAPIView(ParentMixin, generics.RetrieveAPIView, GenericAPIView):
    pass


class RetrieveAPIView(generics.RetrieveAPIView, GenericAPIView):
    pass


class RetrieveUpdateAPIView(RetrieveAPIView, generics.RetrieveUpdateAPIView):

    def update(self, request, *args, **kwargs):
        self.update_filter(request, *args, **kwargs)
        return super(RetrieveUpdateAPIView, self).update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self.update_filter(request, *args, **kwargs)
        return super(RetrieveUpdateAPIView, self).partial_update(request, *args, **kwargs)

    def update_filter(self, request, *args, **kwargs):
        """
        scrub any fields the user cannot/should not put/patch, based on user context.
        This runs after read-only serialization filtering
        """
        pass


class RetrieveDestroyAPIView(RetrieveAPIView, generics.DestroyAPIView):
    pass


class RetrieveUpdateDestroyAPIView(RetrieveUpdateAPIView, generics.DestroyAPIView):
    pass
