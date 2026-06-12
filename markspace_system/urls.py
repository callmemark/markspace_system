
from django.contrib import admin
from django.urls import path, include  

admin.site.site_header = "Admin Panel"
admin.site.site_title = "Admin Panel"
admin.site.index_title = "Welcom Back Mark!"

urlpatterns = [
    path('', include('homepage.urls')),
    path('admin/', admin.site.urls),
    path('iamspace/', include('iam_system.urls')), 
    path('flood-data/', include('flood_forecasting.urls'))
]
