from django.urls import path

from . import views

urlpatterns = [
    path('p/<int:pk>/', views.page_detail, name='page_detail'),
    path('w/new/', views.workspace_create, name='workspace_create'),
    path('w/<int:workspace_id>/pages/new/', views.page_create, name='page_create'),
    path('blocks/<int:pk>/toggle/', views.block_toggle, name='block_toggle'),
    path('blocks/<int:pk>/edit/', views.block_edit, name='block_edit'),
    path('blocks/<int:pk>/update/', views.block_update, name='block_update'),
    path('p/<int:page_pk>/blocks/new/', views.block_create, name='block_create'),
    path('blocks/<int:pk>/delete/', views.block_delete, name='block_delete'),
    path('blocks/<int:pk>/move/', views.block_move, name='block_move'),
    path('blocks/<int:pk>/reorder/', views.block_reorder, name='block_reorder'),
]