from django.contrib import admin
from django.utils.html import format_html
from .models import PropertyListing, PropertyImage

class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 0
    readonly_fields = ['scraped_at']
    fields = ['image_url', 'image_title', 'image_order', 'is_primary', 'scraped_at']

@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display = ['property', 'image_order', 'is_primary', 'image_title', 'scraped_at']
    list_filter = ['is_primary', 'scraped_at']
    search_fields = ['property__title', 'image_title', 'image_url']
    readonly_fields = ['scraped_at']
    list_per_page = 25

@admin.register(PropertyListing)
class PropertyListingAdmin(admin.ModelAdmin):
    list_display = ['title', 'price', 'property_type', 'bedrooms', 'bathrooms', 'size', 'image_count', 'date_added', 'scraping_status']
    list_filter = ['bedrooms', 'bathrooms', 'property_type', 'scraping_status', 'date_added']
    search_fields = ['title', 'description', 'key_features']
    readonly_fields = ['external_id', 'scraped_at', 'last_updated', 'scraping_status', 'scraping_error']
    list_per_page = 25
    inlines = [PropertyImageInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('external_id', 'title', 'listing_url', 'property_type')
        }),
        ('Pricing Information', {
            'fields': ('price', 'price_numeric')
        }),
        ('Property Details', {
            'fields': ('bedrooms', 'bathrooms', 'size')
        }),
        ('Content', {
            'fields': ('description', 'key_features')
        }),
        ('Dates', {
            'fields': ('date_added',)
        }),
        ('Scraping Metadata', {
            'fields': ('scraped_at', 'last_updated', 'scraping_status', 'scraping_error'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-scraped_at')
