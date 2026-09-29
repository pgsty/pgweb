"""Mounted under /wiki/: the 百科 columns. Unbuilt columns redirect to their origin site."""

from django.urls import path, re_path
from django.views.generic import RedirectView

from . import topic_views, views
from .columns import COLUMNS

app_name = 'wiki'
urlpatterns = [
    path('', views.home, name='reference'),
    path('lock/', views.lock_index, name='lock'),
    path('lock/<slug:slug>/', views.lock_detail, name='lock_detail'),
    path('sql/', views.sqlcmd_index, name='sqlcmd'),
    path('sql/changes/', views.sqlcmd_changes_root, name='sqlcmd_changes_root'),
    re_path(r'^sql/changes/(?P<major>\d+(?:\.\d+)?)/$', views.sqlcmd_changes, name='sqlcmd_changes'),
    # The early development snapshot called WAIT "WAIT FOR"; preserve shared links.
    re_path(r'^sql/[Ww][Aa][Ii][Tt]-?[Ff][Oo][Rr]/$', RedirectView.as_view(
        url='/wiki/sql/wait/', permanent=True, query_string=True)),
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
    path('func/', views.func_index, name='func'),
    # 同理：changes/ 排在函数名的通配之前。
    path('func/changes/', views.func_changes_root, name='func_changes_root'),
    re_path(r'^func/changes/(?P<major>\d+(?:\.\d+)?)/$', views.func_changes, name='func_changes'),
    # 规范地址是小写连字符（to-char）；函数名本身（to_char、TO_CHAR）也接受，
    # 随后由视图 301 到规范地址。
    re_path(r'^func/(?P<slug>(?i:[a-z][a-z0-9_-]*))/$', views.func_detail, name='func_detail'),
] + [
    route
    for kind in ('hook', 'relopts', 'role', 'oid')
    for route in (
        path(kind + '/', topic_views.index, {'kind': kind}, name=kind),
        path(kind + '/<slug:slug>/', topic_views.detail, {'kind': kind}, name=kind + '_detail'),
    )
] + [
    path('{}/'.format(column['slug']), RedirectView.as_view(url=column['origin'], permanent=False),
         name=column['slug'])
    for column in COLUMNS if not column['live'] and column['origin']
]


from . import data_types, encyclopedia, index_method_views, version_views
from .topic_registry import DOMAIN_KEYS
urlpatterns += [
    path('type/', data_types.index, name='type'),
    path('type/<str:slug>/', data_types.detail, name='type_detail'),
    path('indexam/', index_method_views.index, name='indexam'),
    path('indexam/changes/', index_method_views.changes, name='indexam_changes_root'),
    path('indexam/changes/<str:major>/', index_method_views.changes, name='indexam_changes'),
    path('indexam/<str:slug>/', index_method_views.detail, name='indexam_detail'),
    path('versions/', version_views.index, name='versions'),
    path('versions/<str:branch>/', version_views.detail, name='versions_detail'),
]
for topic_kind in DOMAIN_KEYS:
    urlpatterns += [
        path(topic_kind + '/', encyclopedia.index, {'kind': topic_kind}, name=topic_kind),
        path(topic_kind + '/changes/', encyclopedia.changes, {'kind': topic_kind}, name=topic_kind + '_changes_root'),
        path(topic_kind + '/changes/<str:major>/', encyclopedia.changes, {'kind': topic_kind}, name=topic_kind + '_changes'),
        path(topic_kind + '/<str:slug>/', encyclopedia.detail, {'kind': topic_kind}, name=topic_kind + '_detail'),
    ]
