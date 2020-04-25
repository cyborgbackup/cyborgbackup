# Python
import logging

# Django REST Framework
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework import permissions
from rest_framework.permissions import IsAuthenticated

# CyBorgBackup
from cyborgbackup.main.models import * # noqa

logger = logging.getLogger('cyborgbackup.api.permissions')

__all__ = ['ModelAccessPermission', 'UserPermission', 'IsSuperUser', 'check_user_access']


def check_user_access(user, model_class, action, *args, **kwargs):
    '''
    Return True if user can perform action against model_class with the
    provided parameters.
    '''
    result = False
    userAction = 'cyborgbackup.{}_{}'.format(action, model_class.__name__.lower())
    result = user.has_perm(userAction)
    if not result and hasattr(model_class, 'can_{}'.format(action)):
        method_perms = getattr(model_class, 'can_{}'.format(action))
        result = method_perms(user, *args, **kwargs)
    return result


class ModelAccessPermission(permissions.BasePermission):
    '''
    Default permissions class to check user access based on the model and
    request method, optionally verifying the request data.
    '''

    def check_options_permissions(self, request, view, obj=None):
        # return self.check_get_permissions(request, view, obj)
        return True

    def check_head_permissions(self, request, view, obj=None):
        return self.check_get_permissions(request, view, obj)

    def check_get_permissions(self, request, view, obj=None):
        if hasattr(view, 'parent_model'):
            parent_obj = view.get_parent_object()
            if not check_user_access(request.user, view.parent_model, 'read',
                                     parent_obj):
                return False
        if not obj:
            return True
        return check_user_access(request.user, view.model, 'read', obj)

    def check_post_permissions(self, request, view, obj=None):
        if hasattr(view, 'parent_model'):
            parent_obj = view.get_parent_object()
            if not check_user_access(request.user, view.parent_model, 'read',
                                     parent_obj):
                return False
            if hasattr(view, 'parent_key'):
                if not check_user_access(request.user, view.model, 'add', {view.parent_key: parent_obj}):
                    return False
            return True
        elif hasattr(view, 'obj_permission_type'):
            # Generic object-centric view permission check without object not needed
            if not obj:
                return True
            # Permission check that happens when get_object() is called
            extra_kwargs = {}
            if view.obj_permission_type == 'admin':
                extra_kwargs['data'] = {}
            return check_user_access(
                request.user, view.model, view.obj_permission_type, obj,
                **extra_kwargs
            )
        else:
            if obj:
                return True
            return check_user_access(request.user, view.model, 'add', request.data)

    def check_put_permissions(self, request, view, obj=None):
        if not obj:
            # FIXME: For some reason this needs to return True
            # because it is first called with obj=None?
            return True
        if getattr(view, 'is_variable_data', False):
            return check_user_access(request.user, view.model, 'change', obj,
                                     dict(variables=request.data))
        else:
            return check_user_access(request.user, view.model, 'change', obj,
                                     request.data)

    def check_patch_permissions(self, request, view, obj=None):
        return self.check_put_permissions(request, view, obj)

    def check_delete_permissions(self, request, view, obj=None):
        if not obj:
            # FIXME: For some reason this needs to return True
            # because it is first called with obj=None?
            return True

        return check_user_access(request.user, view.model, 'delete', obj)

    def check_permissions(self, request, view, obj=None):
        '''
        Perform basic permissions checking before delegating to the appropriate
        method based on the request method.
        '''

        if request.method.upper() == 'OPTIONS':
            return True

        # Don't allow anonymous users. 401, not 403, hence no raised exception.
        if not request.user or request.user.is_anonymous:
            return False

        # Always allow superusers
        if getattr(view, 'always_allow_superuser', True) and request.user.is_superuser:
            return True

        # Check if view supports the request method before checking permission
        # based on request method.
        if request.method.upper() not in view.allowed_methods:
            raise MethodNotAllowed(request.method)

        # Check permissions for the given view and object, based on the request
        # method used.
        check_method = getattr(self, 'check_%s_permissions' % request.method.lower(), None)
        result = check_method and check_method(request, view, obj)
        if not result:
            raise PermissionDenied()

        return result

    def has_permission(self, request, view, obj=None):
        logger.debug('has_permission(user=%s method=%s, %s, %r)',
                     request.user, request.method,
                     view.__class__.__name__, obj)
        try:
            response = self.check_permissions(request, view, obj)
        except Exception as e:
            logger.debug('has_permission raised %r', e, exc_info=True)
            raise
        else:
            logger.debug('has_permission returned %r', response)
            return response

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view, obj)


class UserPermission(ModelAccessPermission):
    def check_post_permissions(self, request, view, obj=None):
        if not request.data:
            return request.user.admin_of_organizations.exists()
        elif request.user.is_superuser:
            return True
        raise PermissionDenied()


class IsSuperUser(permissions.BasePermission):
    """
    Allows access only to admin users.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_superuser


class AllowOptionsAuthentication(IsAuthenticated):
    def has_permission(self, request, view):
        if request.method == 'OPTIONS':
            return True
        return request.user and request.user.is_authenticated