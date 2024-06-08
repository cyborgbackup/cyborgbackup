# Python
import logging

from rest_framework import status
# Django REST Framework
from rest_framework.response import Response

from cyborgbackup.main.models.clients import Client
from cyborgbackup.main.models.policies import Policy
# CyBorgBackup
from .generics import RetrieveUpdateDestroyAPIView, ListCreateAPIView
from ..serializers.clients import ClientSerializer, ClientListSerializer

logger = logging.getLogger('cyborgbackups.api.views.clients')


class ClientList(ListCreateAPIView):
    model = Client
    serializer_class = ClientListSerializer
    tags = ['Client']

    @property
    def allowed_methods(self):
        methods = super(ClientList, self).allowed_methods
        return methods


class ClientDetail(RetrieveUpdateDestroyAPIView):
    model = Client
    serializer_class = ClientSerializer
    tags = ['Client']

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        logger.debug(request.data)

        serializer = self.serializer_class(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        policies = Policy.objects.all()
        if policies.exists() and 'policies' in request.data.keys():
            for pol in policies:
                if (pol.id in request.data['policies'] and
                        len([x for x in pol.clients.all() if x.id == obj.id]) == 0):
                    logger.debug('Add client to policy {}'.format(pol.name))
                if (len([x for x in pol.clients.all() if x.id == obj.id]) > 0
                        and pol.id not in request.data['policies']):
                    logger.debug('Remove client from policy {}'.format(pol.name))

        return super(ClientDetail, self).patch(request, *args, **kwargs)
