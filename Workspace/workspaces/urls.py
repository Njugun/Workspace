from django.urls import path

from . import views

urlpatterns = [
    path('p/<int:pk>/', views.page_detail, name='page_detail'),
]
