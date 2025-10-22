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

def get_properties(request):
    """Get properties data as JSON"""
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        properties = PropertyListing.objects.all().order_by('-scraped_at')
        paginator = Paginator(properties, page_size)
        page_obj = paginator.get_page(page)
        
        properties_data = []
        for prop in page_obj:
            properties_data.append({
                'id': prop.id,
                'title': prop.title,
                'price': prop.price,
                'property_type': prop.property_type,
                'bedrooms': prop.bedrooms,
                'bathrooms': prop.bathrooms,
                'size': prop.size,
                'description': prop.description,
                'key_features': prop.key_features,
                'image_urls': prop.image_urls,
                'image_count': prop.image_count,
                'date_added': prop.date_added.isoformat() if prop.date_added else None,
                'scraped_at': prop.scraped_at.isoformat() if prop.scraped_at else None,
            })
        
        return JsonResponse({
            'status': 'success',
            'data': {
                'properties': properties_data,
                'pagination': {
                    'current_page': page_obj.number,
                    'total_pages': paginator.num_pages,
                    'total_count': paginator.count,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous(),
                }
            }
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

def get_stats(request):
    """Get scraping statistics"""
    try:
        total_properties = PropertyListing.objects.count()
        completed_properties = PropertyListing.objects.filter(scraping_status='completed').count()
        pending_properties = PropertyListing.objects.filter(scraping_status='pending').count()
        failed_properties = PropertyListing.objects.filter(scraping_status='failed').count()
        
        return JsonResponse({
            'status': 'success',
            'data': {
                'total_properties': total_properties,
                'completed_properties': completed_properties,
                'pending_properties': pending_properties,
                'failed_properties': failed_properties,
                'completion_rate': round((completed_properties / total_properties * 100) if total_properties > 0 else 0, 2)
            }
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
