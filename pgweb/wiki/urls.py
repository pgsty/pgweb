"""Mounted under /docs/: the 百科 columns. Unbuilt columns redirect to their origin site."""

from django.urls import path, re_path
from django.views.generic import RedirectView

from . import views
from .columns import COLUMNS

app_name = 'wiki'
urlpatterns = [
    path('sql/', views.sqlcmd_index, name='sqlcmd'),
    path('sql/changes/', views.sqlcmd_changes_root, name='sqlcmd_changes_root'),
    re_path(r'^sql/changes/(?P<major>\d+(?:\.\d+)?)/$', views.sqlcmd_changes, name='sqlcmd_changes'),
    # 大写形式也接受，随后 301 到小写规范地址。
    re_path(r'^sql/(?P<slug>(?i:[a-z][a-z0-9-]*))/$', views.sqlcmd_detail, name='sqlcmd_detail'),
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
    path('waitevent/', views.waitevent_index, name='waitevent'),
    # 同理：changes/ 排在 <type>/<name>/ 之前，否则被类型的通配吃掉。
    path('waitevent/changes/', views.waitevent_changes_root, name='waitevent_changes_root'),
    re_path(r'^waitevent/changes/(?P<major>\d+(?:\.\d+)?)/$', views.waitevent_changes,
            name='waitevent_changes'),
    # 类型只有九个，大小写都放进来，视图里对不上规范 slug 就 404。
    re_path(r'^waitevent/(?P<type>[A-Za-z]{2,12})/(?P<name>[A-Za-z0-9_.-]+)/$',
            views.waitevent_detail, name='waitevent_detail'),
] + [
    path('{}/'.format(column['slug']), RedirectView.as_view(url=column['origin'], permanent=False),
         name=column['slug'])
    for column in COLUMNS if not column['live'] and column['origin']
]
