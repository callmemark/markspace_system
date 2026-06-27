from django.db import models


class GalleryImage(models.Model):
    title_jp = models.CharField("Japanese Title", max_length=100, blank=True)
    title_en = models.CharField("English Subtitle", max_length=100, blank=True)
    image = models.ImageField(upload_to='homepage/gallery/')
    category = models.CharField(
        max_length=30,
        choices=[
            ("design", "Design"),
            ("3D Models", "3D Models"),
            ("photography", "Photography"),
        ],
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first")

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "Gallery Image"
        verbose_name_plural = "Gallery Images"

    def __str__(self):
        return self.title_jp or f"Image {self.pk}"