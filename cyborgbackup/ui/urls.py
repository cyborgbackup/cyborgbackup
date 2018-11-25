from django.conf.urls import url
from django.views.generic.base import TemplateView, RedirectView
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.contrib.staticfiles import views
from django.urls import re_path

app_name = 'ui'


class IndexView(TemplateView):

    template_name = 'ui/index.html'

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)
        # Add any additional context info here.
        return context

index = IndexView.as_view()

urlpatterns = [
    url(r'^$', index, name='index'),
    re_path(r'^(?P<path>.*)$', views.serve),
]
