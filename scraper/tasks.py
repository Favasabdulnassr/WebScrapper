from celery import shared_task
from .scraper import scrape_listing_selenium
import logging

logger = logging.getLogger(__name__)

# celery -A webscraper worker --loglevel=info -P solo


@shared_task
def scrape_properties_task(search_url, max_pages=3):
    logger.info(f"Starting scraping task for: {search_url}")
    try:
        result = scrape_listing_selenium(search_url)
        logger.info(f"Scraping completed. Result: {result}")
        return f"Scraped {result} properties successfully"
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        return f"Scraping failed: {str(e)}"

