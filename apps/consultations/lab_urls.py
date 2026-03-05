from django.urls import path
from . import views

urlpatterns = [
    path("", views.lab_dashboard, name="lab_dashboard"),
    path("consultation/<uuid:consultation_id>/upload/", views.lab_upload_results, name="lab_upload_results"),
]

