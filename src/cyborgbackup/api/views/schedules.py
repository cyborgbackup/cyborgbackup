# Python
import logging

# CyBorgBackup
from .generics import RetrieveUpdateDestroyAPIView, ListCreateAPIView
from ..serializers.schedules import ScheduleSerializer, ScheduleListSerializer
from cyborgbackup.main.models.schedules import Schedule

logger = logging.getLogger('cyborgbackups.api.views.schedules')


class ScheduleList(ListCreateAPIView):
    model = Schedule
    serializer_class = ScheduleListSerializer

    @property
    def allowed_methods(self):
        methods = super(ScheduleList, self).allowed_methods
        return methods


class ScheduleDetail(RetrieveUpdateDestroyAPIView):
    model = Schedule
    serializer_class = ScheduleSerializer
