"""Mounted under /docs/: the 百科 columns. Unbuilt columns redirect to their origin site."""

from django.urls import path
from django.views.generic import RedirectView

from . import views
from .columns import COLUMNS

app_name = 'wiki'
urlpatterns = [
    path('sqlstate/', views.errcode_index, name='errcode'),
    # 通配放最后，免得遮蔽具名路由。
    path('sqlstate/<str:sqlstate>/', views.errcode_detail, name='errcode_detail'),
] + [
    path('{}/'.format(column['slug']), RedirectView.as_view(url=column['origin'], permanent=False),
         name=column['slug'])
    for column in COLUMNS if not column['live']
]
