"""/wiki/: 百科. Each column mounts its own routes under /wiki/<slug>/."""

from django.urls import path

from . import views

app_name = 'wiki'
urlpatterns = [
    path('', views.home, name='home'),
    path('errcode/', views.errcode_index, name='errcode'),
    # 通配放最后，免得遮蔽具名路由。
    path('errcode/<str:sqlstate>/', views.errcode_detail, name='errcode_detail'),
]
