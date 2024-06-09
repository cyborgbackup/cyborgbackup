# Python
import logging
from collections import OrderedDict

from rest_framework import status
# Django REST Framework
from rest_framework.response import Response

from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.utils.encryption import Keypair
# CyBorgBackup
from .generics import ListAPIView, RetrieveUpdateAPIView, ListCreateAPIView
from ..serializers.base import EmptySerializer
from ..serializers.settings import SettingSerializer, SettingListSerializer

logger = logging.getLogger('cyborgbackups.api.views.settings')


class SettingList(ListAPIView):
    model = Setting
    serializer_class = SettingListSerializer
    tags = ['Setting']

    @property
    def allowed_methods(self):
        methods = super(SettingList, self).allowed_methods
        return methods


class SettingDetail(RetrieveUpdateAPIView):
    model = Setting
    serializer_class = SettingSerializer
    tags = ['Setting']


class SettingGetPublicSsh(ListAPIView):
    model = Setting
    serializer_class = EmptySerializer
    tags = ['Setting']

    def list(self, request, *args, **kwargs):
        set = Setting.get_value(name='cyborgbackup_ssh_key')
        if set:
            return Response(Keypair.get_publickey(set))
        else:
            return Response([])


class SettingGenerateSsh(ListCreateAPIView):
    model = Setting
    serializer_class = EmptySerializer
    tags = ['Setting']

    def list(self, request, *args, **kwargs):
        set = Setting.objects.get(key='cyborgbackup_ssh_key')
        if set.value != '':
            return Response([], status=status.HTTP_200_OK)
        else:
            return Response([], status=status.HTTP_204_NO_CONTENT)

    def create(self, request, *args, **kwargs):
        data = request.data
        set = Setting.objects.get(key='cyborgbackup_ssh_key')
        logger.debug(data)
        if set:
            if (set.value != '' and 'force' in data.keys()) \
                    or (set.value == ''):
                sshpass = Setting.objects.get(key='cyborgbackup_ssh_password')
                password = None
                if sshpass and sshpass.value != '':
                    password = sshpass.value
                kp = Keypair(passphrase=password, size=data['size'], type=data['type'])
                kp.generate()
                set.value = kp.privatekey
                set.save()
                sshpass.value = kp.passphrase
                sshpass.save()
                return Response({
                    'pubkey': kp.public_key
                }, status=status.HTTP_201_CREATED)
            else:
                return Response(OrderedDict(), status=status.HTTP_409_CONFLICT)
        else:
            return Response(OrderedDict(), status=status.HTTP_409_CONFLICT)
