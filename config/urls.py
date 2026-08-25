"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import path, include

from dashboard.views import dashboard_page

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard_page, name='dashboard-page'),
    path('api/', include('dashboard.urls')),
]
