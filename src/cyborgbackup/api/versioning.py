from rest_framework.reverse import _reverse


def drf_reverse(viewname, args=None, kwargs=None, request=None, format=None, **extra):
    """
    Copy and monkey-patch `rest_framework.reverse.reverse` to prevent adding unwarranted
    query string parameters.
    """

    return _reverse(viewname, args, kwargs, request, format, **extra)


def reverse(viewname, args=None, kwargs=None, request=None, format=None, **extra):
    return drf_reverse(viewname, args, kwargs, request, format, **extra)
