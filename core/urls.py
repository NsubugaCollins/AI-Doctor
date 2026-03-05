from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('apps.consultations.urls')),
    path('lab/', include('apps.consultations.lab_urls')),
    path('accounts/', include('allauth.urls')),
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
    path('consultation/<str:consultation_id>/', 
         TemplateView.as_view(template_name='consultation.html'), 
         name='consultation-detail'),
    path('dashboard/', 
         TemplateView.as_view(template_name='dashboard.html'), 
         name='dashboard'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])