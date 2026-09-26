from django.urls import path

from . import views

app_name = 'hacker'
urlpatterns = [
    path('', views.index, name='index'),
    path('<slug:slug>/avatar/', views.avatar, name='avatar'),
    path('<slug:slug>/', views.detail, name='detail'),
]
