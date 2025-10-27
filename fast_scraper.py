#!/usr/bin/env python
"""
FAST property scraper - only processes 2-3 properties for quick testing
"""
import os
import django
import re
import time

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
from webdriver_manager.chrome import ChromeDriverManager

def extract_price_numeric(price_text):
    """Extract numeric price from text"""
    if not price_text:
        return None
    price_clean = re.sub(r'[^\d.]', '', price_text)
    try:
        return float(price_clean)
    except ValueError:
        return None

def scrape_fast_property(driver, property_url):
    """Fast scrape of a single property"""
    print(f"🚀 Scraping: {property_url}")
    
    try:
        driver.get(property_url)
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        
        # Get external ID
        id_match = re.search(r'/properties/(\d+)', property_url)
        external_id = id_match.group(1) if id_match else None
        
        # Get all text from page
        page_text = driver.find_element(By.CSS_SELECTOR, "body").text
        
        # Extract title
        title = ""
        try:
            title_element = driver.find_element(By.CSS_SELECTOR, "h1")
            title = title_element.text.strip()
        except:
            title = f"Property {external_id}"
        
        # Extract price
        price = ""
        price_numeric = None
        price_match = re.search(r'£[\d,]+(?:\.\d{2})?', page_text)
        if price_match:
            price = price_match.group()
            price_numeric = extract_price_numeric(price)
        
        # Extract bedrooms/bathrooms
        bedrooms = None
        bathrooms = None
        bed_match = re.search(r'(\d+)\s*bedroom', page_text.lower())
        if bed_match:
            bedrooms = int(bed_match.group(1))
        
        bath_match = re.search(r'(\d+)\s*bathroom', page_text.lower())
        if bath_match:
            bathrooms = int(bath_match.group(1))
        
        # Extract size
        size = ""
        size_match = re.search(r'(\d+(?:,\d+)*)\s*sq\s*ft', page_text)
        if size_match:
            size = size_match.group()
        
        # Extract description - look for long text
        description = ""
        all_divs = driver.find_elements(By.CSS_SELECTOR, "div")
        for div in all_divs:
            text = div.text.strip()
            if len(text) > 300 and any(word in text.lower() for word in ['bedroom', 'apartment', 'property', 'beautifully', 'refurbished']):
                description = text
                break
        
        # Extract key features
        key_features = []
        all_lis = driver.find_elements(By.CSS_SELECTOR, "li")
        for li in all_lis:
            text = li.text.strip()
            if text and len(text) < 100 and any(word in text.lower() for word in ['bedroom', 'bathroom', 'reception', 'lift', 'concierge', 'garden', 'parking']):
                key_features.append(text)
        
        # Extract images
        image_urls = []
        all_imgs = driver.find_elements(By.CSS_SELECTOR, "img")
        for img in all_imgs:
            src = img.get_attribute("src")
            if src and src.startswith("http") and "rightmove" in src and src not in image_urls:
                image_urls.append(src)
        
        property_data = {
            'external_id': external_id,
            'title': title,
            'price': price,
            'price_numeric': price_numeric,
            'property_type': 'Property',
            'bedrooms': bedrooms,
            'bathrooms': bathrooms,
            'size': size,
            'description': description,
            'key_features': key_features,
            'date_added': None,
            'image_urls': image_urls,
            'listing_url': property_url
        }
        
        print(f"✅ Extracted:")
        print(f"  Title: {title}")
        print(f"  Price: {price}")
        print(f"  Bedrooms: {bedrooms}")
        print(f"  Bathrooms: {bathrooms}")
        print(f"  Size: {size}")
        print(f"  Description: {len(description)} chars")
        print(f"  Key features: {len(key_features)} items")
        print(f"  Images: {len(image_urls)}")
        
        return property_data
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def save_property_fast(property_data):
    """Fast save to database"""
    try:
        with transaction.atomic():
            image_urls = property_data.pop("image_urls", [])
            
            obj, created = PropertyListing.objects.update_or_create(
                listing_url=property_data["listing_url"],
                defaults=property_data,
            )
            
            # Save images
            if image_urls:
                obj.images.all().delete()
                for i, image_url in enumerate(image_urls[:5]):  # Limit to 5 images for speed
                    PropertyImage.objects.create(
                        property=obj,
                        image_url=image_url,
                        image_order=i,
                        is_primary=(i == 0),
                        image_title=f"Image {i + 1}"
                    )
            
            print(f"💾 {'NEW' if created else 'UPDATED'}: {obj.title}")
            print(f"  Description: {len(obj.description) if obj.description else 0} chars")
            print(f"  Key features: {len(obj.key_features) if obj.key_features else 0} items")
            print(f"  Size: {obj.size}")
            
            return created
            
    except Exception as e:
        print(f"❌ Save error: {e}")
        return False

def get_few_property_urls():
    """Get just 2-3 property URLs quickly"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    urls = []
    
    try:
        search_url = "https://www.rightmove.co.uk/property-for-sale/find.html?searchLocation=London&useLocationIdentifier=true&locationIdentifier=REGION%5E87490&radius=40.0&_includeSSTC=on&index=0&sortType=2&channel=BUY&transactionType=BUY&displayLocationIdentifier=London-87490.html"
        
        print(f"🔍 Getting URLs from search page...")
        driver.get(search_url)
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='PropertyCard']"))
        )
        
        cards = driver.find_elements(By.CSS_SELECTOR, "div[class*='PropertyCard']")
        print(f"Found {len(cards)} cards")
        
        # Get just first 3 URLs
        for i, card in enumerate(cards[:3]):
            try:
                link = card.find_element(By.CSS_SELECTOR, "a[href*='/properties/']")
                url = link.get_attribute("href")
                if url:
                    urls.append(url)
                    print(f"✅ URL {i+1}: {url}")
            except:
                continue
        
    except Exception as e:
        print(f"❌ Error getting URLs: {e}")
    finally:
        driver.quit()
    
    return urls

def main():
    """Main function - FAST scraping"""
    print("🚀 FAST PROPERTY SCRAPER")
    print("=" * 50)
    
    # Get URLs
    urls = get_few_property_urls()
    
    if not urls:
        print("❌ No URLs found!")
        return
    
    print(f"\n📋 Scraping {len(urls)} properties...")
    
    # Setup driver
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    new_count = 0
    update_count = 0
    
    try:
        for i, url in enumerate(urls, 1):
            print(f"\n🏠 Property {i}/{len(urls)}")
            
            # Scrape
            data = scrape_fast_property(driver, url)
            
            if data:
                # Save
                result = save_property_fast(data)
                if result is True:
                    new_count += 1
                elif result is False:
                    update_count += 1
            
            # Quick delay
            time.sleep(0.5)
        
        print(f"\n✅ COMPLETE!")
        print(f"📊 Results: {new_count} new, {update_count} updated")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

