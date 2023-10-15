# Python
import logging

# Django
from django.utils.translation import gettext_lazy as _

# Django REST Framework
from rest_framework.exceptions import PermissionDenied

# CyBorgBackup
from .generics import ListAPIView, RetrieveUpdateDestroyAPIView, ListCreateAPIView
from ..permissions import UserPermission
from ..serializers.users import UserSerializer
from cyborgbackup.main.models.users import User

logger = logging.getLogger('cyborgbackups.api.views.users')


class UserList(ListCreateAPIView):
    model = User
    serializer_class = UserSerializer
    permission_classes = (UserPermission,)
    tags = ['User']

    def post(self, request, *args, **kwargs):
        ret = super(UserList, self).post(request, *args, **kwargs)
        return ret


class UserMeList(ListAPIView):
    model = User
    serializer_class = UserSerializer
    view_name = _('Me')
    tags = ['User']

    def get_queryset(self):
        return self.model.objects.filter(pk=self.request.user.pk)


class UserDetail(RetrieveUpdateDestroyAPIView):
    model = User
    serializer_class = UserSerializer
    tags = ['User']

    def update_filter(self, request, *args, **kwargs):
        ''' make sure non-read-only fields that can only be edited by admins, are only edited by admins '''
        obj = self.get_object()

        su_only_edit_fields = ('is_superuser')
        # admin_only_edit_fields = ('username', 'is_active')

        fields_to_check = ()
        if not request.user.is_superuser:
            fields_to_check += su_only_edit_fields

        bad_changes = {}
        for field in fields_to_check:
            left = getattr(obj, field, None)
            right = request.data.get(field, None)
            if left is not None and right is not None and left != right:
                bad_changes[field] = (left, right)
        if bad_changes:
            raise PermissionDenied(_('Cannot change %s.') % ', '.join(bad_changes.keys()))
