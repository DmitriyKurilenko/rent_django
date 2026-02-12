# Changelog

All notable changes to BoatRental project will be documented in this file.

## [1.2.0] - 2026-02-01

### ✨ Added - Quick Offer Creation Feature
- **One-click offer creation** from boat detail pages
- **Modal interface** with role-based offer type selection
- **Role-based permissions**:
  - `captain` role: Captain (agent) offers only
  - `manager`/`admin` roles: Choice between captain and tourist offers
- **Dynamic pricing**: Auto-fetched from API based on dates
- **Instant creation**: No form page, direct offer generation
- New view: `quick_create_offer()` in `boats/views.py`
- New URL: `/boat/<slug>/create-offer/`
- Modal UI in `templates/boats/detail.html` with JavaScript logic

### 📚 Documentation Updates
- **README.md**: Complete project overview with quick start
- **Production checklist**: 50+ items for deployment verification
- **.env.example**: Comprehensive unified environment template
- **.github/copilot-instructions.md**: Updated with quick offer creation patterns
- Added architecture diagrams and data flow explanations

### 🔧 Improvements
- Enhanced `create_offer` view with session-based prefill support
- Better error handling in offer creation flow
- Improved role-based permission checks
- Added `has_meal` option for tourist offers

### 🐛 Bug Fixes
- Fixed source_url field type (TextField instead of URLField) for long URLs
- Improved price calculation logic for different offer types
- Better handling of missing boat data in offer creation

---

## [1.1.0] - 2026-01-25

### ✨ Added - Multi-Language Support
- 5 languages: English, Russian, German, Spanish, French
- URL-based language switching: `/ru/boat/`, `/en/boat/`, etc.
- Language-aware API requests (ru_RU, en_EN, de_DE, es_ES, fr_FR)
- Translated boat descriptions and UI elements
- Fallback logic for missing translations

### 📚 Documentation
- Complete I18N documentation suite in `docs/`
- Multi-language architecture guide
- Code examples and quick reference
- Setup and deployment instructions

---

## [1.0.0] - 2026-01-15

### 🎉 Initial Release

#### Core Features
- **Boat Management**: 28,000+ boats from boataround.com
- **Dual-layer integration**: REST API + HTML parsing
- **Smart caching**: ParsedBoat model with 24-hour TTL
- **Async parsing**: Celery-based bulk import (15-20 hours)
- **Search & filtering**: Fast API-based search with pagination
- **User roles**: Tourist, Captain, Manager, Admin

#### Technical Stack
- Django 4.2 on Python 3.8+
- PostgreSQL 15 with JSONField
- Redis 7 for Celery broker
- Celery 5.3 with retry logic
- Alpine.js + JSON API frontend
- BeautifulSoup4 for parsing
- VK Cloud S3 + Free CDN for images

#### Deployment
- Docker Compose for local development
- Ubuntu 20.04+ production guide
- Gunicorn + Nginx + systemd
- Let's Encrypt SSL support
- Comprehensive documentation

---

## Future Roadmap

### [1.3.0] - Planned
- [ ] Advanced search filters (price range, year, manufacturer)
- [ ] Booking system integration
- [ ] Payment gateway integration (Stripe/PayPal)
- [ ] Email notifications for offers
- [ ] SMS notifications via Twilio
- [ ] Real-time availability check
- [ ] Favorites/wishlist for tourists

### [2.0.0] - Future
- [ ] Mobile app (React Native)
- [ ] Progressive Web App (PWA)
- [ ] Advanced analytics dashboard
- [ ] AI-powered boat recommendations
- [ ] Customer reviews and ratings
- [ ] Multi-currency support
- [ ] Calendar integration
- [ ] WhatsApp Business API integration

---

## Version Format

We follow [Semantic Versioning](https://semver.org/):
- MAJOR version: Incompatible API changes
- MINOR version: New functionality (backward compatible)
- PATCH version: Bug fixes (backward compatible)

---

## Support

For bugs and feature requests, please open an issue on GitHub.

For production support, contact the development team.
