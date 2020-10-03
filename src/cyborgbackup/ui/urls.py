from django.conf.urls import url
from django.views.generic.base import TemplateView
from django.contrib.staticfiles import views
from django.urls import re_path


from cyborgbackup.main.utils.tasks import catalog_is_running, celery_worker_is_running
from cyborgbackup.main.models import Job, Policy, Repository, Schedule, Client

app_name = 'ui'


class IndexView(TemplateView):

    template_name = 'ui/index.html'

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)
        context['celery'] = celery_worker_is_running()
        context['catalog'] = catalog_is_running()
        context['jobs'] = len(Job.objects.filter())
        context['policies'] = len(Policy.objects.filter())
        context['clients'] = len(Client.objects.filter())
        context['schedules'] = len(Schedule.objects.filter())
        context['repositories'] = len(Repository.objects.filter())
        return context


index = IndexView.as_view()

urlpatterns = [
    url(r'^$', index, name='index'),
    re_path(r'^(?P<path>.*)$', views.serve),
]
