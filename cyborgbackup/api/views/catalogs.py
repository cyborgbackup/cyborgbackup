# Python
import logging
from collections import OrderedDict

import pymongo
# Django
from django.conf import settings as dsettings
from rest_framework import status
# Django REST Framework
from rest_framework.response import Response

from cyborgbackup.main.models.catalogs import Catalog
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.utils.callbacks import CallbackQueueDispatcher
# CyBorgBackup
from .generics import ListAPIView, RetrieveUpdateDestroyAPIView, ListCreateAPIView
from ..serializers.catalogs import RestoreLaunchSerializer, CatalogSerializer, CatalogListSerializer
from ..serializers.jobs import JobSerializer

logger = logging.getLogger('cyborgbackups.api.views.catalogs')


class RestoreLaunch(ListCreateAPIView):
    model = Job
    serializer_class = RestoreLaunchSerializer
    tags = ['Catalog']

    def list(self, request, *args, **kwargs):
        data = []
        return Response(data)

    def create(self, request, *args, **kwargs):
        result = None
        new_job = None
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        obj = serializer.validated_data
        jobs = Job.objects.filter(archive_name=obj['archive_name'])
        if jobs.exists():
            job = jobs[0]
            client = job.client

            jobs_client = Job.objects.filter(client=client.pk)
            if jobs_client.exists():
                for job_client in jobs_client:
                    if job_client.status in ['waiting', 'pending', 'running']:
                        return Response({'detail': 'Backup job already running for this client.'},
                                        status=status.HTTP_400_BAD_REQUEST)

            extra_vars = {
                'item': serializer.validated_data['item'],
                'dest': serializer.validated_data['destination'],
                'dry_run': serializer.validated_data['dry_run'],
                'dest_folder': serializer.validated_data['dest_folder']
            }

            new_job = job.policy.create_restore_job(source_job=job, extra_vars=extra_vars)

            result = new_job.signal_start()

        if not result:
            data = OrderedDict()
            new_job.delete()
            return Response(data, status=status.HTTP_400_BAD_REQUEST)
        else:
            data = OrderedDict()
            data['job'] = new_job.id
            data.update(JobSerializer(new_job, context=self.get_serializer_context()).to_representation(new_job))
            return Response(data, status=status.HTTP_201_CREATED)


class CatalogList(ListCreateAPIView):
    model = Catalog
    serializer_class = CatalogListSerializer
    tags = ['Catalog']

    def create(self, request, *args, **kwargs):
        data = request.data
        if set(data.keys()).intersection(['archive_name', 'job', 'event', 'catalog']):
            callback = CallbackQueueDispatcher()
            callback.dispatch(data)
            return Response(OrderedDict(), status=status.HTTP_201_CREATED)

        return Response(OrderedDict(), status=status.HTTP_400_BAD_REQUEST)


class CatalogDetail(RetrieveUpdateDestroyAPIView):
    model = Catalog
    serializer_class = CatalogSerializer
    tags = ['Catalog']


class MongoCatalog(ListAPIView):
    model = Catalog
    serializer_class = CatalogSerializer
    tags = ['Catalog']

    def list(self, request, *args, **kwargs):
        logger.debug(request.data)
        data = []
        archive_name = request.GET.get('archive_name', None)
        path = request.GET.get('path__regexp', None)
        db = pymongo.MongoClient(dsettings.MONGODB_URL).local
        if path:
            obj = db.catalog.find({'$and': [{'archive_name': archive_name}, {'path': {'$regex': '^{}$'.format(path)}}]},
                                  {"_id": 0, "archive_name": 1, "path": 1, "type": 1, "size": 1, "healthy": 1,
                                   "mtime": 1, "owner": 1, "group": 1, "mode": 1})
            data = list(obj.sort('path', 1))
            return Response({'count': len(data), 'results': data})
        else:
            obj = db.catalog.count({'archive_name': archive_name})
            return Response({'count': obj, 'results': []})
