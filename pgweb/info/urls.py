"""/info/: the 博览 column. Named routes come before the day pattern."""

from django.urls import path

from . import views
from .feeds import InfoFeed

app_name = 'info'
urlpatterns = [
    path('', views.stream, name='stream'),
    path('daily/', views.daily, name='daily'),
    path('archive/', views.archive, name='archive'),
    path('search/', views.search, name='search'),
    path('rss/', InfoFeed(), name='rss'),
    path('<str:datestr>/', views.day, name='day'),
]
