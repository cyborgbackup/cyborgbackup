# Python
import logging

from cyborgbackup.main.models.schedules import Schedule
# CyBorgBackup
from .generics import RetrieveUpdateDestroyAPIView, ListCreateAPIView
from ..serializers.schedules import ScheduleSerializer, ScheduleListSerializer

logger = logging.getLogger('cyborgbackups.api.views.schedules')


class ScheduleList(ListCreateAPIView):
    model = Schedule
    serializer_class = ScheduleListSerializer
    tags = ['Schedule']

    @property
    def allowed_methods(self):
        methods = super(ScheduleList, self).allowed_methods
        return methods


class ScheduleDetail(RetrieveUpdateDestroyAPIView):
    model = Schedule
    serializer_class = ScheduleSerializer
    tags = ['Schedule']
