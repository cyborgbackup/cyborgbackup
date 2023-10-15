# Python
import logging

# CyBorgBackup
from .generics import RetrieveUpdateDestroyAPIView, ListCreateAPIView
from ..serializers.repositories import RepositorySerializer, RepositoryListSerializer
from cyborgbackup.main.models.repositories import Repository

logger = logging.getLogger('cyborgbackups.api.views.repositories')


class RepositoryList(ListCreateAPIView):
    model = Repository
    serializer_class = RepositoryListSerializer
    tags = ['Repository']

    @property
    def allowed_methods(self):
        methods = super(RepositoryList, self).allowed_methods
        return methods


class RepositoryDetail(RetrieveUpdateDestroyAPIView):
    model = Repository
    serializer_class = RepositorySerializer
    tags = ['Repository']
