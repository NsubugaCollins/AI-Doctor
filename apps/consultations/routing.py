"""
WebSocket URL routing
"""

from django.urls import re_path
from apps.consultations import consumers

websocket_urlpatterns = [
    re_path(r'ws/consultation/(?P<consultation_id>[^/]+)/?$', consumers.ConsultationConsumer.as_asgi())
]
