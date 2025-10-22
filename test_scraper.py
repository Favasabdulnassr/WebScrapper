#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webscraper.settings')
django.setup()

from scraper.models import PropertyListing
from scraper.scraper import scrape_complete_property_details, save_property_to_db_simple
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def test_single_property():
    print("Testing single property scraping...")
    
    # Setup Chrome driver
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        # Test URL
        test_url = "https://www.rightmove.co.uk/properties/166367849"
        print(f"Scraping: {test_url}")
        
        # Scrape the property
        data = scrape_complete_property_details(driver, test_url)
        
        if data:
            print(f"✅ Extracted data:")
            print(f"  Title: {data.get('title', 'None')}")
            print(f"  Description length: {len(data.get('description', ''))}")
            print(f"  Key features count: {len(data.get('key_features', []))}")
            print(f"  Size: {data.get('size', 'None')}")
            print(f"  Price: {data.get('price', 'None')}")
            print(f"  Bedrooms: {data.get('bedrooms', 'None')}")
            print(f"  Bathrooms: {data.get('bathrooms', 'None')}")
            
            # Save to database
            print("\nSaving to database...")
            result = save_property_to_db_simple(data)
            print(f"Save result: {result}")
            
            # Check what was actually saved
            if data.get('listing_url'):
                saved_prop = PropertyListing.objects.filter(listing_url=data['listing_url']).first()
                if saved_prop:
                    print(f"\n✅ Saved property:")
                    print(f"  Title: {saved_prop.title}")
                    print(f"  Description length: {len(saved_prop.description) if saved_prop.description else 0}")
                    print(f"  Key features count: {len(saved_prop.key_features) if saved_prop.key_features else 0}")
                    print(f"  Size: {saved_prop.size}")
                    print(f"  Price: {saved_prop.price}")
                    print(f"  Bedrooms: {saved_prop.bedrooms}")
                    print(f"  Bathrooms: {saved_prop.bathrooms}")
                else:
                    print("❌ Property not found in database")
        else:
            print("❌ No data extracted")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    test_single_property()
