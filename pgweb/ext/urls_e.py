"""/e/<name>/: one extension."""

from django.urls import path

from . import views

app_name = 'e'
urlpatterns = [
    path('', views.detail_root),
    path('<str:name>/', views.detail, name='detail'),
]
