from django.contrib import admin
from django.utils.html import format_html
from .models import PropertyListing, PropertyImage


admin.site.register(PropertyListing)
admin.site.register(PropertyImage)