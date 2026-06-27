from django.shortcuts import render
from rest_framework.generics import ListAPIView

from .models import GalleryImage
from .serializers import GalleryImageSerializer






def index_page_view(request):
    return render(request, 'pages/landing.html')

def gallery_page_view(request):
    return render(request, 'pages/gallery.html')



class GalleryImageListAPIView(ListAPIView):
    queryset = GalleryImage.objects.all()
    serializer_class = GalleryImageSerializer