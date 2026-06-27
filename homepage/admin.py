from django.contrib import admin
from .models import GalleryImage

@admin.register(GalleryImage)
class GalleryImageAdmin(admin.ModelAdmin):
    list_display = ("title_jp", "title_en", "category", "order", "created_at")
    list_editable = ("order", "category")
    search_fields = ("title_jp", "title_en")
    list_filter = ("category",)