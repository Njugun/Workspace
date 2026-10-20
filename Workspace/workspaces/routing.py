from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/pages/<int:page_id>/', consumers.PageConsumer.as_asgi()),
]
