# API Documentation

## Table of Contents
- [Overview](#overview)
- [Authentication](#authentication)
- [Base URLs](#base-urls)
- [Endpoints](#endpoints)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)

---

## Overview

BoatRental provides REST API endpoints for boat search, autocomplete, and offer management. The API returns JSON responses and follows RESTful conventions.

### API Version
Current version: `v1`

### Content Type
All requests and responses use `application/json` unless specified otherwise.

---

## Authentication

### Session Authentication
Most endpoints require user authentication via Django session cookies.

```bash
# Login first
curl -X POST https://api.boatrental.com/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "user@example.com", "password": "your_password"}'
```

### Required Headers
```
Cookie: sessionid=<session_id>
X-CSRFToken: <csrf_token>
```

---

## Base URLs

### Development
```
http://localhost:8000
```

### Production
```
https://api.boatrental.com
```

---

## Endpoints

### 1. Boat Search

Search for available boats with filters.

**Endpoint:** `GET /boat-search/`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `destination` | string | Yes | Destination slug (e.g., `turkey`) |
| `check_in` | string | Yes | Check-in date (YYYY-MM-DD) |
| `check_out` | string | Yes | Check-out date (YYYY-MM-DD) |
| `page` | integer | No | Page number (default: 1) |
| `limit` | integer | No | Results per page (default: 18) |

**Example Request:**
```bash
curl -X GET 'https://api.boatrental.com/boat-search/?destination=turkey&check_in=2026-06-01&check_out=2026-06-08&page=1'
```

**Example Response:**
```json
{
  "results": [
    {
      "id": "62b96d157a9323583a5a4880",
      "slug": "bavaria-cruiser-46-2022",
      "title": "Bavaria Cruiser 46",
      "location": "Fethiye, Turkey",
      "price_per_day": 450.00,
      "currency": "EUR",
      "image_url": "https://imageresizer.yachtsbt.com/...",
      "cabins": 4,
      "berths": 8,
      "length": 14.27,
      "manufacturer": "Bavaria",
      "year": 2022
    }
  ],
  "total": 156,
  "page": 1,
  "pages": 9,
  "has_next": true,
  "has_previous": false
}
```

---

### 2. Autocomplete

Get location suggestions for search input.

**Endpoint:** `GET /autocomplete/`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query (min 2 chars) |

**Example Request:**
```bash
curl -X GET 'https://api.boatrental.com/autocomplete/?query=turk'
```

**Example Response:**
```json
{
  "suggestions": [
    {
      "label": "Turkey (Fethiye, Marmaris, Bodrum)",
      "value": "turkey",
      "country": "TR",
      "marinas": 15
    },
    {
      "label": "Turkiye - Bodrum",
      "value": "bodrum-turkey",
      "country": "TR",
      "marinas": 3
    }
  ]
}
```

---

### 3. Boat Detail

Get detailed information about a specific boat.

**Endpoint:** `GET /boat/<boat_id>/`

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `boat_id` | string | Yes | Unique boat identifier |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `check_in` | string | No | Check-in date for pricing |
| `check_out` | string | No | Check-out date for pricing |

**Example Request:**
```bash
curl -X GET 'https://api.boatrental.com/boat/62b96d157a9323583a5a4880/?check_in=2026-06-01&check_out=2026-06-08'
```

**Example Response:**
```json
{
  "boat_id": "62b96d157a9323583a5a4880",
  "slug": "bavaria-cruiser-46-2022",
  "boat_info": {
    "title": "Bavaria Cruiser 46",
    "location": "Fethiye Marina, Turkey",
    "manufacturer": "Bavaria",
    "model": "Cruiser 46",
    "year": 2022,
    "length": 14.27,
    "cabins": 4,
    "berths": 8,
    "heads": 2,
    "engines": 1,
    "power": "75 HP",
    "fuel_type": "Diesel"
  },
  "images": [
    {
      "thumb": "https://imageresizer.yachtsbt.com/...",
      "main_img": "/boats/62b96d157a9323583a5a4880/img1.jpg"
    }
  ],
  "specs": {
    "beam": 4.35,
    "draft": 2.05,
    "fuel_capacity": 210,
    "water_capacity": 480,
    "engines": 1,
    "max_speed": 8
  },
  "extras": ["WiFi", "Air Conditioning", "Generator", "Autopilot"],
  "pricing": {
    "base_price": 3150.00,
    "currency": "EUR",
    "rental_days": 7,
    "price_per_day": 450.00
  }
}
```

---

### 4. Create Offer (Quick)

Create an offer directly from boat detail page.

**Endpoint:** `POST /boat/<boat_slug>/create-offer/`

**Authentication:** Required

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `boat_slug` | string | Yes | Boat slug identifier |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `check_in` | string | Yes | Check-in date (YYYY-MM-DD) |
| `check_out` | string | Yes | Check-out date (YYYY-MM-DD) |

**Request Body:**
```json
{
  "offer_type": "captain",
  "has_meal": false
}
```

**Example Request:**
```bash
curl -X POST 'https://api.boatrental.com/boat/bavaria-cruiser-46-2022/create-offer/?check_in=2026-06-01&check_out=2026-06-08' \
  -H "Content-Type: application/json" \
  -H "Cookie: sessionid=<session_id>" \
  -H "X-CSRFToken: <csrf_token>" \
  -d '{"offer_type": "captain", "has_meal": false}'
```

**Example Response:**
```json
{
  "status": "success",
  "offer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "offer_url": "/offer/a1b2c3d4-e5f6-7890-abcd-ef1234567890/",
  "message": "Offer created successfully"
}
```

---

### 5. Offer Detail

Get offer information by UUID.

**Endpoint:** `GET /offer/<uuid>/`

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `uuid` | string | Yes | Offer UUID |

**Example Request:**
```bash
curl -X GET 'https://api.boatrental.com/offer/a1b2c3d4-e5f6-7890-abcd-ef1234567890/'
```

**Example Response:**
```json
{
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "offer_type": "captain",
  "boat": {
    "title": "Bavaria Cruiser 46",
    "location": "Fethiye, Turkey",
    "images": [...]
  },
  "dates": {
    "check_in": "2026-06-01",
    "check_out": "2026-06-08",
    "rental_days": 7
  },
  "pricing": {
    "base_price": 3150.00,
    "extras": 500.00,
    "total": 3650.00,
    "currency": "EUR"
  },
  "created_at": "2026-02-01T10:30:00Z",
  "views": 5
}
```

---

### 6. My Offers List

Get all offers created by authenticated user.

**Endpoint:** `GET /my-offers/`

**Authentication:** Required

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `page` | integer | No | Page number (default: 1) |
| `offer_type` | string | No | Filter by type (`captain` or `tourist`) |

**Example Request:**
```bash
curl -X GET 'https://api.boatrental.com/my-offers/?page=1' \
  -H "Cookie: sessionid=<session_id>"
```

**Example Response:**
```json
{
  "results": [
    {
      "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "boat_title": "Bavaria Cruiser 46",
      "check_in": "2026-06-01",
      "check_out": "2026-06-08",
      "total_price": 3650.00,
      "currency": "EUR",
      "offer_type": "captain",
      "created_at": "2026-02-01T10:30:00Z",
      "views": 5
    }
  ],
  "total": 12,
  "page": 1,
  "pages": 2
}
```

---

## Error Handling

### Error Response Format
```json
{
  "error": "Error message",
  "code": "ERROR_CODE",
  "details": {}
}
```

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 201 | Created | Resource created |
| 400 | Bad Request | Invalid parameters |
| 401 | Unauthorized | Authentication required |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |

### Common Error Codes

**VALIDATION_ERROR**
```json
{
  "error": "Validation failed",
  "code": "VALIDATION_ERROR",
  "details": {
    "check_in": ["This field is required"],
    "check_out": ["Invalid date format"]
  }
}
```

**AUTHENTICATION_REQUIRED**
```json
{
  "error": "Authentication credentials required",
  "code": "AUTHENTICATION_REQUIRED"
}
```

**PERMISSION_DENIED**
```json
{
  "error": "You don't have permission to perform this action",
  "code": "PERMISSION_DENIED"
}
```

**BOAT_NOT_FOUND**
```json
{
  "error": "Boat not found",
  "code": "BOAT_NOT_FOUND",
  "details": {
    "boat_id": "invalid_id"
  }
}
```

---

## Rate Limiting

### Limits

| Endpoint Type | Rate Limit | Window |
|--------------|------------|--------|
| Search/API | 30 req/min | Per IP |
| General | 10 req/min | Per IP |
| Create Offer | 5 req/min | Per User |

### Rate Limit Headers

**Response Headers:**
```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 25
X-RateLimit-Reset: 1704110400
```

### Rate Limit Exceeded Response
```json
{
  "error": "Rate limit exceeded",
  "code": "RATE_LIMIT_EXCEEDED",
  "details": {
    "retry_after": 60
  }
}
```

---

## Example Usage

### Complete Workflow: Search → Detail → Create Offer

```python
import requests

BASE_URL = "https://api.boatrental.com"

# Step 1: Login
session = requests.Session()
login_response = session.post(
    f"{BASE_URL}/accounts/login/",
    json={"username": "user@example.com", "password": "password"}
)

# Step 2: Search boats
search_response = session.get(
    f"{BASE_URL}/boat-search/",
    params={
        "destination": "turkey",
        "check_in": "2026-06-01",
        "check_out": "2026-06-08"
    }
)
boats = search_response.json()["results"]

# Step 3: Get boat details
boat_slug = boats[0]["slug"]
detail_response = session.get(
    f"{BASE_URL}/boat/{boat_slug}/",
    params={"check_in": "2026-06-01", "check_out": "2026-06-08"}
)
boat_detail = detail_response.json()

# Step 4: Create offer
offer_response = session.post(
    f"{BASE_URL}/boat/{boat_slug}/create-offer/",
    params={"check_in": "2026-06-01", "check_out": "2026-06-08"},
    json={"offer_type": "captain", "has_meal": False}
)
offer = offer_response.json()

print(f"Offer created: {offer['offer_url']}")
```

---

## Integration Examples

### JavaScript (Fetch API)

```javascript
const BASE_URL = 'https://api.boatrental.com';

// Search boats
async function searchBoats(destination, checkIn, checkOut) {
  const params = new URLSearchParams({
    destination,
    check_in: checkIn,
    check_out: checkOut
  });
  
  const response = await fetch(`${BASE_URL}/boat-search/?${params}`, {
    credentials: 'include'  // Include cookies
  });
  
  return await response.json();
}

// Create offer
async function createOffer(boatSlug, checkIn, checkOut, offerType) {
  const params = new URLSearchParams({ check_in: checkIn, check_out: checkOut });
  
  const response = await fetch(
    `${BASE_URL}/boat/${boatSlug}/create-offer/?${params}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
      },
      credentials: 'include',
      body: JSON.stringify({ offer_type: offerType, has_meal: false })
    }
  );
  
  return await response.json();
}
```

---

## Support

For API support or questions:
- 📧 Email: api-support@boatrental.com
- 📖 Documentation: https://docs.boatrental.com
- 💬 Discord: https://discord.gg/boatrental

---

**Last Updated:** 2026-02-01
