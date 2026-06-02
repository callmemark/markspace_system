from django.urls import path
from .views import FloodDepthView

urlpatterns = [
    path('api/flood-depth/', FloodDepthView.as_view(), name='flood-depth'),
]