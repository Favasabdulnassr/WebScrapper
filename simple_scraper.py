#!/usr/bin/env python
"""
Simple, reliable property scraper that extracts ALL data from detail pages
"""
import os
import django
import re
import time
from datetime import datetime

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webscraper.settings')
django.setup()

from scraper.models import PropertyListing, PropertyImage
from django.db import transaction
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_price_numeric(price_text):
    """Extract numeric price from text"""
    if not price_text:
        return None
    # Remove all non-numeric characters except decimal point
    price_clean = re.sub(r'[^\d.]', '', price_text)
    try:
        return float(price_clean)
    except ValueError:
        return None

def scrape_single_property_detail(driver, property_url):
    """Scrape complete property details from a single property page"""
    try:
        logger.info(f"Scraping: {property_url}")
        driver.get(property_url)
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )
        
        # Extract external ID from URL
        id_match = re.search(r'/properties/(\d+)', property_url)
        external_id = id_match.group(1) if id_match else None
        
        # Initialize property data
        property_data = {
            'external_id': external_id,
            'title': '',
            'price': '',
            'price_numeric': None,
            'property_type': '',
            'bedrooms': None,
            'bathrooms': None,
            'size': '',
            'description': '',
            'key_features': [],
            'date_added': None,
            'image_urls': [],
            'listing_url': property_url
        }
        
        # Extract title
        try:
            title_element = driver.find_element(By.CSS_SELECTOR, "h1")
            property_data['title'] = title_element.text.strip()
            logger.info(f"✅ Title: {property_data['title']}")
        except:
            pass
        
        # Extract price
        try:
            price_elements = driver.find_elements(By.CSS_SELECTOR, "*")
            for element in price_elements:
                text = element.text.strip()
                if "£" in text and any(char.isdigit() for char in text):
                    property_data['price'] = text
                    property_data['price_numeric'] = extract_price_numeric(text)
                    logger.info(f"✅ Price: {text}")
                    break
        except:
            pass
        
        # Extract bedrooms and bathrooms
        try:
            all_text = driver.find_element(By.CSS_SELECTOR, "body").text
            bed_match = re.search(r'(\d+)\s*bedroom', all_text.lower())
            if bed_match:
                property_data['bedrooms'] = int(bed_match.group(1))
                logger.info(f"✅ Bedrooms: {property_data['bedrooms']}")
            
            bath_match = re.search(r'(\d+)\s*bathroom', all_text.lower())
            if bath_match:
                property_data['bathrooms'] = int(bath_match.group(1))
                logger.info(f"✅ Bathrooms: {property_data['bathrooms']}")
        except:
            pass
        
        # Extract size
        try:
            all_text = driver.find_element(By.CSS_SELECTOR, "body").text
            size_match = re.search(r'(\d+(?:,\d+)*)\s*sq\s*ft', all_text)
            if size_match:
                property_data['size'] = size_match.group()
                logger.info(f"✅ Size: {property_data['size']}")
        except:
            pass
        
        # Extract description - look for long text blocks
        try:
            all_divs = driver.find_elements(By.CSS_SELECTOR, "div")
            for div in all_divs:
                text = div.text.strip()
                if len(text) > 200 and any(word in text.lower() for word in ['bedroom', 'apartment', 'property', 'beautifully', 'refurbished']):
                    property_data['description'] = text
                    logger.info(f"✅ Description: {text[:100]}...")
                    break
        except:
            pass
        
        # Extract key features - look for list items
        try:
            all_lis = driver.find_elements(By.CSS_SELECTOR, "li")
            for li in all_lis:
                text = li.text.strip()
                if text and len(text) < 100 and any(word in text.lower() for word in ['bedroom', 'bathroom', 'reception', 'lift', 'concierge', 'garden', 'parking']):
                    property_data['key_features'].append(text)
                    logger.info(f"✅ Key feature: {text}")
        except:
            pass
        
        # Extract images
        try:
            all_imgs = driver.find_elements(By.CSS_SELECTOR, "img")
            for img in all_imgs:
                src = img.get_attribute("src")
                if src and src.startswith("http") and "rightmove" in src and src not in property_data['image_urls']:
                    property_data['image_urls'].append(src)
        except:
            pass
        
        logger.info(f"✅ Extracted {len(property_data['image_urls'])} images")
        return property_data
        
    except Exception as e:
        logger.error(f"Error scraping {property_url}: {e}")
        return None

def save_property_data(property_data):
    """Save property data to database"""
    try:
        if not property_data or not property_data.get("listing_url"):
            return False
        
        with transaction.atomic():
            # Remove image_urls from property_data
            image_urls = property_data.pop("image_urls", [])
            
            # Create or update property
            obj, created = PropertyListing.objects.update_or_create(
                listing_url=property_data["listing_url"],
                defaults=property_data,
            )
            
            # Save images
            if image_urls:
                obj.images.all().delete()
                for i, image_url in enumerate(image_urls):
                    if image_url and image_url.startswith("http"):
                        PropertyImage.objects.create(
                            property=obj,
                            image_url=image_url,
                            image_order=i,
                            is_primary=(i == 0),
                            image_title=f"Image {i + 1}"
                        )
            
            logger.info(f"{'✅ New' if created else '🔄 Updated'}: {obj.title}")
            logger.info(f"  Description: {len(obj.description) if obj.description else 0} chars")
            logger.info(f"  Key features: {len(obj.key_features) if obj.key_features else 0} items")
            logger.info(f"  Size: {obj.size}")
            logger.info(f"  Images: {len(image_urls)}")
            
            return created
            
    except Exception as e:
        logger.error(f"Error saving property: {e}")
        return False

def get_property_urls(search_url, max_pages=2):
    """Get property URLs from search results"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    property_urls = []
    
    try:
        logger.info(f"Getting URLs from: {search_url}")
        driver.get(search_url)
        
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='PropertyCard']"))
        )
        
        for page in range(1, max_pages + 1):
            cards = driver.find_elements(By.CSS_SELECTOR, "div[class*='PropertyCard']")
            logger.info(f"Page {page}: {len(cards)} cards")
            
            for card in cards:
                try:
                    link = card.find_element(By.CSS_SELECTOR, "a[href*='/properties/']")
                    url = link.get_attribute("href")
                    if url and url not in property_urls:
                        property_urls.append(url)
                except:
                    continue
            
            # Try to go to next page
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, ".pagination-direction--next")
                if next_button.is_enabled():
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(3)
                else:
                    break
            except:
                break
        
        logger.info(f"✅ Found {len(property_urls)} property URLs")
        
    except Exception as e:
        logger.error(f"Error getting URLs: {e}")
    finally:
        driver.quit()
    
    return property_urls

def scrape_properties_complete(search_url, max_pages=2):
    """Complete scraping process"""
    # Step 1: Get property URLs
    property_urls = get_property_urls(search_url, max_pages)
    
    if not property_urls:
        logger.error("No property URLs found!")
        return 0
    
    # Step 2: Scrape each property
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    new_count = 0
    update_count = 0
    
    try:
        logger.info(f"Scraping {len(property_urls)} properties...")
        
        for i, url in enumerate(property_urls, 1):
            logger.info(f"Property {i}/{len(property_urls)}")
            
            # Scrape property details
            data = scrape_single_property_detail(driver, url)
            
            if data:
                # Save to database
                result = save_property_data(data)
                if result is True:
                    new_count += 1
                elif result is False:
                    update_count += 1
            
            # Small delay
            time.sleep(1)
        
        logger.info(f"✅ Complete: {new_count} new, {update_count} updated")
        
    except Exception as e:
        logger.error(f"Scraping error: {e}")
    finally:
        driver.quit()
    
    return new_count + update_count

if __name__ == "__main__":
    # Test with a small number of properties
    search_url = "https://www.rightmove.co.uk/property-for-sale/find.html?searchLocation=London&useLocationIdentifier=true&locationIdentifier=REGION%5E87490&radius=40.0&_includeSSTC=on&index=0&sortType=2&channel=BUY&transactionType=BUY&displayLocationIdentifier=London-87490.html"
    
    result = scrape_properties_complete(search_url, max_pages=1)
    print(f"Scraping completed. Total processed: {result}")
