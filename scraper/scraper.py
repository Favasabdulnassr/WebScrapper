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
        # Find all dt elements
        dt_elements = card.find_elements(By.CSS_SELECTOR, "dt")
        
        for dt in dt_elements:
            dt_text = dt.text.strip().upper()
            
            if "SIZE" in dt_text:
                try:
                    # Find the next sibling dd element
                    dd_element = dt.find_element(By.XPATH, "following-sibling::dd")
                    
                    # Look for p tags with size information
                    p_elements = dd_element.find_elements(By.CSS_SELECTOR, "p")
                    for p in p_elements:
                        p_text = p.text.strip()
                        if "sq ft" in p_text.lower() or "sq m" in p_text.lower():
                            size = p_text
                            logger.info(f"✅ Found size: {size}")
                            break
                except:
                    continue
                    
    except Exception as e:
        logger.warning(f"Error extracting size: {e}")
    
    return size


def extract_date_added_from_elements(card):
    """Extract date added from HTML elements"""
    date_added = None
    
    try:
        # Look for divs containing "Added on" text
        date_selectors = [
            "div[class*='_2nk2x6QhNB1UrxdI5KpvaF']",  # Specific class from your HTML
            "div:contains('Added on')",
            "[class*='date']",
            "[class*='added']"
        ]
        
        for selector in date_selectors:
            try:
                elements = card.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    text = element.text.strip()
                    if "Added on" in text or "Reduced on" in text:
                        # Extract date from text like "Added on 14/08/2025"
                        date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
                        if date_match:
                            date_str = date_match.group(1)
                            try:
                                from datetime import datetime
                                date_added = datetime.strptime(date_str, "%d/%m/%Y").date()
                                logger.info(f"✅ Found date added: {date_added}")
                                break
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
        
        # Look for carousel images
        carousel_selectors = [
            "a[itemprop='photo']",
            "[data-testid='photo-collage'] a",
            "[class*='carousel'] a",
            "[class*='photo'] a"
        ]
        
        for selector in carousel_selectors:
            try:
                img_elements = card.find_elements(By.CSS_SELECTOR, selector)
                for img in img_elements:
                    # Try to get image URL from various attributes
                    src = img.get_attribute("href") or img.get_attribute("data-src") or img.get_attribute("src")
                    if src and src.startswith("http") and src not in images:
                        images.append(src)
            except:
                continue
        
        # Fallback: look for regular img tags
        img_elements = card.find_elements(By.CSS_SELECTOR, "img")
        for img in img_elements:
            src = img.get_attribute("src")
            if src and src.startswith("http") and src not in images:
                images.append(src)
                
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
        price_selectors = [".PropertyCardPrice_propertyCardPrice__2P9Xz", "[class*='price']", ".price"]

        for selector in price_selectors:
            try:
                price_element = card.find_element(By.CSS_SELECTOR, selector)
                price_text = price_element.text.strip()
                if "£" in price_text:
                    price = price_text
                    price_numeric = extract_price_numeric(price)
                    break
            except NoSuchElementException:
                continue

        if not price:
            match = re.search(r"£[\d,]+(?:\.\d{2})?", card_text)
            if match:
                price = match.group()
                price_numeric = extract_price_numeric(price)

        # --- Bedrooms & Bathrooms ---
        bedrooms, bathrooms = extract_bedrooms_bathrooms_from_elements(card)
        if not bedrooms and not bathrooms:
            bedrooms, bathrooms = extract_bedrooms_bathrooms(card_text)

        # --- Property Type ---
        property_type = ""
        for line in card_text.split("\n"):
            if any(
                word in line.lower()
                for word in ["terrace", "flat", "house", "apartment", "bungalow", "studio"]
            ):
                property_type = line.strip()
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
# Public function
# ----------------------------
def scrape_listing_selenium(url):
    return scrape_rightmove_search_results(url, max_pages=2)
