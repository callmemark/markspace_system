from django.urls import path
from .views import FloodDepthView, FloodDepthGeoJSONView

urlpatterns = [
    path('api/flood-depth/', FloodDepthView.as_view(), name='flood-depth'),
]