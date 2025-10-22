import time
import re
import logging
from django.db import transaction
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from .models import PropertyListing, PropertyImage

# ----------------------------
# Logging setup
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ----------------------------
# Utility functions
# ----------------------------
def extract_price_numeric(price_str):
    """Convert price string to float"""
    if not price_str:
        return None
    s = re.sub(r"[^\d\.]", "", price_str.replace(",", ""))
    try:
        return float(s) if s else None
    except:
        return None


# ----------------------------
# Complete property detail page scraping
# ----------------------------
# COMPLETE FIXED VERSION - Replace entire scraping section

def scrape_complete_property_details(driver, property_url):
    """Scrape ALL property information from individual property detail page"""
    try:
        logger.info(f"Scraping complete property details from: {property_url}")
        driver.get(property_url)
        
        # Wait for page to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Add extra wait for dynamic content
        time.sleep(3)
        
        property_data = {
            'external_id': '',
            'title': '',
            'price': '',
            'price_numeric': None,
            'property_type': '',
            'bedrooms': None,
            'bathrooms': None,
            'size': '',
            'description': '',  # Initialize as empty string, NOT None
            'key_features': [],  # Initialize as empty list, NOT None
            'date_added': None,
            'image_urls': [],
            'listing_url': property_url
        }
        
        # Get the entire page text for fallback extraction
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Extract External ID from URL
        id_match = re.search(r'/properties/(\d+)', property_url)
        if id_match:
            property_data['external_id'] = id_match.group(1)
            logger.info(f"✅ Found external ID: {property_data['external_id']}")
        
        # Extract Title (Address)
        try:
            title_element = driver.find_element(By.CSS_SELECTOR, "h1[itemprop='streetAddress']")
            property_data['title'] = title_element.text.strip()
            logger.info(f"✅ Found title: {property_data['title']}")
        except:
            try:
                title_element = driver.find_element(By.CSS_SELECTOR, "h1")
                property_data['title'] = title_element.text.strip()
                logger.info(f"✅ Found title (fallback): {property_data['title']}")
            except:
                logger.warning("Could not extract title")
        
        # Extract Price
        try:
            price_selectors = [
                "span._1gfnqJ3Vtd1z40MlC0MzXu span",
                "[data-testid='price'] span",
                "span[class*='price']"
            ]
            
            for selector in price_selectors:
                try:
                    price_element = driver.find_element(By.CSS_SELECTOR, selector)
                    price_text = price_element.text.strip()
                    if "£" in price_text:
                        property_data['price'] = price_text
                        property_data['price_numeric'] = extract_price_numeric(price_text)
                        logger.info(f"✅ Found price: {price_text}")
                        break
                except:
                    continue
        except Exception as e:
            logger.warning(f"Error extracting price: {e}")
        
        # Extract Property Details from dt/dd structure
        try:
            dt_elements = driver.find_elements(By.CSS_SELECTOR, "dt")
            
            for dt in dt_elements:
                dt_text = dt.text.strip().upper()
                
                try:
                    dd_element = dt.find_element(By.XPATH, "following-sibling::dd[1]")
                    dd_text = dd_element.text.strip()
                    
                    if "PROPERTY TYPE" in dt_text or dt_text == "TYPE":
                        property_data['property_type'] = dd_text
                        logger.info(f"✅ Found property type: {dd_text}")
                    
                    elif "BEDROOM" in dt_text:
                        bed_match = re.search(r'(\d+)', dd_text)
                        if bed_match:
                            property_data['bedrooms'] = int(bed_match.group(1))
                            logger.info(f"✅ Found bedrooms: {property_data['bedrooms']}")
                    
                    elif "BATHROOM" in dt_text:
                        bath_match = re.search(r'(\d+)', dd_text)
                        if bath_match:
                            property_data['bathrooms'] = int(bath_match.group(1))
                            logger.info(f"✅ Found bathrooms: {property_data['bathrooms']}")
                    
                    elif "SIZE" in dt_text or "FLOOR AREA" in dt_text:
                        if any(unit in dd_text.lower() for unit in ['sq ft', 'sq m', 'sqft', 'sqm']):
                            property_data['size'] = dd_text
                            logger.info(f"✅ Found size: {dd_text}")
                
                except Exception as e:
                    continue
        
        except Exception as e:
            logger.warning(f"Error extracting property details: {e}")
        
        # ==========================================
        # EXTRACT DESCRIPTION - FIXED VERSION
        # ==========================================
        description_text = ""
        
        # Method 1: Look for "Description" heading followed by text
        try:
            lines = page_text.split('\n')
            desc_start_idx = -1
            
            for i, line in enumerate(lines):
                line_clean = line.strip().lower()
                if line_clean == 'description' or line_clean == 'property description':
                    desc_start_idx = i + 1
                    logger.info(f"🔍 Found 'Description' heading at line {i}")
                    break
            
            if desc_start_idx > 0:
                desc_lines = []
                stop_headings = ['key features', 'brochures', 'council tax', 'notes', 'staying secure', 
                                'map', 'nearest stations', 'schools', 'broadband', 'property type', 
                                'bedrooms', 'bathrooms', 'size', 'tenure', 'features']
                
                for line in lines[desc_start_idx:]:
                    line_stripped = line.strip()
                    line_lower = line_stripped.lower()
                    
                    # Stop if we hit another section heading
                    if any(heading in line_lower for heading in stop_headings):
                        logger.info(f"🛑 Stopped at section: {line_stripped}")
                        break
                    
                    # Add substantial lines
                    if line_stripped and len(line_stripped) > 15:
                        desc_lines.append(line_stripped)
                
                if desc_lines:
                    description_text = ' '.join(desc_lines)
                    logger.info(f"✅ DESCRIPTION METHOD 1 SUCCESS: {len(description_text)} chars")
                    logger.info(f"   Preview: {description_text[:150]}...")
        
        except Exception as e:
            logger.warning(f"Error in description method 1: {e}")
        
        # Method 2: Try specific CSS selectors
        if not description_text or len(description_text) < 50:
            try:
                desc_selectors = [
                    "div.STw8udCxUaBUMfOOZu0iL",
                    "[data-testid='description']",
                    "div[itemprop='description']",
                    "section div p"
                ]
                
                for selector in desc_selectors:
                    try:
                        desc_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in desc_elements:
                            text = element.text.strip()
                            if len(text) > 100:
                                description_text = text
                                logger.info(f"✅ DESCRIPTION METHOD 2 SUCCESS: {len(text)} chars via {selector}")
                                logger.info(f"   Preview: {text[:150]}...")
                                break
                        if description_text and len(description_text) > 50:
                            break
                    except:
                        continue
            except Exception as e:
                logger.warning(f"Error in description method 2: {e}")
        
        # CRITICAL: Assign the extracted description
        if description_text:
            property_data['description'] = description_text
            logger.info(f"✅✅✅ FINAL DESCRIPTION SET: {len(property_data['description'])} chars")
        else:
            logger.warning("⚠️ NO DESCRIPTION FOUND - Will save empty string")
            property_data['description'] = ""  # Explicit empty string
        
        # ==========================================
        # EXTRACT KEY FEATURES - FIXED VERSION
        # ==========================================
        features_list = []
        
        # Method 1: Extract from page text
        try:
            lines = page_text.split('\n')
            features_start_idx = -1
            
            for i, line in enumerate(lines):
                line_clean = line.strip().lower()
                if 'key features' in line_clean or line_clean == 'features':
                    features_start_idx = i + 1
                    logger.info(f"🔍 Found 'Key Features' heading at line {i}")
                    break
            
            if features_start_idx > 0:
                stop_headings = ['description', 'brochures', 'council tax', 'notes', 'property type', 
                                'bedrooms', 'bathrooms', 'size', 'tenure', 'added on', 'reduced on',
                                'agent', 'map', 'schools', 'station']
                
                for line in lines[features_start_idx:]:
                    line_stripped = line.strip()
                    line_lower = line_stripped.lower()
                    
                    # Stop conditions
                    if not line_stripped:
                        continue
                    if any(heading in line_lower for heading in stop_headings):
                        logger.info(f"🛑 Stopped features at: {line_stripped}")
                        break
                    
                    # Valid feature criteria
                    if (5 < len(line_stripped) < 150 and 
                        not line_stripped.isupper() and 
                        ':' not in line_stripped and
                        not line_stripped.startswith('£')):
                        features_list.append(line_stripped)
                        logger.info(f"   + Feature: {line_stripped}")
                
                if features_list:
                    logger.info(f"✅ FEATURES METHOD 1 SUCCESS: {len(features_list)} features")
        
        except Exception as e:
            logger.warning(f"Error in key features method 1: {e}")
        
        # Method 2: Try CSS selectors for list items
        if not features_list or len(features_list) < 2:
            try:
                list_selectors = [
                    "ul._1uI3IvdF5sIuBtRIvKrreQ li",
                    "[data-testid='key-features'] li",
                    "ul li"
                ]
                
                for selector in list_selectors:
                    try:
                        feature_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        
                        if len(feature_elements) >= 3:
                            temp_features = []
                            for element in feature_elements:
                                text = element.text.strip()
                                if (text and 5 < len(text) < 150 and
                                    not any(nav_word in text.lower() for nav_word in 
                                           ['buy', 'rent', 'sold', 'commercial', 'mortgages', 
                                            'agent', 'search', 'house prices'])):
                                    temp_features.append(text)
                                    logger.info(f"   + Feature (CSS): {text}")
                            
                            if len(temp_features) >= 3:
                                features_list = temp_features[:20]
                                logger.info(f"✅ FEATURES METHOD 2 SUCCESS: {len(features_list)} features")
                                break
                    except:
                        continue
            
            except Exception as e:
                logger.warning(f"Error in key features method 2: {e}")
        
        # CRITICAL: Assign the extracted features
        if features_list:
            property_data['key_features'] = features_list
            logger.info(f"✅✅✅ FINAL KEY FEATURES SET: {len(property_data['key_features'])} items")
            for idx, feat in enumerate(property_data['key_features'][:5], 1):
                logger.info(f"      {idx}. {feat}")
        else:
            logger.warning("⚠️ NO KEY FEATURES FOUND - Will save empty list")
            property_data['key_features'] = []  # Explicit empty list
        
        # Extract Date Added
        try:
            date_patterns = [
                r'(?:Added on|Reduced on)\s+(\d{2}/\d{2}/\d{4})',
                r'(?:added on|reduced on)\s+(\d{2}/\d{2}/\d{4})',
            ]
            
            for pattern in date_patterns:
                date_match = re.search(pattern, page_text, re.IGNORECASE)
                if date_match:
                    date_str = date_match.group(1)
                    try:
                        from datetime import datetime
                        property_data['date_added'] = datetime.strptime(date_str, "%d/%m/%Y").date()
                        logger.info(f"✅ Found date added: {property_data['date_added']}")
                        break
                    except ValueError:
                        continue
        
        except Exception as e:
            logger.warning(f"Error extracting date: {e}")
        
        # Extract Images
        try:
            # Try meta tags first
            try:
                meta_images = driver.find_elements(By.CSS_SELECTOR, "meta[property='og:image']")
                for meta in meta_images:
                    src = meta.get_attribute("content")
                    if src and src.startswith("http") and src not in property_data['image_urls']:
                        property_data['image_urls'].append(src)
            except:
                pass
            
            # Then try img tags
            image_selectors = [
                "img[src*='rightmove']",
                "img[src*='media']",
                "div[class*='gallery'] img",
                "img"
            ]
            
            for selector in image_selectors:
                try:
                    img_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for img in img_elements:
                        src = img.get_attribute("src") or img.get_attribute("data-src")
                        if (src and src.startswith("http") and src not in property_data['image_urls'] and
                            any(x in src.lower() for x in ['rightmove', 'media', 'property'])):
                            property_data['image_urls'].append(src)
                except:
                    continue
            
            logger.info(f"✅ Found {len(property_data['image_urls'])} images")
        
        except Exception as e:
            logger.warning(f"Error extracting images: {e}")
        
        # Final validation log
        logger.info(f"=" * 60)
        logger.info(f"EXTRACTION SUMMARY (PRE-SAVE):")
        logger.info(f"Title: {property_data['title'][:50] if property_data['title'] else '❌ NOT FOUND'}")
        logger.info(f"Price: {property_data['price'] or '❌ NOT FOUND'}")
        logger.info(f"Bedrooms: {property_data['bedrooms'] or '❌ NOT FOUND'}")
        logger.info(f"Bathrooms: {property_data['bathrooms'] or '❌ NOT FOUND'}")
        logger.info(f"Property Type: {property_data['property_type'] or '❌ NOT FOUND'}")
        logger.info(f"Size: {property_data['size'] or '❌ NOT FOUND'}")
        logger.info(f"Description TYPE: {type(property_data['description'])}")
        logger.info(f"Description LENGTH: {len(property_data['description'])} chars")
        logger.info(f"Description PREVIEW: {property_data['description'][:100] if property_data['description'] else 'EMPTY'}")
        logger.info(f"Key Features TYPE: {type(property_data['key_features'])}")
        logger.info(f"Key Features COUNT: {len(property_data['key_features'])} items")
        logger.info(f"Key Features CONTENT: {property_data['key_features'][:3] if property_data['key_features'] else 'EMPTY LIST'}")
        logger.info(f"Images: {len(property_data['image_urls'])} URLs")
        logger.info(f"=" * 60)
        
        return property_data
        
    except Exception as e:
        logger.error(f"Error scraping complete property details: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


def save_property_to_db_simple(property_data):
    """Fixed database save function"""
    try:
        if not property_data.get("listing_url"):
            logger.error("No listing URL provided")
            return False

        with transaction.atomic():
            # Remove image_urls for separate processing
            image_urls = property_data.pop("image_urls", [])
            
            # CRITICAL: Verify data BEFORE saving
            description = property_data.get('description', '')
            key_features = property_data.get('key_features', [])
            
            logger.info(f"=" * 60)
            logger.info(f"💾 PRE-SAVE VERIFICATION:")
            logger.info(f"   Description type: {type(description)}")
            logger.info(f"   Description length: {len(description)}")
            logger.info(f"   Description value: '{description[:100]}...' " if description else "   Description: EMPTY")
            logger.info(f"   Key features type: {type(key_features)}")
            logger.info(f"   Key features count: {len(key_features)}")
            logger.info(f"   Key features value: {key_features[:3]}" if key_features else "   Key features: EMPTY LIST")
            
            # Ensure proper types (should already be correct from extraction)
            if not isinstance(description, str):
                description = str(description) if description else ''
                property_data['description'] = description
                
            if not isinstance(key_features, list):
                key_features = list(key_features) if key_features else []
                property_data['key_features'] = key_features
            
            # Create or update the property
            obj, created = PropertyListing.objects.update_or_create(
                listing_url=property_data["listing_url"],
                defaults=property_data,
            )
            
            # Force refresh from database
            obj.refresh_from_db()
            
            # Verify what was actually saved
            logger.info(f"=" * 60)
            logger.info(f"✅ POST-SAVE VERIFICATION:")
            logger.info(f"   ID: {obj.id}")
            logger.info(f"   Title: {obj.title}")
            logger.info(f"   Description DB type: {type(obj.description)}")
            logger.info(f"   Description DB length: {len(obj.description) if obj.description else 0}")
            logger.info(f"   Description DB preview: '{obj.description[:100]}...'" if obj.description else "   Description DB: EMPTY")
            logger.info(f"   Key features DB type: {type(obj.key_features)}")
            logger.info(f"   Key features DB count: {len(obj.key_features) if obj.key_features else 0}")
            logger.info(f"   Key features DB value: {obj.key_features[:3]}" if obj.key_features else "   Key features DB: EMPTY")
            
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
                logger.info(f"   Images saved: {len(image_urls)}")
            
            # Final fresh query verification
            verify_obj = PropertyListing.objects.get(id=obj.id)
            logger.info(f"=" * 60)
            logger.info(f"🔍 FRESH QUERY VERIFICATION:")
            logger.info(f"   Description exists: {bool(verify_obj.description)}")
            logger.info(f"   Description chars: {len(verify_obj.description) if verify_obj.description else 0}")
            logger.info(f"   Key features exists: {bool(verify_obj.key_features)}")
            logger.info(f"   Key features items: {len(verify_obj.key_features) if verify_obj.key_features else 0}")
            logger.info(f"   Key features data: {verify_obj.key_features}")
            logger.info(f"=" * 60)
                        
        logger.info(f"{'✅ NEW PROPERTY' if created else '🔄 UPDATED'}: {property_data.get('title', 'Unknown')}")
        return created
        
    except Exception as e:
        logger.error(f"❌ DB Save Error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
# ----------------------------
# Get URLs from search results
# ----------------------------
def scrape_property_urls_from_search(search_url, max_pages=2):
    """Get property URLs from search results page"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    property_urls = []

    try:
        logger.info(f"🔍 Getting property URLs from: {search_url}")
        driver.get(search_url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='PropertyCard_propertyCardContainer']"))
        )

        for page in range(1, max_pages + 1):
            cards = driver.find_elements(By.CSS_SELECTOR, "div[class*='PropertyCard_propertyCardContainer']")
            logger.info(f"📄 Page {page}: Found {len(cards)} property cards")

            for card in cards:
                try:
                    link_element = card.find_element(By.CSS_SELECTOR, "a[href*='/properties/']")
                    property_url = link_element.get_attribute("href")
                    if property_url and property_url not in property_urls:
                        property_urls.append(property_url)
                except NoSuchElementException:
                    continue

            # Try to go to next page
            if page < max_pages:
                try:
                    next_button = driver.find_element(By.CSS_SELECTOR, ".pagination-direction--next")
                    if next_button.is_enabled():
                        driver.execute_script("arguments[0].click();", next_button)
                        time.sleep(3)
                    else:
                        break
                except NoSuchElementException:
                    break

        logger.info(f"✅ Total property URLs found: {len(property_urls)}")

    except Exception as e:
        logger.error(f"❌ Error getting property URLs: {e}")
    finally:
        driver.quit()

    return property_urls


# ----------------------------
# Main scraping function
# ----------------------------
def scrape_properties_from_detail_pages(search_url, max_pages=2):
    """Main function: Get URLs from search, then scrape each detail page completely"""
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 STARTING RIGHTMOVE SCRAPER")
    logger.info(f"{'='*60}\n")
    
    # Step 1: Get property URLs
    property_urls = scrape_property_urls_from_search(search_url, max_pages)
    
    if not property_urls:
        logger.error("❌ No property URLs found!")
        return 0
    
    # Step 2: Scrape each property
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    new_count = 0
    update_count = 0

    try:
        logger.info(f"\n📥 Scraping {len(property_urls)} property detail pages...\n")
        
        for i, property_url in enumerate(property_urls, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"🏠 Property {i}/{len(property_urls)}")
            logger.info(f"🔗 URL: {property_url}")
            logger.info(f"{'='*60}")
            
            # Scrape complete details
            property_data = scrape_complete_property_details(driver, property_url)
            
            if property_data:
                result = save_property_to_db_simple(property_data)
                if result is True:
                    new_count += 1
                elif result is False:
                    update_count += 1
            
            # Polite delay
            time.sleep(2)

        logger.info(f"\n{'='*60}")
        logger.info(f"🎉 SCRAPING COMPLETE!")
        logger.info(f"✅ New properties: {new_count}")
        logger.info(f"🔄 Updated properties: {update_count}")
        logger.info(f"📊 Total processed: {new_count + update_count}")
        logger.info(f"{'='*60}\n")

    except Exception as e:
        logger.error(f"❌ Scraping error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    finally:
        driver.quit()

    return new_count + update_count


# ----------------------------
# Public function
# ----------------------------
def scrape_listing_selenium(url):
    """Public function to scrape Rightmove listings"""
    return scrape_properties_from_detail_pages(url, max_pages=2)