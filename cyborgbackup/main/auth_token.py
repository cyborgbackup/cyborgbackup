import functools

# from channels.handler import AsgiRequest


# from channels.handler import AsgiRequest


# print(api_settings.DEFAULT_AUTHENTICATION_CLASSES)
# authenticators = [auth() for auth in api_settings.DEFAULT_AUTHENTICATION_CLASSES]


# def rest_auth(func):
#     """
#     Wraps a HTTP or WebSocket connect consumer (or any consumer of messages
#     that provides a "cookies" or "get" attribute) to provide a "http_session"
#     attribute that behaves like request.session; that is, it's hung off of
#     a per-user session key that is saved in a cookie or passed as the
#     "session_key" GET parameter.
#
#     It won't automatically create and set a session cookie for users who
#     don't have one - that's what SessionMiddleware is for, this is a simpler
#     read-only version for more low-level code.
#
#     If a message does not have a session we can inflate, the "session" attribute
#     will be None, rather than an empty session you can write to.
#
#     Does not allow a new session to be set; that must be done via a view. This
#     is only an accessor for any existing session.
#     """
#     @functools.wraps(func)
#     def inner(message, *args, **kwargs):
#         # Make sure there's NOT a http_session already
#         try:
#             # We want to parse the WebSocket (or similar HTTP-lite) message
#             # to get cookies and GET, but we need to add in a few things that
#             # might not have been there.
#             if "method" not in message.content:
#                 message.content['method'] = "FAKE"
#             request = AsgiRequest(message)
#
#         except Exception as e:
#             raise ValueError("Cannot parse HTTP message - are you sure this is a HTTP consumer? %s" % e)
#         # Make sure there's a session key
#         user = None
#         auth = None
#         auth_token = request.GET.get("token", None)
#         print('NEW TOKEN : {}'.format(auth_token))
#         if auth_token:
#             # comptatibility with rest framework
#             request._request = {}
#             request.META["HTTP_AUTHORIZATION"] = "Bearer {}".format(auth_token)
#             authenticators = [auth() for auth in api_settings.DEFAULT_AUTHENTICATION_CLASSES]
#             print('Try Auth with {}'.format(request.META['HTTP_AUTHORIZATION']))
#             for authenticator in authenticators:
#                 try:
#                     user_auth_tuple = authenticator.authenticate(request)
#                 except AuthenticationFailed:
#                     pass
#
#                 if user_auth_tuple is not None:
#                     message._authenticator = authenticator
#                     user, auth = user_auth_tuple
#                     break
#         message.user, message.auth = user, auth
#         # Make sure there's a session key
#         # Run the consumer
#         result = func(message, *args, **kwargs)
#         return result
#     return inner


def rest_token_user(func):
    """
saf    Wraps a HTTP or WebSocket consumer (or any consumer of messages
    that provides a "COOKIES" attribute) to provide both a "session"
    attribute and a "user" attibute, like AuthMiddleware does.

    This runs http_session() to get a session to hook auth off of.
    If the user does not have a session cookie set, both "session"
    and "user" will be None.
    """

    @functools.wraps(func)
    def inner(message, *args, **kwargs):
        # If we didn't get a session, then we don't get a user
        if not hasattr(message, "auth"):
            raise ValueError("Did not see a http session to get auth from")
        return func(message, *args, **kwargs)

    return inner


class RestTokenConsumerMixin(object):
    rest_user = False

    def get_handler(self, message, **kwargs):
        handler = super(RestTokenConsumerMixin, self).get_handler(message, **kwargs)
        if self.rest_user:
            handler = rest_token_user(handler)
        return handler

    def connect(self, message, **kwargs):
        if self.rest_user and not self.message.user:
            self.close()
        return message
