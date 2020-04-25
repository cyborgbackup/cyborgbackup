from django.conf.urls import include, url
from rest_framework_simplejwt import views as jwt_views

from cyborgbackup.api.swagger import SwaggerSchemaView

from cyborgbackup.api.views import (
    UserList,
    UserDetail,
    ClientList,
    ClientDetail,
    ScheduleList,
    ScheduleDetail,
    RepositoryList,
    RepositoryDetail,
    CatalogList,
    CatalogDetail,
    PolicyList,
    PolicyDetail,
    PolicyLaunch,
    PolicyCalendar,
    PolicyVMModule,
    Stats,
    JobEventList,
    JobEventDetail,
    JobList,
    JobDetail,
    JobStart,
    JobCancel,
    JobRelaunch,
    JobJobEventsList,
    JobStdout,
    SettingList,
    SettingDetail,
    ApiRootView,
    ApiV1RootView,
    ApiV1PingView,
    ApiV1ConfigView,
    AuthView,
    UserMeList,
    CyborgTokenObtainPairView,
    RestoreLaunch
)

from cyborgbackup.elasticsearch.views import ESCatalogViewSet

from cyborgbackup.api.generics import (
    LoggedLoginView,
    LoggedLogoutView,
)


user_urls = [
    url(r'^$', UserList.as_view(), name='user_list'),
    url(r'^(?P<pk>[0-9]+)/$', UserDetail.as_view(), name='user_detail'),
]

client_urls = [
    url(r'^$', ClientList.as_view(), name='client_list'),
    url(r'^(?P<pk>[0-9]+)/$', ClientDetail.as_view(), name='client_detail'),
]

schedule_urls = [
    url(r'^$', ScheduleList.as_view(), name='schedule_list'),
    url(r'^(?P<pk>[0-9]+)/$', ScheduleDetail.as_view(), name='schedule_detail'),
]

repository_urls = [
    url(r'^$', RepositoryList.as_view(), name='repository_list'),
    url(r'^(?P<pk>[0-9]+)/$', RepositoryDetail.as_view(), name='repository_detail'),
]

catalog_urls = [
    url(r'^$', CatalogList.as_view(), name='catalog_list'),
    url(r'^(?P<pk>[0-9]+)/$', CatalogDetail.as_view(), name='catalog_detail'),
]

policy_urls = [
    url(r'^$', PolicyList.as_view(), name='policy_list'),
    url(r'^(?P<pk>[0-9]+)/$', PolicyDetail.as_view(), name='policy_detail'),
    url(r'^(?P<pk>[0-9]+)/launch/$', PolicyLaunch.as_view(), name='policy_launch'),
    url(r'^(?P<pk>[0-9]+)/calendar/$', PolicyCalendar.as_view(), name='policy_calendar'),
    url(r'^vmmodule/$', PolicyVMModule.as_view(), name='policy_vmmodule'),
]

stats_urls = [
    url(r'^$', Stats.as_view(), name='stats'),
]

job_events_urls = [
    url(r'^$', JobEventList.as_view(), name='job_event_list'),
    url(r'^(?P<pk>[0-9]+)/$', JobEventDetail.as_view(), name='job_event_detail'),
]

job_urls = [
    url(r'^$', JobList.as_view(), name='job_list'),
    url(r'^(?P<pk>[0-9]+)/$', JobDetail.as_view(), name='job_detail'),
    url(r'^(?P<pk>[0-9]+)/start/$', JobStart.as_view(), name='job_start'),
    url(r'^(?P<pk>[0-9]+)/cancel/$', JobCancel.as_view(), name='job_cancel'),
    url(r'^(?P<pk>[0-9]+)/relaunch/$', JobRelaunch.as_view(), name='job_relaunch'),
    url(r'^(?P<pk>[0-9]+)/job_events/$', JobJobEventsList.as_view(), name='job_job_events_list'),
    url(r'^(?P<pk>[0-9]+)/stdout/$', JobStdout.as_view(), name='job_stdout'),
]

setting_urls = [
    url(r'^$', SettingList.as_view(), name='setting_list'),
    url(r'^(?P<pk>[0-9]+)/$', SettingDetail.as_view(), name='setting_detail'),
]

restore_urls = [
    url(r'^$', RestoreLaunch.as_view(), name='restore_launch'),
]

app_name = 'api'

v1_urls = [
    url(r'^$', ApiV1RootView.as_view(), name='api_v1_root_view'),
    url(r'^ping/$', ApiV1PingView.as_view(), name='api_v1_ping_view'),
    url(r'^config/$', ApiV1ConfigView.as_view(), name='api_v1_config_view'),
    url(r'^auth/$', AuthView.as_view(), name="auth"),
    url(r'^me/$', UserMeList.as_view(), name='user_me_list'),
    url(r'^users/', include(user_urls)),
    url(r'^jobs/', include(job_urls)),
    url(r'^job_events/', include(job_events_urls)),
    url(r'^settings/', include(setting_urls)),
    url(r'^clients/', include(client_urls)),
    url(r'^schedules/', include(schedule_urls)),
    url(r'^repositories/', include(repository_urls)),
    url(r'^policies/', include(policy_urls)),
    url(r'^restore/', include(restore_urls)),
    url(r'^catalogs/', include(catalog_urls)),
    url(r'^stats/', include(stats_urls)),
    url(r'^escatalogs/', ESCatalogViewSet.as_view({'get': 'list'}), name='escatalog_list')
]

urlpatterns = [
    url(r'^$', ApiRootView.as_view(), name='api_root_view'),
    url(r'^(?P<version>(v1))/', include(v1_urls)),
    url(r'^token/obtain/$', CyborgTokenObtainPairView.as_view(), name='token_create'),  # override sjwt stock token
    url(r'^token/refresh/$', jwt_views.TokenRefreshView.as_view(), name='token_refresh'),
    url(r'^password_reset/', include('django_rest_passwordreset.urls', namespace='password_reset')),
    url(r'^login/$', LoggedLoginView.as_view(
        template_name='rest_framework/login.html',
        extra_context={'inside_login_context': True}
    ), name='login'),
    url(r'^logout/$', LoggedLogoutView.as_view(
        next_page='/api/', redirect_field_name='next'
    ), name='logout'),
    url(r'^swagger/$', SwaggerSchemaView.as_view(), name='swagger_view'),
]
