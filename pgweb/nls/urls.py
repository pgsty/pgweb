"""/nls/: 消息翻译. The page plus the JSON API the page talks to."""

from django.urls import path

from . import views

app_name = 'nls'
urlpatterns = [
    path('', views.index, name='index'),
    path('api/bootstrap/', views.api_bootstrap, name='api_bootstrap'),
    path('api/component/', views.api_component, name='api_component'),
    path('api/references/', views.api_references, name='api_references'),
    path('api/decide/', views.api_decide, name='api_decide'),
    path('api/save/', views.api_save, name='api_save'),
    path('api/export/', views.api_export, name='api_export'),
]
