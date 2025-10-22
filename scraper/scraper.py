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
# FIXED: Utility function for price extraction
# ----------------------------
def extract_price_numeric(price_str):
    """Convert price string to float - handles £, commas, and various formats"""
    if not price_str:
        return None
    
    # Remove all non-numeric characters except decimal point
    s = re.sub(r"[^\d\.]", "", price_str.replace(",", ""))
    
    try:
        return float(s) if s else None
    except:
        return None


# ----------------------------
# FIXED: Complete property detail page scraping with improved price extraction
# ----------------------------
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
            'description': '',
            'key_features': [],
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
        
        # ==========================================
        # FIXED: PRICE EXTRACTION WITH MULTIPLE METHODS
        # ==========================================
        price_found = False
        
        # Method 1: Try common CSS selectors for price
        try:
            price_selectors = [
                "span._1gfnqJ3Vtd1z40MlC0MzXu span",
                "span[data-testid='price']",
                "div[data-testid='price'] span",
                "span[class*='propertyCard-priceValue']",
                "p[class*='price']",
                "div[class*='price'] span",
                "span.propertyCard-priceValue",
                "article span[class*='price']"
            ]
            
            for selector in price_selectors:
                try:
                    price_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for price_element in price_elements:
                        price_text = price_element.text.strip()
                        if price_text and "£" in price_text and len(price_text) > 2:
                            property_data['price'] = price_text
                            property_data['price_numeric'] = extract_price_numeric(price_text)
                            logger.info(f"✅ Found price (Method 1 - {selector}): {price_text}")
                            price_found = True
                            break
                    if price_found:
                        break
                except:
                    continue
        except Exception as e:
            logger.warning(f"Method 1 price extraction error: {e}")
        
        # Method 2: Search in page text using regex
        if not price_found:
            try:
                # Look for patterns like "£550,000" or "£1,250,000"
                price_patterns = [
                    r'£[\d,]+(?:\.\d{2})?',  # Matches £550,000 or £550,000.00
                    r'£\s*[\d,]+(?:\.\d{2})?',  # With optional space
                ]
                
                for pattern in price_patterns:
                    matches = re.findall(pattern, page_text)
                    if matches:
                        # Find the most likely price (usually the largest number)
                        valid_prices = []
                        for match in matches:
                            numeric_val = extract_price_numeric(match)
                            if numeric_val and numeric_val > 10000:  # Reasonable property price
                                valid_prices.append((match, numeric_val))
                        
                        if valid_prices:
                            # Sort by numeric value and take the first one (usually the main price)
                            valid_prices.sort(key=lambda x: x[1], reverse=True)
                            best_price = valid_prices[0]
                            property_data['price'] = best_price[0]
                            property_data['price_numeric'] = best_price[1]
                            logger.info(f"✅ Found price (Method 2 - Regex): {best_price[0]}")
                            price_found = True
                            break
            except Exception as e:
                logger.warning(f"Method 2 price extraction error: {e}")
        
        # Method 3: Try XPath for price
        if not price_found:
            try:
                xpath_selectors = [
                    "//span[contains(text(), '£')]",
                    "//p[contains(text(), '£')]",
                    "//div[contains(text(), '£')]"
                ]
                
                for xpath in xpath_selectors:
                    try:
                        price_elements = driver.find_elements(By.XPATH, xpath)
                        for element in price_elements:
                            text = element.text.strip()
                            if text and "£" in text and len(text) < 30:  # Avoid long descriptions
                                numeric_val = extract_price_numeric(text)
                                if numeric_val and numeric_val > 10000:
                                    property_data['price'] = text
                                    property_data['price_numeric'] = numeric_val
                                    logger.info(f"✅ Found price (Method 3 - XPath): {text}")
                                    price_found = True
                                    break
                        if price_found:
                            break
                    except:
                        continue
            except Exception as e:
                logger.warning(f"Method 3 price extraction error: {e}")
        
        # Method 4: Look for price in meta tags (Open Graph)
        if not price_found:
            try:
                meta_price = driver.find_elements(By.CSS_SELECTOR, "meta[property='og:price:amount']")
                if meta_price:
                    price_content = meta_price[0].get_attribute("content")
                    if price_content:
                        property_data['price_numeric'] = float(price_content)
                        property_data['price'] = f"£{price_content}"
                        logger.info(f"✅ Found price (Method 4 - Meta): £{price_content}")
                        price_found = True
            except Exception as e:
                logger.warning(f"Method 4 price extraction error: {e}")
        
        if not price_found:
            logger.warning("⚠️ PRICE NOT FOUND - Tried all methods")
        
        # ==========================================
        # END OF FIXED PRICE EXTRACTION
        # ==========================================
        
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
        
        # Extract Description
        description_text = ""
        
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
                    
                    if any(heading in line_lower for heading in stop_headings):
                        logger.info(f"🛑 Stopped at section: {line_stripped}")
                        break
                    
                    if line_stripped and len(line_stripped) > 15:
                        desc_lines.append(line_stripped)
                
                if desc_lines:
                    description_text = ' '.join(desc_lines)
                    logger.info(f"✅ DESCRIPTION: {len(description_text)} chars")
        
        except Exception as e:
            logger.warning(f"Error in description extraction: {e}")
        
        if description_text:
            property_data['description'] = description_text
        else:
            property_data['description'] = ""
        
        # Extract Key Features
        features_list = []
        
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
                stop_headings = ['description', 'brochures', 'council tax', 'notes', 'property type']
                
                for line in lines[features_start_idx:]:
                    line_stripped = line.strip()
                    line_lower = line_stripped.lower()
                    
                    if not line_stripped:
                        continue
                    if any(heading in line_lower for heading in stop_headings):
                        break
                    
                    if (5 < len(line_stripped) < 150 and 
                        not line_stripped.isupper() and 
                        ':' not in line_stripped):
                        features_list.append(line_stripped)
                
                if features_list:
                    logger.info(f"✅ KEY FEATURES: {len(features_list)} items")
        
        except Exception as e:
            logger.warning(f"Error in key features extraction: {e}")
        
        if features_list:
            property_data['key_features'] = features_list
        else:
            property_data['key_features'] = []
        
        # Extract Date Added
        try:
            date_patterns = [
                r'(?:Added on|Reduced on)\s+(\d{2}/\d{2}/\d{4})',
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
            try:
                meta_images = driver.find_elements(By.CSS_SELECTOR, "meta[property='og:image']")
                for meta in meta_images:
                    src = meta.get_attribute("content")
                    if src and src.startswith("http") and src not in property_data['image_urls']:
                        property_data['image_urls'].append(src)
            except:
                pass
            
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
        logger.info(f"EXTRACTION SUMMARY:")
        logger.info(f"Title: {property_data['title'][:50] if property_data['title'] else '❌'}")
        logger.info(f"Price: {property_data['price'] or '❌ NOT FOUND'}")
        logger.info(f"Price Numeric: {property_data['price_numeric'] or '❌ NOT FOUND'}")
        logger.info(f"Bedrooms: {property_data['bedrooms'] or '❌'}")
        logger.info(f"Property Type: {property_data['property_type'] or '❌'}")
        logger.info(f"Description: {len(property_data['description'])} chars")
        logger.info(f"Key Features: {len(property_data['key_features'])} items")
        logger.info(f"Images: {len(property_data['image_urls'])} URLs")
        logger.info(f"=" * 60)
        
        return property_data
        
    except Exception as e:
        logger.error(f"Error scraping complete property details: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


def save_property_to_db_simple(property_data):
    """Save property data to database"""
    try:
        if not property_data.get("listing_url"):
            logger.error("No listing URL provided")
            return False

        with transaction.atomic():
            image_urls = property_data.pop("image_urls", [])
            
            logger.info(f"💾 Saving to database...")
            logger.info(f"   Price: {property_data.get('price', 'N/A')}")
            logger.info(f"   Price Numeric: {property_data.get('price_numeric', 'N/A')}")
            
            obj, created = PropertyListing.objects.update_or_create(
                listing_url=property_data["listing_url"],
                defaults=property_data,
            )
            
            obj.refresh_from_db()
            
            logger.info(f"✅ SAVED TO DATABASE:")
            logger.info(f"   ID: {obj.id}")
            logger.info(f"   Price DB: {obj.price}")
            logger.info(f"   Price Numeric DB: {obj.price_numeric}")
            
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
                        
        logger.info(f"{'✅ NEW' if created else '🔄 UPDATED'}: {property_data.get('title', 'Unknown')}")
        return created
        
    except Exception as e:
        logger.error(f"❌ DB Save Error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


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


def scrape_properties_from_detail_pages(search_url, max_pages=2):
    """Main function: Get URLs from search, then scrape each detail page"""
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 STARTING RIGHTMOVE SCRAPER")
    logger.info(f"{'='*60}\n")
    
    property_urls = scrape_property_urls_from_search(search_url, max_pages)
    
    if not property_urls:
        logger.error("❌ No property URLs found!")
        return 0
    
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
            
            property_data = scrape_complete_property_details(driver, property_url)
            
            if property_data:
                result = save_property_to_db_simple(property_data)
                if result is True:
                    new_count += 1
                elif result is False:
                    update_count += 1
            
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


def scrape_listing_selenium(url):
    """Public function to scrape Rightmove listings"""
    return scrape_properties_from_detail_pages(url, max_pages=2)