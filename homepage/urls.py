from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from .views import (
        index_page_view, 
        gallery_page_view, 
        GalleryImageListAPIView
    )



urlpatterns = [
    path("", index_page_view, name="index"),
    path("gallery/", gallery_page_view, name="gallery"),
    path("api/gallery/", GalleryImageListAPIView.as_view(), name="api-gallery"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)