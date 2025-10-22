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


def extract_bedrooms_bathrooms_from_elements(card):
    """Extract bedroom and bathroom counts from HTML elements using dt/dd structure"""
    bedrooms = bathrooms = None

    try:
        # First try to extract from meta tag with itemprop="name" (e.g., "5 bedroom penthouse")
        try:
            meta_name_element = card.find_element(By.CSS_SELECTOR, "meta[itemprop='name']")
            meta_content = meta_name_element.get_attribute("content")
            if meta_content:
                # Extract bedroom count from meta content like "5 bedroom penthouse"
                bed_match = re.search(r'(\d+)\s*bedroom', meta_content.lower())
                if bed_match:
                    bedrooms = int(bed_match.group(1))
                    logger.info(f"✅ Found bedrooms from meta: {bedrooms}")
                
                # Extract bathroom count if present
                bath_match = re.search(r'(\d+)\s*bathroom', meta_content.lower())
                if bath_match:
                    bathrooms = int(bath_match.group(1))
                    logger.info(f"✅ Found bathrooms from meta: {bathrooms}")
        except NoSuchElementException:
            pass

        # If not found in meta, try dt/dd structure
        if not bedrooms and not bathrooms:
            dt_elements = card.find_elements(By.CSS_SELECTOR, "dt")

            for dt in dt_elements:
                dt_text = dt.text.strip().upper()

                if "BEDROOM" in dt_text:
                    try:
                        dd_element = dt.find_element(By.XPATH, "following-sibling::dd")
                        for p in dd_element.find_elements(By.CSS_SELECTOR, "p"):
                            if p.text.strip().isdigit():
                                bedrooms = int(p.text.strip())
                                break
                    except:
                        continue

                elif "BATHROOM" in dt_text:
                    try:
                        dd_element = dt.find_element(By.XPATH, "following-sibling::dd")
                        for p in dd_element.find_elements(By.CSS_SELECTOR, "p"):
                            if p.text.strip().isdigit():
                                bathrooms = int(p.text.strip())
                                break
                    except:
                        continue

    except Exception as e:
        logger.warning(f"Error extracting bedrooms/bathrooms: {e}")

    return bedrooms, bathrooms


def extract_bedrooms_bathrooms(text):
    """Extract bedroom and bathroom counts from plain text (fallback method)"""
    bedrooms = bathrooms = None
    if not text:
        return bedrooms, bathrooms

    # Split text into lines for analysis
    lines = text.split('\n')
    
    # Look for the pattern: Property Type followed by two numbers
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Check if this line contains property type keywords
        property_types = ['detached', 'apartment', 'house', 'penthouse', 'terraced', 'semi-detached', 
                        'town house', 'end of terrace', 'block of apartments', 'land']
        
        if any(ptype in line.lower() for ptype in property_types):
            # Look at the next two lines for bedroom/bathroom counts
            if i + 2 < len(lines):
                try:
                    bed_line = lines[i + 1].strip()
                    bath_line = lines[i + 2].strip()
                    
                    # Check if both are numbers
                    if bed_line.isdigit() and bath_line.isdigit():
                        bedrooms = int(bed_line)
                        bathrooms = int(bath_line)
                        logger.info(f"✅ Found bedrooms: {bedrooms}, bathrooms: {bathrooms}")
                        break
                except (ValueError, IndexError):
                    continue
    
    # If not found with the above method, try regex patterns
    if not bedrooms and not bathrooms:
        bed_patterns = [
            r'(\d+)\s*bedroom', r'(\d+)\s*bed\b', r'(\d+)\s*beds?', r'(\d+)\s*br\b'
        ]
        bath_patterns = [
            r'(\d+)\s*bathroom', r'(\d+)\s*bath\b', r'(\d+)\s*baths?', r'(\d+)\s*ba\b'
        ]

        for pattern in bed_patterns:
            match = re.search(pattern, text.lower())
            if match:
                bedrooms = int(match.group(1))
                break

        for pattern in bath_patterns:
            match = re.search(pattern, text.lower())
            if match:
                bathrooms = int(match.group(1))
                break

    return bedrooms, bathrooms


def extract_size_from_elements(card):
    """Extract property size from HTML elements using dt/dd structure"""
    size = ""
    
    try:
        # Look for size in various structured elements
        size_selectors = [
            "[data-testid='size']",
            "[data-testid='floor-area']",
            "[class*='size']",
            "[class*='area']",
            "[class*='floor-area']"
        ]
        
        for selector in size_selectors:
            try:
                size_element = card.find_element(By.CSS_SELECTOR, selector)
                size_text = size_element.text.strip()
                if any(unit in size_text.lower() for unit in ["sq ft", "sq m", "sqft", "sqm", "square feet", "square metres"]):
                    size = size_text
                    logger.info(f"✅ Found size from element: {size}")
                    return size
            except NoSuchElementException:
                continue
        
        # Try dt/dd structure (original method)
        dt_elements = card.find_elements(By.CSS_SELECTOR, "dt")
        
        for dt in dt_elements:
            dt_text = dt.text.strip().upper()
            
            if any(keyword in dt_text for keyword in ["SIZE", "AREA", "FLOOR AREA"]):
                try:
                    # Find the next sibling dd element
                    dd_element = dt.find_element(By.XPATH, "following-sibling::dd")
                    
                    # Look for p tags with size information
                    p_elements = dd_element.find_elements(By.CSS_SELECTOR, "p")
                    for p in p_elements:
                        p_text = p.text.strip()
                        if any(unit in p_text.lower() for unit in ["sq ft", "sq m", "sqft", "sqm"]):
                            size = p_text
                            logger.info(f"✅ Found size from dt/dd: {size}")
                            return size
                    
                    # If no p tags, use dd text directly
                    dd_text = dd_element.text.strip()
                    if any(unit in dd_text.lower() for unit in ["sq ft", "sq m", "sqft", "sqm"]):
                        size = dd_text
                        logger.info(f"✅ Found size from dd: {size}")
                        return size
                except:
                    continue
                    
    except Exception as e:
        logger.warning(f"Error extracting size: {e}")
    
    return size


def extract_date_added_from_elements(card):
    """Extract date added from HTML elements"""
    date_added = None
    
    try:
        # Look for various date elements with comprehensive selectors
        date_selectors = [
            # Rightmove specific selectors
            "[data-testid='date-added']",
            "[data-testid='listing-date']",
            "[class*='date-added']",
            "[class*='listing-date']",
            "[class*='added-on']",
            # Generic date selectors
            "[class*='date']",
            "[class*='added']",
            "[class*='reduced']",
            # Specific class from your HTML
            "div[class*='_2nk2x6QhNB1UrxdI5KpvaF']"
        ]
        
        for selector in date_selectors:
            try:
                elements = card.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    text = element.text.strip()
                    if any(keyword in text.lower() for keyword in ["added on", "reduced on", "listed on", "date"]):
                        # Extract date from various formats
                        date_patterns = [
                            r'(\d{1,2}/\d{1,2}/\d{4})',  # DD/MM/YYYY
                            r'(\d{1,2}-\d{1,2}-\d{4})',  # DD-MM-YYYY
                            r'(\d{4}-\d{1,2}-\d{1,2})',  # YYYY-MM-DD
                            r'(\d{1,2}\s+\w+\s+\d{4})',  # DD Month YYYY
                        ]
                        
                        for pattern in date_patterns:
                            date_match = re.search(pattern, text)
                            if date_match:
                                date_str = date_match.group(1)
                                try:
                                    from datetime import datetime
                                    # Try different date formats
                                    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"]:
                                        try:
                                            date_added = datetime.strptime(date_str, fmt).date()
                                            logger.info(f"✅ Found date added: {date_added}")
                                            return date_added
                                        except ValueError:
                                            continue
                                except:
                                    continue
            except:
                continue
        
        # Fallback: search entire card text for date patterns
        card_text = card.text
        date_patterns = [
            r'(?:added on|reduced on|listed on)\s+(\d{1,2}/\d{1,2}/\d{4})',
            r'(?:added on|reduced on|listed on)\s+(\d{1,2}-\d{1,2}-\d{4})',
            r'(\d{1,2}/\d{1,2}/\d{4})',
            r'(\d{1,2}-\d{1,2}-\d{4})'
        ]
        
        for pattern in date_patterns:
            date_match = re.search(pattern, card_text.lower())
            if date_match:
                date_str = date_match.group(1)
                try:
                    from datetime import datetime
                    for fmt in ["%d/%m/%Y", "%d-%m-%Y"]:
                        try:
                            date_added = datetime.strptime(date_str, fmt).date()
                            logger.info(f"✅ Found date from text: {date_added}")
                            return date_added
                        except ValueError:
                            continue
                except:
                    continue
                
    except Exception as e:
        logger.warning(f"Error extracting date added: {e}")
    
    return date_added


def extract_images_from_elements(card):
    """Extract multiple images from HTML elements"""
    images = []

    try:
        # Look for meta tags with image URLs (from your HTML structure)
        meta_elements = card.find_elements(By.CSS_SELECTOR, "meta[itemprop='image']")
        for meta in meta_elements:
            src = meta.get_attribute("content")
            if src and src.startswith("http") and src not in images:
                images.append(src)
                logger.info(f"✅ Found image from meta: {src}")
        
        # Look for carousel images with more comprehensive selectors
        carousel_selectors = [
            "a[itemprop='photo']",
            "[data-testid='photo-collage'] a",
            "[data-testid='property-photo'] a",
            "[class*='carousel'] a",
            "[class*='photo'] a",
            "[class*='image'] a",
            "[class*='gallery'] a",
            "[class*='slider'] a"
        ]
        
        for selector in carousel_selectors:
            try:
                img_elements = card.find_elements(By.CSS_SELECTOR, selector)
                for img in img_elements:
                    # Try to get image URL from various attributes
                    src = img.get_attribute("href") or img.get_attribute("data-src") or img.get_attribute("src")
                    if src and src.startswith("http") and src not in images:
                        images.append(src)
                        logger.info(f"✅ Found image from carousel: {src}")
            except:
                continue
        
        # Look for img tags with data attributes
        img_selectors = [
            "img[data-src]",
            "img[data-lazy]",
            "img[src]"
        ]
        
        for selector in img_selectors:
            try:
                img_elements = card.find_elements(By.CSS_SELECTOR, selector)
                for img in img_elements:
                    src = img.get_attribute("data-src") or img.get_attribute("data-lazy") or img.get_attribute("src")
                    if src and src.startswith("http") and src not in images:
                        images.append(src)
                        logger.info(f"✅ Found image from img tag: {src}")
            except:
                continue
        
        # Fallback: look for regular img tags
        if not images:
            img_elements = card.find_elements(By.CSS_SELECTOR, "img")
            for img in img_elements:
                src = img.get_attribute("src")
                if src and src.startswith("http") and src not in images:
                    images.append(src)
                    logger.info(f"✅ Found image from fallback: {src}")
                
    except Exception as e:
        logger.warning(f"Error extracting images: {e}")
    
    return images


# ----------------------------
# Core data extraction
# ----------------------------
def extract_property_data_from_card(card):
    """Extract essential property data from a property card element"""
    try:
        # --- URL ---
        try:
            link_element = card.find_element(By.CSS_SELECTOR, "a[href*='/properties/']")
            property_url = link_element.get_attribute("href")
        except NoSuchElementException:
            return None

        if not property_url:
            return None

        # --- External ID ---
        id_match = re.search(r'/properties/(\d+)', property_url)
        external_id = id_match.group(1) if id_match else None

        card_text = card.text
        title = ""

        # --- Title ---
        # First try to get the property name from meta tag (e.g., "5 bedroom penthouse")
        try:
            meta_name_element = card.find_element(By.CSS_SELECTOR, "meta[itemprop='name']")
            property_name = meta_name_element.get_attribute("content")
            if property_name and len(property_name) > 5:
                title = property_name.strip()
                logger.info(f"✅ Found property name from meta: {title}")
        except NoSuchElementException:
            pass

        # If no meta name found, try the h1 element with itemprop streetAddress
        if not title:
            try:
                h1_element = card.find_element(By.CSS_SELECTOR, "h1[itemprop='streetAddress']")
                title_text = h1_element.text.strip()
                if len(title_text) > 10:
                    title = title_text.split("\n")[0].strip()
                    logger.info(f"✅ Found title from h1: {title}")
            except NoSuchElementException:
                pass

        # Fallback to other title selectors
        if not title:
            title_selectors = [
                "h1", "h2", "h3",
                ".PropertyCardTitle_propertyCardTitle__2P9Xz",
                "[class*='summary']", "[class*='title']", "[class*='address']"
            ]
            for selector in title_selectors:
                try:
                    title_element = card.find_element(By.CSS_SELECTOR, selector)
                    title_text = title_element.text.strip()
                    if len(title_text) > 10:
                        title = title_text.split("\n")[0].strip()
                        break
                except NoSuchElementException:
                    continue

        # Final fallback: extract from card text
        if not title:
            for line in card_text.split("\n"):
                if len(line) > 20 and any(
                    word in line.lower()
                    for word in ["bedroom", "flat", "house", "apartment", "property", "road", "street"]
                ):
                    title = line.strip()
                    break
        if not title:
            title = f"Property {external_id or ''}"

        # --- Price ---
        price = ""
        price_numeric = None
        
        # Try multiple price extraction methods
        price_selectors = [
            # Rightmove specific selectors
            "[data-testid='price']",
            "[class*='PropertyCardPrice']",
            "[class*='price']",
            ".price",
            # Generic price patterns
            "[class*='amount']",
            "[class*='cost']"
        ]

        for selector in price_selectors:
            try:
                price_element = card.find_element(By.CSS_SELECTOR, selector)
                price_text = price_element.text.strip()
                if "£" in price_text:
                    price = price_text
                    price_numeric = extract_price_numeric(price)
                    logger.info(f"✅ Found price: {price}")
                    break
            except NoSuchElementException:
                continue

        # Fallback: extract price from text using regex
        if not price:
            price_patterns = [
                r"£[\d,]+(?:\.\d{2})?",
                r"£\s*[\d,]+(?:\.\d{2})?",
                r"[\d,]+(?:\.\d{2})?\s*£"
            ]
            
            for pattern in price_patterns:
                match = re.search(pattern, card_text)
                if match:
                    price = match.group().replace(" ", "")
                    price_numeric = extract_price_numeric(price)
                    logger.info(f"✅ Found price from text: {price}")
                    break

        # --- Bedrooms & Bathrooms ---
        bedrooms, bathrooms = extract_bedrooms_bathrooms_from_elements(card)
        if not bedrooms and not bathrooms:
            bedrooms, bathrooms = extract_bedrooms_bathrooms(card_text)

        # --- Property Type ---
        property_type = ""
        
        # First try to extract from meta tag (e.g., "5 bedroom penthouse" -> "penthouse")
        try:
            meta_name_element = card.find_element(By.CSS_SELECTOR, "meta[itemprop='name']")
            meta_content = meta_name_element.get_attribute("content")
            if meta_content:
                # Extract property type from meta content
                property_types = ['penthouse', 'apartment', 'house', 'flat', 'studio', 'bungalow', 
                               'terraced', 'semi-detached', 'detached', 'town house', 'end of terrace']
                
                meta_lower = meta_content.lower()
                for ptype in property_types:
                    if ptype in meta_lower:
                        property_type = ptype.title()
                        logger.info(f"✅ Found property type from meta: {property_type}")
                        break
        except NoSuchElementException:
            pass
        
        # If not found in meta, try structured elements
        if not property_type:
            property_type_selectors = [
                "[data-testid='property-type']",
                "[class*='property-type']",
                "[class*='type']"
            ]
            
            for selector in property_type_selectors:
                try:
                    type_element = card.find_element(By.CSS_SELECTOR, selector)
                    type_text = type_element.text.strip()
                    if len(type_text) > 2 and len(type_text) < 50:
                        property_type = type_text
                        logger.info(f"✅ Found property type from element: {property_type}")
                        break
                except NoSuchElementException:
                    continue
        
        # Fallback: extract from card text
        if not property_type:
            property_types = ['terrace', 'flat', 'house', 'apartment', 'bungalow', 'studio', 
                            'penthouse', 'detached', 'semi-detached', 'town house']
            for line in card_text.split("\n"):
                line_lower = line.lower().strip()
                for ptype in property_types:
                    if ptype in line_lower and len(line.strip()) < 50:
                        property_type = line.strip()
                        logger.info(f"✅ Found property type from text: {property_type}")
                        break
                if property_type:
                    break

        # --- Size ---
        size = extract_size_from_elements(card)
        
        # Fallback: extract size from text if not found in elements
        if not size:
            size_patterns = [
                r'(\d+(?:,\d+)*)\s*sq\s*ft',
                r'(\d+(?:,\d+)*)\s*sqft',
                r'(\d+(?:,\d+)*)\s*sq\.\s*ft',
                r'(\d+(?:,\d+)*)\s*square\s*feet',
                r'(\d+(?:,\d+)*)\s*sq\s*m',
                r'(\d+(?:,\d+)*)\s*sqm'
            ]
            
            for pattern in size_patterns:
                size_match = re.search(pattern, card_text, re.IGNORECASE)
                if size_match:
                    size = size_match.group()
                    logger.info(f"✅ Found size from text: {size}")
                    break
        
        # --- Date Added ---
        date_added = extract_date_added_from_elements(card)
        
        # --- Images ---
        images = extract_images_from_elements(card)

        return {
            "external_id": external_id,
                    "title": title,
                    "price": price,
                    "price_numeric": price_numeric,
            "property_type": property_type,
                    "bedrooms": bedrooms,
                    "bathrooms": bathrooms,
            "size": size,
            "listing_url": property_url,
            "image_urls": images,
            "date_added": date_added,
        }

    except Exception as e:
        logger.error(f"Error extracting property data: {e}")
        return None


# ----------------------------
# Database saving
# ----------------------------
def save_property_to_db(property_data):
    """Save property data to database"""
    try:
        if not property_data.get("listing_url"):
            return False

        with transaction.atomic():
            # Remove image_urls from property_data since we'll handle images separately
            image_urls = property_data.pop("image_urls", [])
            
            obj, created = PropertyListing.objects.update_or_create(
                listing_url=property_data["listing_url"],
                defaults=property_data,
            )
            
            # Save images to PropertyImage model
            if image_urls:
                # Clear existing images for this property
                obj.images.all().delete()
                
                for i, image_url in enumerate(image_urls):
                    if image_url and image_url.startswith("http"):
                        PropertyImage.objects.create(
                            property=obj,
                            image_url=image_url,
                            image_order=i,
                            is_primary=(i == 0),  # First image is primary
                            image_title=f"Image {i + 1}"
                        )
                        
        logger.info(f"{'✅ New' if created else '🔄 Updated'}: {property_data['title']} ({len(image_urls)} images)")
        return created
    except Exception as e:
        logger.error(f"DB Save Error: {e}")
        return False


# ----------------------------
# Selenium main scraper
# ----------------------------
def scrape_rightmove_search_results(search_url, max_pages=2):
    """Scrape property listings from Rightmove search results page"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    new_count = 0
    update_count = 0

    try:
        logger.info(f"Scraping {search_url}")
        driver.get(search_url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='PropertyCard_propertyCardContainer']"))
        )

        for page in range(1, max_pages + 1):
            cards = driver.find_elements(By.CSS_SELECTOR, "div[class*='PropertyCard_propertyCardContainer']")
            logger.info(f"Page {page}: {len(cards)} cards")

            for card in cards:
                data = extract_property_data_from_card(card)
                if data:
                    result = save_property_to_db(data)
                    if result is True:
                        new_count += 1
                    elif result is False:
                        update_count += 1

            try:
                next_button = driver.find_element(By.CSS_SELECTOR, ".pagination-direction--next")
                if next_button.is_enabled():
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(3)
                else:
                    break
            except NoSuchElementException:
                break

        logger.info(f"✅ Done: {new_count} new, {update_count} updated")

    except Exception as e:
        logger.error(f"Scraping error: {e}")
    finally:
        driver.quit()

    return new_count + update_count


# ----------------------------
# Complete property detail page scraping
# ----------------------------
def scrape_complete_property_details(driver, property_url):
    """Scrape ALL property information from individual property detail page"""
    try:
        logger.info(f"Scraping complete property details from: {property_url}")
        driver.get(property_url)
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )
        
        # Debug: Log page title to confirm we're on the right page
        page_title = driver.title
        logger.info(f"Page title: {page_title}")
        
        # Debug: Log some basic page info
        try:
            all_divs = driver.find_elements(By.CSS_SELECTOR, "div")
            logger.info(f"Found {len(all_divs)} div elements on page")
            
            all_lis = driver.find_elements(By.CSS_SELECTOR, "li")
            logger.info(f"Found {len(all_lis)} li elements on page")
        except:
            pass
        
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
        
        # Extract External ID from URL
        id_match = re.search(r'/properties/(\d+)', property_url)
        if id_match:
            property_data['external_id'] = id_match.group(1)
            logger.info(f"✅ Found external ID: {property_data['external_id']}")
        
        # Extract Title
        try:
            title_selectors = [
                "h1[itemprop='streetAddress']",
                "h1",
                "[class*='title']",
                "[class*='address']"
            ]
            
            for selector in title_selectors:
                try:
                    title_element = driver.find_element(By.CSS_SELECTOR, selector)
                    title_text = title_element.text.strip()
                    if len(title_text) > 10:
                        property_data['title'] = title_text
                        logger.info(f"✅ Found title: {title_text}")
                        break
                except:
                    continue
        except Exception as e:
            logger.warning(f"Error extracting title: {e}")
        
        # Extract Price
        try:
            price_selectors = [
                "[data-testid='price']",
                "[class*='price']",
                ".price"
            ]
            
            for selector in price_selectors:
                try:
                    price_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in price_elements:
                        price_text = element.text.strip()
                        if "£" in price_text:
                            property_data['price'] = price_text
                            property_data['price_numeric'] = extract_price_numeric(price_text)
                            logger.info(f"✅ Found price: {price_text}")
                            break
                    if property_data['price']:
                        break
                except:
                    continue
        except Exception as e:
            logger.warning(f"Error extracting price: {e}")
        
        # Extract Bedrooms and Bathrooms
        try:
            # Look for bedroom/bathroom info in various places
            bedroom_bathroom_selectors = [
                "dt",
                "[class*='bedroom']",
                "[class*='bathroom']",
                "span",
                "p"
            ]
            
            for selector in bedroom_bathroom_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip().lower()
                        
                        # Extract bedrooms
                        if 'bedroom' in text:
                            bed_match = re.search(r'(\d+)\s*bedroom', text)
                            if bed_match:
                                property_data['bedrooms'] = int(bed_match.group(1))
                                logger.info(f"✅ Found bedrooms: {property_data['bedrooms']}")
                        
                        # Extract bathrooms
                        if 'bathroom' in text:
                            bath_match = re.search(r'(\d+)\s*bathroom', text)
                            if bath_match:
                                property_data['bathrooms'] = int(bath_match.group(1))
                                logger.info(f"✅ Found bathrooms: {property_data['bathrooms']}")
                except:
                    continue
        except Exception as e:
            logger.warning(f"Error extracting bedrooms/bathrooms: {e}")
        
        # Extract Property Type
        try:
            property_type_selectors = [
                "[class*='property-type']",
                "[class*='type']",
                "span",
                "p"
            ]
            
            for selector in property_type_selectors:
                try:
                    type_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in type_elements:
                        type_text = element.text.strip()
                        if len(type_text) > 2 and len(type_text) < 50:
                            property_data['property_type'] = type_text
                            logger.info(f"✅ Found property type: {type_text}")
                            break
                    if property_data['property_type']:
                        break
                except:
                    continue
        except Exception as e:
            logger.warning(f"Error extracting property type: {e}")
        
        # Extract Size
        try:
            # Look for size in the specific structure you showed (dt/dd with SIZE)
            size_selectors = [
                "dt + dd p",
                "p._1hV1kqpVceE9m-QrX_hWDN",
                "p._3vyydJK3KMwn7-s2BEXJAf",
                "[class*='size'] p",
                "span",
                "p"
            ]
            
            for selector in size_selectors:
                try:
                    size_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in size_elements:
                        text = element.text.strip()
                        if any(unit in text.lower() for unit in ['sq ft', 'sq m', 'sqft', 'sqm']):
                            property_data['size'] = text
                            logger.info(f"✅ Found size: {text}")
                            break
                    if property_data['size']:
                        break
                except:
                    continue
            
            # If still not found, look for any text containing size information
            if not property_data['size']:
                try:
                    all_elements = driver.find_elements(By.CSS_SELECTOR, "*")
                    for element in all_elements:
                        text = element.text.strip()
                        if any(unit in text.lower() for unit in ['sq ft', 'sq m', 'sqft', 'sqm']) and len(text) < 50:
                            property_data['size'] = text
                            logger.info(f"✅ Found size from general search: {text}")
                            break
                except:
                    pass
        except Exception as e:
            logger.warning(f"Error extracting size: {e}")
        
        # Extract Description
        try:
            # Look for description in the specific structure you showed
            description_selectors = [
                "div.STw8udCxUaBUMfOOZu0iL div",
                "[data-testid='primary-layout'] div",
                ".STw8udCxUaBUMfOOZu0iL",
                "[class*='description']",
                "div:contains('Description')"
            ]
            
            for selector in description_selectors:
                try:
                    desc_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in desc_elements:
                        text = element.text.strip()
                        # Look for longer text that contains property-related keywords
                        if len(text) > 200 and any(word in text.lower() for word in ['bedroom', 'apartment', 'property', 'beautifully', 'refurbished', 'spacious', 'luxury', 'modern', 'period']):
                            property_data['description'] = text
                            logger.info(f"✅ Found description: {text[:100]}...")
                            break
                    if property_data['description']:
                        break
                except:
                    continue
            
            # If still not found, try looking for any div with substantial text
            if not property_data['description']:
                try:
                    all_divs = driver.find_elements(By.CSS_SELECTOR, "div")
                    for div in all_divs:
                        text = div.text.strip()
                        if len(text) > 300 and any(word in text.lower() for word in ['bedroom', 'apartment', 'property', 'beautifully', 'refurbished']):
                            property_data['description'] = text
                            logger.info(f"✅ Found description from general div: {text[:100]}...")
                            break
                except:
                    pass
        except Exception as e:
            logger.warning(f"Error extracting description: {e}")
        
        # Extract Key Features
        try:
            # Look for key features in the specific structure you showed
            key_features_selectors = [
                "ul._1uI3IvdF5sIuBtRIvKrreQ li",
                "ul li.1IhZ24u1NHMa5Y6gDH90A",
                "[class*='key-features'] li",
                "[class*='features'] li",
                "ul li"
            ]
            
            for selector in key_features_selectors:
                try:
                    feature_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in feature_elements:
                        text = element.text.strip()
                        # Look for typical property features
                        if text and len(text) < 100 and len(text) > 2 and any(word in text.lower() for word in ['bedroom', 'bathroom', 'reception', 'lift', 'concierge', 'garden', 'parking', 'garage', 'balcony', 'terrace']):
                            property_data['key_features'].append(text)
                            logger.info(f"✅ Found key feature: {text}")
                except:
                    continue
            
            # If still not found, try looking for any li elements with property-related text
            if not property_data['key_features']:
                try:
                    all_lis = driver.find_elements(By.CSS_SELECTOR, "li")
                    for li in all_lis:
                        text = li.text.strip()
                        if text and len(text) < 50 and len(text) > 2 and any(word in text.lower() for word in ['bedroom', 'bathroom', 'reception', 'lift', 'concierge']):
                            property_data['key_features'].append(text)
                            logger.info(f"✅ Found key feature from general li: {text}")
                except:
                    pass
        except Exception as e:
            logger.warning(f"Error extracting key features: {e}")
        
        # Extract Date Added
        try:
            date_selectors = [
                "[class*='date-added']",
                "[class*='added']",
                "span",
                "p"
            ]
            
            for selector in date_selectors:
                try:
                    date_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in date_elements:
                        text = element.text.strip()
                        if "Added on" in text or "Reduced on" in text:
                            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
                            if date_match:
                                date_str = date_match.group(1)
                                try:
                                    from datetime import datetime
                                    property_data['date_added'] = datetime.strptime(date_str, "%d/%m/%Y").date()
                                    logger.info(f"✅ Found date added: {property_data['date_added']}")
                                    break
                                except ValueError:
                                    continue
                except:
                    continue
        except Exception as e:
            logger.warning(f"Error extracting date added: {e}")
        
        # Extract Images
        try:
            image_selectors = [
                "img[src]",
                "img[data-src]",
                "[class*='photo'] img",
                "[class*='image'] img"
            ]
            
            for selector in image_selectors:
                try:
                    img_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for img in img_elements:
                        src = img.get_attribute("src") or img.get_attribute("data-src")
                        if src and src.startswith("http") and src not in property_data['image_urls']:
                            property_data['image_urls'].append(src)
                            logger.info(f"✅ Found image: {src}")
                except:
                    continue
        except Exception as e:
            logger.warning(f"Error extracting images: {e}")
        
        return property_data
        
    except Exception as e:
        logger.error(f"Error scraping complete property details: {e}")
        return None


# ----------------------------
# Enhanced property data extraction
# ----------------------------
def extract_property_data_from_card(card):
    """Extract essential property data from a property card element"""
    try:
        # --- URL ---
        try:
            link_element = card.find_element(By.CSS_SELECTOR, "a[href*='/properties/']")
            property_url = link_element.get_attribute("href")
        except NoSuchElementException:
            return None

        if not property_url:
            return None

        # --- External ID ---
        id_match = re.search(r'/properties/(\d+)', property_url)
        external_id = id_match.group(1) if id_match else None

        card_text = card.text
        title = ""

        # --- Title ---
        # First try to get the property name from meta tag (e.g., "5 bedroom penthouse")
        try:
            meta_name_element = card.find_element(By.CSS_SELECTOR, "meta[itemprop='name']")
            property_name = meta_name_element.get_attribute("content")
            if property_name and len(property_name) > 5:
                title = property_name.strip()
                logger.info(f"✅ Found property name from meta: {title}")
        except NoSuchElementException:
            pass

        # If no meta name found, try the h1 element with itemprop streetAddress
        if not title:
            try:
                h1_element = card.find_element(By.CSS_SELECTOR, "h1[itemprop='streetAddress']")
                title_text = h1_element.text.strip()
                if len(title_text) > 10:
                    title = title_text.split("\n")[0].strip()
                    logger.info(f"✅ Found title from h1: {title}")
            except NoSuchElementException:
                pass

        # Fallback to other title selectors
        if not title:
            title_selectors = [
                "h1", "h2", "h3",
                ".PropertyCardTitle_propertyCardTitle__2P9Xz",
                "[class*='summary']", "[class*='title']", "[class*='address']"
            ]
            for selector in title_selectors:
                try:
                    title_element = card.find_element(By.CSS_SELECTOR, selector)
                    title_text = title_element.text.strip()
                    if len(title_text) > 10:
                        title = title_text.split("\n")[0].strip()
                        break
                except NoSuchElementException:
                    continue

        # Final fallback: extract from card text
        if not title:
            for line in card_text.split("\n"):
                if len(line) > 20 and any(
                    word in line.lower()
                    for word in ["bedroom", "flat", "house", "apartment", "property", "road", "street"]
                ):
                    title = line.strip()
                    break
        if not title:
            title = f"Property {external_id or ''}"

        # --- Price ---
        price = ""
        price_numeric = None
        
        # Try multiple price extraction methods
        price_selectors = [
            # Rightmove specific selectors
            "[data-testid='price']",
            "[class*='PropertyCardPrice']",
            "[class*='price']",
            ".price",
            # Generic price patterns
            "[class*='amount']",
            "[class*='cost']"
        ]

        for selector in price_selectors:
            try:
                price_element = card.find_element(By.CSS_SELECTOR, selector)
                price_text = price_element.text.strip()
                if "£" in price_text:
                    price = price_text
                    price_numeric = extract_price_numeric(price)
                    logger.info(f"✅ Found price: {price}")
                    break
            except NoSuchElementException:
                continue

        # Fallback: extract price from text using regex
        if not price:
            price_patterns = [
                r"£[\d,]+(?:\.\d{2})?",
                r"£\s*[\d,]+(?:\.\d{2})?",
                r"[\d,]+(?:\.\d{2})?\s*£"
            ]
            
            for pattern in price_patterns:
                match = re.search(pattern, card_text)
                if match:
                    price = match.group().replace(" ", "")
                    price_numeric = extract_price_numeric(price)
                    logger.info(f"✅ Found price from text: {price}")
                    break

        # --- Bedrooms & Bathrooms ---
        bedrooms, bathrooms = extract_bedrooms_bathrooms_from_elements(card)
        if not bedrooms and not bathrooms:
            bedrooms, bathrooms = extract_bedrooms_bathrooms(card_text)

        # --- Property Type ---
        property_type = ""
        
        # First try to extract from meta tag (e.g., "5 bedroom penthouse" -> "penthouse")
        try:
            meta_name_element = card.find_element(By.CSS_SELECTOR, "meta[itemprop='name']")
            meta_content = meta_name_element.get_attribute("content")
            if meta_content:
                # Extract property type from meta content
                property_types = ['penthouse', 'apartment', 'house', 'flat', 'studio', 'bungalow', 
                               'terraced', 'semi-detached', 'detached', 'town house', 'end of terrace']
                
                meta_lower = meta_content.lower()
                for ptype in property_types:
                    if ptype in meta_lower:
                        property_type = ptype.title()
                        logger.info(f"✅ Found property type from meta: {property_type}")
                        break
        except NoSuchElementException:
            pass
        
        # If not found in meta, try structured elements
        if not property_type:
            property_type_selectors = [
                "[data-testid='property-type']",
                "[class*='property-type']",
                "[class*='type']"
            ]
            
            for selector in property_type_selectors:
                try:
                    type_element = card.find_element(By.CSS_SELECTOR, selector)
                    type_text = type_element.text.strip()
                    if len(type_text) > 2 and len(type_text) < 50:
                        property_type = type_text
                        logger.info(f"✅ Found property type from element: {property_type}")
                        break
                except NoSuchElementException:
                    continue
        
        # Fallback: extract from card text
        if not property_type:
            property_types = ['terrace', 'flat', 'house', 'apartment', 'bungalow', 'studio', 
                            'penthouse', 'detached', 'semi-detached', 'town house']
            for line in card_text.split("\n"):
                line_lower = line.lower().strip()
                for ptype in property_types:
                    if ptype in line_lower and len(line.strip()) < 50:
                        property_type = line.strip()
                        logger.info(f"✅ Found property type from text: {property_type}")
                        break
                if property_type:
                    break

        # --- Size ---
        size = extract_size_from_elements(card)
        
        # Fallback: extract size from text if not found in elements
        if not size:
            size_patterns = [
                r'(\d+(?:,\d+)*)\s*sq\s*ft',
                r'(\d+(?:,\d+)*)\s*sqft',
                r'(\d+(?:,\d+)*)\s*sq\.\s*ft',
                r'(\d+(?:,\d+)*)\s*square\s*feet',
                r'(\d+(?:,\d+)*)\s*sq\s*m',
                r'(\d+(?:,\d+)*)\s*sqm'
            ]
            
            for pattern in size_patterns:
                size_match = re.search(pattern, card_text, re.IGNORECASE)
                if size_match:
                    size = size_match.group()
                    logger.info(f"✅ Found size from text: {size}")
                    break
        
        # --- Date Added ---
        date_added = extract_date_added_from_elements(card)
        
        # --- Images ---
        images = extract_images_from_elements(card)

        return {
            "external_id": external_id,
            "title": title,
            "price": price,
            "price_numeric": price_numeric,
            "property_type": property_type,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "size": size,
            "listing_url": property_url,
            "image_urls": images,
            "date_added": date_added,
        }

    except Exception as e:
        logger.error(f"Error extracting property data: {e}")
        return None


# ----------------------------
# Enhanced database saving
# ----------------------------
def save_property_to_db(property_data, driver=None):
    """Save property data to database with optional detail page scraping"""
    try:
        if not property_data.get("listing_url"):
            return False

        with transaction.atomic():
            # Remove image_urls from property_data since we'll handle images separately
            image_urls = property_data.pop("image_urls", [])
            
            obj, created = PropertyListing.objects.update_or_create(
                listing_url=property_data["listing_url"],
                defaults=property_data,
            )
            
            # If we have a driver and this is a new property, scrape detailed information
            if driver and created and obj.listing_url:
                logger.info(f"Scraping detailed information for new property: {obj.title}")
                details = scrape_property_details(driver, obj.listing_url)
                
                # Update with detailed information
                if details['description']:
                    obj.description = details['description']
                if details['key_features']:
                    obj.key_features = details['key_features']
                if details['size'] and not obj.size:
                    obj.size = details['size']
                
                obj.save()
            
            # Save images to PropertyImage model
            if image_urls:
                # Clear existing images for this property
                obj.images.all().delete()
                
                for i, image_url in enumerate(image_urls):
                    if image_url and image_url.startswith("http"):
                        PropertyImage.objects.create(
                            property=obj,
                            image_url=image_url,
                            image_order=i,
                            is_primary=(i == 0),  # First image is primary
                            image_title=f"Image {i + 1}"
                        )
                        
        logger.info(f"{'✅ New' if created else '🔄 Updated'}: {property_data['title']} ({len(image_urls)} images)")
        return created
    except Exception as e:
        logger.error(f"DB Save Error: {e}")
        return False


# ----------------------------
# Enhanced Selenium main scraper
# ----------------------------
def scrape_rightmove_search_results(search_url, max_pages=2):
    """Scrape property listings from Rightmove search results page"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    new_count = 0
    update_count = 0

    try:
        logger.info(f"Scraping {search_url}")
        driver.get(search_url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='PropertyCard_propertyCardContainer']"))
        )

        for page in range(1, max_pages + 1):
            cards = driver.find_elements(By.CSS_SELECTOR, "div[class*='PropertyCard_propertyCardContainer']")
            logger.info(f"Page {page}: {len(cards)} cards")

            for card in cards:
                data = extract_property_data_from_card(card)
                if data:
                    result = save_property_to_db(data, driver)
                    if result is True:
                        new_count += 1
                    elif result is False:
                        update_count += 1

            try:
                next_button = driver.find_element(By.CSS_SELECTOR, ".pagination-direction--next")
                if next_button.is_enabled():
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(3)
                else:
                    break
            except NoSuchElementException:
                break

        logger.info(f"✅ Done: {new_count} new, {update_count} updated")

    except Exception as e:
        logger.error(f"Scraping error: {e}")
    finally:
        driver.quit()

    return new_count + update_count


# ----------------------------
# New approach: Get URLs from search results, then scrape each detail page
# ----------------------------
def scrape_property_urls_from_search(search_url, max_pages=2):
    """Get property URLs from search results page"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    property_urls = []

    try:
        logger.info(f"Getting property URLs from: {search_url}")
        driver.get(search_url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='PropertyCard_propertyCardContainer']"))
        )

        for page in range(1, max_pages + 1):
            cards = driver.find_elements(By.CSS_SELECTOR, "div[class*='PropertyCard_propertyCardContainer']")
            logger.info(f"Page {page}: {len(cards)} cards")

            for card in cards:
                try:
                    link_element = card.find_element(By.CSS_SELECTOR, "a[href*='/properties/']")
                    property_url = link_element.get_attribute("href")
                    if property_url and property_url not in property_urls:
                        property_urls.append(property_url)
                        logger.info(f"✅ Found property URL: {property_url}")
                except NoSuchElementException:
                    continue

            try:
                next_button = driver.find_element(By.CSS_SELECTOR, ".pagination-direction--next")
                if next_button.is_enabled():
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(3)
                else:
                    break
            except NoSuchElementException:
                break

        logger.info(f"✅ Found {len(property_urls)} property URLs")

    except Exception as e:
        logger.error(f"Error getting property URLs: {e}")
    finally:
        driver.quit()

    return property_urls


def scrape_properties_from_detail_pages(search_url, max_pages=2):
    """Main function: Get URLs from search, then scrape each detail page completely"""
    # Step 1: Get property URLs from search results
    property_urls = scrape_property_urls_from_search(search_url, max_pages)
    
    if not property_urls:
        logger.error("No property URLs found!")
        return 0
    
    # Step 2: Scrape each property detail page
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    new_count = 0
    update_count = 0

    try:
        logger.info(f"Scraping {len(property_urls)} property detail pages...")
        
        for i, property_url in enumerate(property_urls, 1):
            logger.info(f"Scraping property {i}/{len(property_urls)}: {property_url}")
            
            # Scrape complete property details
            property_data = scrape_complete_property_details(driver, property_url)
            
            if property_data:
                # Save to database
                result = save_property_to_db_simple(property_data)
                if result is True:
                    new_count += 1
                elif result is False:
                    update_count += 1
            
            # Small delay between requests
            time.sleep(1)

        logger.info(f"✅ Done: {new_count} new, {update_count} updated")

    except Exception as e:
        logger.error(f"Scraping error: {e}")
    finally:
        driver.quit()

    return new_count + update_count


def save_property_to_db_simple(property_data):
    """Simple database save function for complete property data"""
    try:
        if not property_data.get("listing_url"):
            logger.error("No listing URL provided")
            return False

        with transaction.atomic():
            # Remove image_urls from property_data since we'll handle images separately
            image_urls = property_data.pop("image_urls", [])
            
            # Log what we're trying to save
            logger.info(f"Saving property: {property_data.get('title', 'Unknown')}")
            logger.info(f"Description length: {len(property_data.get('description', ''))}")
            logger.info(f"Key features count: {len(property_data.get('key_features', []))}")
            logger.info(f"Size: {property_data.get('size', 'None')}")
            
            obj, created = PropertyListing.objects.update_or_create(
                listing_url=property_data["listing_url"],
                defaults=property_data,
            )
            
            # Log what was actually saved
            logger.info(f"Saved property: {obj.title}")
            logger.info(f"Saved description length: {len(obj.description) if obj.description else 0}")
            logger.info(f"Saved key features count: {len(obj.key_features) if obj.key_features else 0}")
            logger.info(f"Saved size: {obj.size}")
            
            # Save images to PropertyImage model
            if image_urls:
                # Clear existing images for this property
                obj.images.all().delete()
                
                for i, image_url in enumerate(image_urls):
                    if image_url and image_url.startswith("http"):
                        PropertyImage.objects.create(
                            property=obj,
                            image_url=image_url,
                            image_order=i,
                            is_primary=(i == 0),  # First image is primary
                            image_title=f"Image {i + 1}"
                        )
                        
        logger.info(f"{'✅ New' if created else '🔄 Updated'}: {property_data['title']} ({len(image_urls)} images)")
        return created
    except Exception as e:
        logger.error(f"DB Save Error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


# ----------------------------
# Public function
# ----------------------------
def scrape_listing_selenium(url):
    return scrape_properties_from_detail_pages(url, max_pages=2)
