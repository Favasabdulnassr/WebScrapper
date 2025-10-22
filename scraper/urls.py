from django.urls import path
from . import views

urlpatterns = [
    path('api/scrape/', views.trigger_scraping, name='trigger_scraping'),
]
