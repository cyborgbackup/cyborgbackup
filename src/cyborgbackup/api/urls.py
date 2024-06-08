from django.conf.urls import include
from django.urls import re_path
from rest_framework_simplejwt import views as jwt_views

from .views.api import ApiRootView, ApiV1RootView, ApiV1PingView, ApiV1ConfigView, AuthView, CyborgTokenObtainPairView
from .views.catalogs import CatalogList, CatalogDetail, MongoCatalog, RestoreLaunch
from .views.clients import ClientList, ClientDetail
from .views.generics import LoggedLoginView, LoggedLogoutView
from .views.jobs import JobStart, JobCancel, JobRelaunch, JobJobEventsList, JobStdout, JobList, JobEventDetail, \
    JobEventList, JobDetail
from .views.policies import PolicyList, PolicyModule, PolicyDetail, PolicyLaunch, PolicyCalendar, PolicyVMModule
from .views.repositories import RepositoryList, RepositoryDetail
from .views.schedules import ScheduleList, ScheduleDetail
from .views.settings import SettingList, SettingGetPublicSsh, SettingDetail, SettingGenerateSsh
from .views.stats import Stats
from .views.users import UserList, UserDetail, UserMeList

user_urls = [
    re_path(r'^$', UserList.as_view(), name='user_list'),
    re_path(r'^(?P<pk>[0-9]+)/$', UserDetail.as_view(), name='user_detail'),
]

client_urls = [
    re_path(r'^$', ClientList.as_view(), name='client_list'),
    re_path(r'^(?P<pk>[0-9]+)/$', ClientDetail.as_view(), name='client_detail'),
]

schedule_urls = [
    re_path(r'^$', ScheduleList.as_view(), name='schedule_list'),
    re_path(r'^(?P<pk>[0-9]+)/$', ScheduleDetail.as_view(), name='schedule_detail'),
]

repository_urls = [
    re_path(r'^$', RepositoryList.as_view(), name='repository_list'),
    re_path(r'^(?P<pk>[0-9]+)/$', RepositoryDetail.as_view(), name='repository_detail'),
]

catalog_urls = [
    re_path(r'^$', CatalogList.as_view(), name='catalog_list'),
    re_path(r'^(?P<pk>[0-9]+)/$', CatalogDetail.as_view(), name='catalog_detail'),
]

policy_urls = [
    re_path(r'^$', PolicyList.as_view(), name='policy_list'),
    re_path(r'^(?P<pk>[0-9]+)/$', PolicyDetail.as_view(), name='policy_detail'),
    re_path(r'^(?P<pk>[0-9]+)/launch/$', PolicyLaunch.as_view(), name='policy_launch'),
    re_path(r'^(?P<pk>[0-9]+)/calendar/$', PolicyCalendar.as_view(), name='policy_calendar'),
    re_path(r'^vmmodule/$', PolicyVMModule.as_view(), name='policy_vmmodule'),
    re_path(r'^module/(?P<module>[\w-]+)/(?P<client>[0-9]+)/$', PolicyModule.as_view(), name='policy_module'),
]

stats_urls = [
    re_path(r'^$', Stats.as_view(), name='stats'),
]

job_events_urls = [
    re_path(r'^$', JobEventList.as_view(), name='job_event_list'),
    re_path(r'^(?P<pk>[0-9]+)/$', JobEventDetail.as_view(), name='job_event_detail'),
]

job_urls = [
    re_path(r'^$', JobList.as_view(), name='job_list'),
    re_path(r'^(?P<pk>[0-9]+)/$', JobDetail.as_view(), name='job_detail'),
    re_path(r'^(?P<pk>[0-9]+)/start/$', JobStart.as_view(), name='job_start'),
    re_path(r'^(?P<pk>[0-9]+)/cancel/$', JobCancel.as_view(), name='job_cancel'),
    re_path(r'^(?P<pk>[0-9]+)/relaunch/$', JobRelaunch.as_view(), name='job_relaunch'),
    re_path(r'^(?P<pk>[0-9]+)/job_events/$', JobJobEventsList.as_view(), name='job_job_events_list'),
    re_path(r'^(?P<pk>[0-9]+)/stdout/$', JobStdout.as_view(), name='job_stdout'),
]

setting_urls = [
    re_path(r'^$', SettingList.as_view(), name='setting_list'),
    re_path(r'^(?P<pk>[0-9]+)/$', SettingDetail.as_view(), name='setting_detail'),
    re_path(r'^generate_ssh/$', SettingGenerateSsh.as_view(), name='setting_generate_ssh'),
    re_path(r'^get_ssh_publickey/$', SettingGetPublicSsh.as_view(), name='setting_get_ssh_publickey'),
]

restore_urls = [
    re_path(r'^$', RestoreLaunch.as_view(), name='restore_launch'),
]

app_name = 'api'

v1_urls = [
    re_path(r'^$', ApiV1RootView.as_view(), name='api_v1_root_view'),
    re_path(r'^ping/$', ApiV1PingView.as_view(), name='api_v1_ping_view'),
    re_path(r'^config/$', ApiV1ConfigView.as_view(), name='api_v1_config_view'),
    re_path(r'^auth/$', AuthView.as_view(), name="auth"),
    re_path(r'^me/$', UserMeList.as_view(), name='user_me_list'),
    re_path(r'^users/', include(user_urls)),
    re_path(r'^jobs/', include(job_urls)),
    re_path(r'^job_events/', include(job_events_urls)),
    re_path(r'^settings/', include(setting_urls)),
    re_path(r'^clients/', include(client_urls)),
    re_path(r'^schedules/', include(schedule_urls)),
    re_path(r'^repositories/', include(repository_urls)),
    re_path(r'^policies/', include(policy_urls)),
    re_path(r'^restore/', include(restore_urls)),
    re_path(r'^catalogs/', include(catalog_urls)),
    re_path(r'^stats/', include(stats_urls)),
    re_path(r'^escatalogs/', MongoCatalog.as_view(), name='escatalog_list')
]

urlpatterns = [
    re_path(r'^$', ApiRootView.as_view(), name='api_root_view'),
    re_path(r'^v1/', include(v1_urls)),
    re_path(r'^token/obtain/$', CyborgTokenObtainPairView.as_view(), name='token_create'),  # override sjwt stock token
    re_path(r'^token/refresh/$', jwt_views.TokenRefreshView.as_view(), name='token_refresh'),
    re_path(r'^password_reset/', include('django_rest_passwordreset.urls', namespace='password_reset')),
    re_path(r'^login/$', LoggedLoginView.as_view(
        template_name='rest_framework/login.html',
        extra_context={'inside_login_context': True}
    ), name='login'),
    re_path(r'^logout/$', LoggedLogoutView.as_view(
        next_page='/api/', redirect_field_name='next'
    ), name='logout'),
]
