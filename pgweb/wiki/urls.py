"""Mounted under /docs/: the 百科 columns. Unbuilt columns redirect to their origin site."""

from django.urls import path, re_path
from django.views.generic import RedirectView

from . import views
from .columns import COLUMNS

app_name = 'wiki'
urlpatterns = [
    path('sqlstate/', views.errcode_index, name='errcode'),
    # 通配放最后，免得遮蔽具名路由。
    path('sqlstate/<str:sqlstate>/', views.errcode_detail, name='errcode_detail'),
    path('catalog/', views.catalog_index, name='catalog'),
    # changes/ 必须排在 <name>/ 之前，否则被关系名的通配吃掉。
    path('catalog/changes/', views.catalog_changes_root, name='catalog_changes_root'),
    re_path(r'^catalog/changes/(?P<major>\d+(?:\.\d+)?)/$', views.catalog_changes,
            name='catalog_changes'),
    re_path(r'^catalog/(?P<name>pg_[a-z0-9_]+)/$', views.catalog_detail, name='catalog_detail'),
    path('guc/', views.guc_index, name='guc'),
    # 同理：changes/ 排在参数名的通配之前。
    path('guc/changes/', views.guc_changes_root, name='guc_changes_root'),
    re_path(r'^guc/changes/(?P<major>\d+(?:\.\d+)?)/$', views.guc_changes, name='guc_changes'),
    re_path(r'^guc/(?P<name>[A-Za-z][A-Za-z0-9_]*)/$', views.guc_detail, name='guc_detail'),
] + [
    path('{}/'.format(column['slug']), RedirectView.as_view(url=column['origin'], permanent=False),
         name=column['slug'])
    for column in COLUMNS if not column['live']
]
