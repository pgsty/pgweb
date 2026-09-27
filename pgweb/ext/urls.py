"""/ext/: the catalogue and redirects for former indexes and filter pages. /e/ is urls_e.py."""

from django.urls import path

from . import views, cloud_views

app_name = 'ext'
urlpatterns = [
    path('', views.browse, name='home'),
    path('cloud/', cloud_views.matrix, name='cloud'),
    path('cloud/evidence/', cloud_views.evidence, name='cloud_evidence'),
    path('cloud/<slug:service_id>/', cloud_views.matrix, name='cloud_service'),
    path('list/', views.index, name='list'),
    path('sitemap.xml', views.sitemap, name='sitemap'),
    # /ext/list/<dimension>/ was the first index URL; keep it as a redirect.
    path('list/<str:dimension>/', views.legacy_index, name='legacy_index'),
    # A dimension index (/ext/license/), a category (/ext/gis/), or an old
    # detail URL (/ext/vector/ now lives at /e/vector/).
    path('<str:segment>/', views.section, name='section'),
    path('<str:dimension>/<path:value>/', views.value, name='value'),
]
