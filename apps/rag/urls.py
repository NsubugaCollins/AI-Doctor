from django.urls import path
from . import views

app_name = 'rag'

urlpatterns = [
    path('upload/', views.upload_pdf, name='upload-pdf'),
    path('search/', views.search_pdfs, name='search-pdfs'),
    path('sources/', views.list_sources, name='pdf-sources'),
]