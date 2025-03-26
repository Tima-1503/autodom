from django.urls import path
from . import views

urlpatterns = [
    path('', views.get_workers, name='get_workers'),
    path('works/', views.get_works, name='get_works'),
    path('pause/', views.make_pause, name='make_pause'),
    path('cars/<str:executor>/', views.get_cars, name='get_cars'),
    path('get_orders/', views.get_orders, name='get_orders'),
]