from django.http import JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
from .models import PropertyListing
from .tasks import scrape_properties_task


@csrf_exempt
@require_POST
def trigger_scraping(request):
    """Simple endpoint to trigger scraping"""
    try:
        data = json.loads(request.body)
        search_url = data.get('search_url', 'https://www.rightmove.co.uk/property-for-sale/find.html?searchLocation=London&useLocationIdentifier=true&locationIdentifier=REGION%5E87490&_includeSSTC=on&index=0&sortType=2&channel=BUY&transactionType=BUY&displayLocationIdentifier=London-87490.html&radius=40.0')
        max_pages = data.get('max_pages', 5)
        
        task = scrape_properties_task.delay(search_url, max_pages)
        
        return JsonResponse({
            'status': 'success',
            'message': f'Scraping started for {search_url}',
            'task_id': task.id
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
