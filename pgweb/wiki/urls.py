"""/wiki/: 百科. Each column mounts its own routes under /wiki/<slug>/."""

from django.urls import path

from . import views

app_name = 'wiki'
urlpatterns = [
    path('', views.home, name='home'),
]
