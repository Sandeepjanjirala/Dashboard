from django.urls import path

from dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("dashboard/filters/", views.filters_view, name="filters"),
    path("dashboard/ask-ai/", views.ask_ai_view, name="ask-ai"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
]
