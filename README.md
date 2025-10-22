# Rightmove Property Scraper (Simplified)

A simple Django + Celery web scraper for Rightmove properties with only essential fields.

## 🎯 What it scrapes

- **Price** (text and numeric)
- **Title** 
- **Property Type** (House, Flat, etc.)
- **Bedrooms** count
- **Bathrooms** count
- **Size** (square feet)
- **Multiple Images** URLs
- **Date Added**
- **Key Features** (Garden, Parking, etc.)
- **Description** (basic)

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Setup Database
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

### 3. Start Services

**Terminal 1 - Django Server:**
```bash
python manage.py runserver
```

**Terminal 2 - Celery Worker:**
```bash
celery -A webscraper worker --loglevel=info
```

**Terminal 3 - Redis (if not running):**
```bash
redis-server
```

### 4. Trigger Scraping

**Option A - API (Recommended):**
```bash
curl -X POST http://127.0.0.1:8000/api/scrape/ \
  -H "Content-Type: application/json" \
  -d '{"search_url": "https://www.rightmove.co.uk/property-for-sale/find.html?searchLocation=London&useLocationIdentifier=true&locationIdentifier=REGION%5E87490&_includeSSTC=on&index=0&sortType=2&channel=BUY&transactionType=BUY&displayLocationIdentifier=London-87490.html&radius=40.0", "max_pages": 3}'
```

**Option B - Management Command:**
```bash
python manage.py scrape_celery --url "https://www.rightmove.co.uk/property-for-sale/find.html?searchLocation=London&useLocationIdentifier=true&locationIdentifier=REGION%5E87490&_includeSSTC=on&index=0&sortType=2&channel=BUY&transactionType=BUY&displayLocationIdentifier=London-87490.html&radius=40.0" --pages 3
```

## 📊 API Endpoints

- `POST /api/scrape/` - Trigger scraping
- `GET /api/properties/` - Get scraped properties
- `GET /api/stats/` - Get scraping statistics

## 🔍 View Data

- **Django Admin:** http://127.0.0.1:8000/admin/
- **API:** http://127.0.0.1:8000/api/properties/

## 🧪 Test

```bash
python test_simple.py
```

## 📁 Project Structure

```
WebScrapper/
├── scraper/
│   ├── models.py          # PropertyListing model (simplified)
│   ├── views.py           # API endpoints
│   ├── urls.py            # URL routing
│   ├── admin.py           # Django admin
│   ├── scraper.py         # Core scraping logic
│   ├── tasks.py           # Celery tasks
│   └── management/commands/scrape_celery.py
├── webscraper/
│   ├── settings.py        # Django settings
│   ├── celery.py          # Celery configuration
│   └── urls.py            # Main URL routing
├── requirements.txt       # Dependencies
└── test_simple.py         # Test script
```

## ⚙️ Configuration

The scraper is configured to run headless and extract only essential property data. All unnecessary fields have been removed for simplicity.

## 🚨 Notes

- Make sure Redis is running for Celery
- Chrome browser must be installed
- Scraping runs in background via Celery
- Data is stored in SQLite database
- Admin interface available for data management