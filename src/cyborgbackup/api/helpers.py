# Python
import logging

# Django
from django.core.exceptions import FieldError
from django.db import IntegrityError
from django.utils.safestring import mark_safe
from rest_framework import views
# Django REST Framework
from rest_framework.exceptions import ParseError

__all__ = ['get_view_description', 'get_view_name']

logger = logging.getLogger('cyborgbackup.api.helpers')
analytics_logger = logging.getLogger('cyborgbackup.analytics.performance')


def get_view_name(cls, suffix=None):
    """
    Wrapper around REST framework get_view_name() to support get_name() method
    and view_name property on a view class.
    """
    name = ''
    if hasattr(cls, 'get_name') and callable(cls.get_name):
        name = cls().get_name()
    elif hasattr(cls, 'view_name'):
        if callable(cls.view_name):
            name = cls.view_name()
        else:
            name = cls.view_name
    if name:
        return ('%s %s' % (name, suffix)) if suffix else name
    return views.get_view_name(cls)


def get_view_description(cls, request, html=False):
    """
    Wrapper around REST framework get_view_description() to support
    get_description() method and view_description property on a view class.
    """
    if hasattr(cls, 'get_description') and callable(cls.get_description):
        desc = cls().get_description(request, html=html)
        cls = type(cls.__name__, (object,), {'__doc__': desc})
    elif hasattr(cls, 'view_description'):
        if callable(cls.view_description):
            view_desc = cls.view_description()
        else:
            view_desc = cls.view_description
        cls = type(cls.__name__, (object,), {'__doc__': view_desc})
    desc = views.get_view_description(cls, html=html)
    if html:
        desc = '<div class="description">%s</div>' % desc
    return mark_safe(desc)


def get_default_schema():
    from cyborgbackup.api.swagger import AutoSchema
    return AutoSchema()


def api_exception_handler(exc, context):
    """
    Override default API exception handler to catch IntegrityError exceptions.
    """
    if isinstance(exc, IntegrityError):
        exc = ParseError(exc.args[0])
    if isinstance(exc, FieldError):
        exc = ParseError(exc.args[0])
    return views.exception_handler(exc, context)
