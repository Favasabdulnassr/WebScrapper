from django.urls import path
from . import views

urlpatterns = [
    path('api/scrape/', views.trigger_scraping, name='trigger_scraping'),
    path('api/properties/', views.get_properties, name='get_properties'),
    path('api/stats/', views.get_stats, name='get_stats'),
]
