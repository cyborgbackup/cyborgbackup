"""cyborgbackup URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.urls import include, re_path, path

from cyborgbackup.api.swagger import CyBorgBackupSchemaView

app_name = 'cyborgbackup'
urlpatterns = [
    re_path(r'^admin/', admin.site.urls),
    re_path(r'^api/', include((
        'cyborgbackup.api.urls',
        'cyborgbackup'
    ), namespace='api')),
    path('doc/swagger<format>', CyBorgBackupSchemaView.without_ui(cache_timeout=0), name='schema_json'),
    path('doc/swagger/', CyBorgBackupSchemaView.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('doc/redoc/', CyBorgBackupSchemaView.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    re_path(r'', include('cyborgbackup.ui.urls', namespace='ui')),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [
                      re_path(r'^__debug__/', include(debug_toolbar.urls)),
                  ] + urlpatterns
