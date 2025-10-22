from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class PropertyImage(models.Model):
    property = models.ForeignKey('PropertyListing', on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField(max_length=1000)
    image_title = models.CharField(max_length=200, blank=True)
    image_order = models.IntegerField(default=0, help_text="Order of image in the property's image list")
    is_primary = models.BooleanField(default=False, help_text="Whether this is the primary/main image")
    scraped_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['image_order', 'scraped_at']
        indexes = [
            models.Index(fields=['property', 'image_order']),
            models.Index(fields=['is_primary']),
        ]
        unique_together = ['property', 'image_url']  
    
    def __str__(self):
        return f"{self.property.title} - Image {self.image_order}"

class PropertyListing(models.Model):
    # Essential Information
    external_id = models.CharField(max_length=64, unique=True)
    listing_url = models.URLField(max_length=1000, unique=True)
    title = models.CharField(max_length=512, blank=True)
    
    # Pricing Information
    price = models.CharField(max_length=128, blank=True)
    price_numeric = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Property Details
    property_type = models.CharField(max_length=100, blank=True)  # "End of Terrace", "Flat", "House", etc.
    bedrooms = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(20)])
    bathrooms = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(20)])
    size = models.CharField(max_length=100, blank=True)  # "1,200 sq ft", "Ask agent", etc.
    
    # Content
    description = models.TextField(blank=True)
    key_features = models.JSONField(default=list, blank=True)  # ["STARTER HOME", "OPEN PLAN", etc.]
    
    # Dates
    date_added = models.DateField(null=True, blank=True)
    
    # Scraping Metadata
    scraped_at = models.DateTimeField(auto_now=True)
    last_updated = models.DateTimeField(auto_now_add=True)
    scraping_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('scraping', 'Scraping'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ])
    scraping_error = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-scraped_at']
        indexes = [
            models.Index(fields=['external_id']),
            models.Index(fields=['price_numeric']),
            models.Index(fields=['bedrooms']),
            models.Index(fields=['property_type']),
            models.Index(fields=['scraped_at']),
        ]

    def __str__(self):
        return f"{self.external_id} - {self.title or 'Unknown Property'}"
    
    @property
    def has_images(self):
        return self.images.exists()
    
    @property
    def image_count(self):
        return self.images.count()
    
    @property
    def primary_image(self):
        """Get the primary image URL"""
        primary_img = self.images.filter(is_primary=True).first()
        if primary_img:
            return primary_img.image_url
        # Fallback to first image if no primary is set
        first_img = self.images.first()
        return first_img.image_url if first_img else None
    
    @property
    def image_urls(self):
        """Get all image URLs as a list (for backward compatibility)"""
        return list(self.images.values_list('image_url', flat=True))
