# apps/consultations/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('new-consultation/', views.new_consultation, name='new_consultation'),
    path('consultations/start/', views.start_consultation_api, name='start_consultation'),
    path('consultation/<uuid:consultation_id>/', views.consultation_detail, name='consultation_detail'),
    path('consultation/<uuid:consultation_id>/add-symptoms/', views.add_symptoms_ui, name='add_symptoms'),
    path('consultation/<uuid:consultation_id>/status/', views.consultation_status_api, name='consultation_status'),
]