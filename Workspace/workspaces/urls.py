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
    path('p/<int:page_pk>/blocks/', views.block_list, name='block_list'),
    path('blocks/<int:pk>/', views.block_detail, name='block_detail'),
    path('blocks/<int:pk>/delete/', views.block_delete, name='block_delete'),
    path('blocks/<int:pk>/move/', views.block_move, name='block_move'),
    path('blocks/<int:pk>/reorder/', views.block_reorder, name='block_reorder'),
    path('w/<int:workspace_id>/members/', views.members, name='members'),
    path('w/<int:workspace_id>/members/add/', views.member_add, name='member_add'),
    path('w/<int:workspace_id>/members/<int:pk>/role/', views.member_role, name='member_role'),
    path('w/<int:workspace_id>/members/<int:pk>/remove/', views.member_remove, name='member_remove'),
    path('p/<int:page_pk>/subpages/new/', views.subpage_create, name='subpage_create'),
    path('sidebar/', views.sidebar_fragment, name='sidebar'),
    path('p/<int:pk>/title/', views.page_title_edit, name='page_title_edit'),
    path('p/<int:pk>/rename/', views.page_rename, name='page_rename'),
    path('p/<int:pk>/delete/', views.page_delete, name='page_delete'),
]