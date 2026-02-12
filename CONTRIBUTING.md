# Contributing to BoatRental

First off, thank you for considering contributing to BoatRental! 🎉

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Pull Request Process](#pull-request-process)
- [Testing Guidelines](#testing-guidelines)

---

## Code of Conduct

This project adheres to a simple code of conduct:
- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on what is best for the community
- Show empathy towards others

---

## Getting Started

### Prerequisites
- Python 3.8+
- Docker & Docker Compose
- Git
- Basic Django knowledge

### Quick Setup
```bash
# Clone the repository
git clone <repository-url>
cd rent_django

# Start development environment
docker-compose up

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Visit http://localhost:8000
```

---

## Development Setup

### 1. Fork and Clone
```bash
# Fork the repository on GitHub
# Clone your fork
git clone https://github.com/YOUR_USERNAME/rent_django.git
cd rent_django

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL_OWNER/rent_django.git
```

### 2. Create Feature Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

### 3. Development Environment
```bash
# Use Docker (recommended)
docker-compose up

# Or local virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

---

## How to Contribute

### Reporting Bugs
1. Check if the bug has already been reported in Issues
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots if applicable
   - Your environment (OS, Python version, etc.)

### Suggesting Features
1. Check existing feature requests in Issues
2. Create a new issue with `[Feature Request]` prefix
3. Describe the feature and its use case
4. Explain why it would be valuable

### Code Contributions
1. Pick an issue or create one
2. Comment on the issue to claim it
3. Fork the repository
4. Create a feature branch
5. Make your changes
6. Write/update tests
7. Update documentation
8. Submit a pull request

---

## Coding Standards

### Python Style Guide
- Follow PEP 8
- Use meaningful variable names
- Add docstrings to functions and classes
- Keep functions small and focused

```python
def parse_boat_detail(boat_slug):
    """
    Parse boat details from external API.
    
    Args:
        boat_slug (str): Unique boat identifier
        
    Returns:
        dict: Parsed boat data with images, specs, and pricing
        
    Raises:
        ValueError: If boat_slug is invalid
    """
    # Implementation
```

### Django Best Practices
- Use Django ORM (avoid raw SQL)
- Always use `get_object_or_404()` for single objects
- Use class-based views when appropriate
- Add `verbose_name` to model fields
- Use Django forms for validation

### Frontend (Alpine.js + JSON API)
- Keep JavaScript minimal
- Use Alpine.js for local interactivity and state
- Use `fetch` + JSON responses for dynamic updates
- Follow Tailwind CSS/DaisyUI conventions

### Naming Conventions
```python
# Models: CamelCase
class ParsedBoat(models.Model):
    pass

# Views: snake_case
def boat_detail_api(request, boat_id):
    pass

# URLs: kebab-case
path('boat-search/', views.boat_search, name='boat_search')

# Variables: snake_case
boat_data = parse_boat(slug)
```

---

## Pull Request Process

### Before Submitting
- [ ] Code follows project style guide
- [ ] All tests pass: `python manage.py test`
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] Commit messages are clear and descriptive
- [ ] Branch is up to date with main

### PR Template
```markdown
## Description
Brief description of what this PR does

## Type of Change
- [ ] Bug fix (non-breaking change)
- [ ] New feature (non-breaking change)
- [ ] Breaking change
- [ ] Documentation update

## Testing
How has this been tested?

## Screenshots (if applicable)
Add screenshots here

## Checklist
- [ ] Code follows style guide
- [ ] Tests pass
- [ ] Documentation updated
```

### Review Process
1. Maintainer will review within 48 hours
2. Address any requested changes
3. Once approved, maintainer will merge
4. Your contribution will be in the next release!

---

## Testing Guidelines

### Running Tests
```bash
# Run all tests
docker-compose exec web python manage.py test

# Run specific app tests
docker-compose exec web python manage.py test boats

# Run with coverage
docker-compose exec web coverage run --source='.' manage.py test
docker-compose exec web coverage report
```

### Writing Tests
```python
from django.test import TestCase
from boats.models import ParsedBoat

class ParsedBoatTestCase(TestCase):
    def setUp(self):
        """Set up test data"""
        self.boat = ParsedBoat.objects.create(
            boat_id='test123',
            slug='test-boat',
            boat_data={'title': 'Test Boat'}
        )
    
    def test_boat_creation(self):
        """Test boat is created correctly"""
        self.assertEqual(self.boat.slug, 'test-boat')
        self.assertTrue(self.boat.boat_data)
```

### Test Coverage Requirements
- New features: 80%+ coverage
- Bug fixes: Add test that catches the bug
- Critical paths: 90%+ coverage

---

## Common Development Tasks

### Adding a New Model
1. Add model to `boats/models.py`
2. Create migration: `python manage.py makemigrations`
3. Run migration: `python manage.py migrate`
4. Register in admin: `boats/admin.py`
5. Write tests: `boats/tests/test_models.py`

### Adding a New View
1. Add view to `boats/views.py`
2. Add URL to `boats/urls.py`
3. Create template in `templates/boats/`
4. Write tests: `boats/tests/test_views.py`

### Adding Translation
1. Mark strings for translation: `{% trans "Text" %}`
2. Generate messages: `python manage.py makemessages -l ru`
3. Edit `.po` files in `locale/`
4. Compile: `python manage.py compilemessages`

### Debugging
```python
# Use Django shell
python manage.py shell

# Import models
from boats.models import ParsedBoat

# Query data
ParsedBoat.objects.all()

# Use debugger
import pdb; pdb.set_trace()
```

---

## Documentation

### Code Comments
- Explain WHY, not WHAT
- Update comments when code changes
- Use docstrings for functions/classes

### README Updates
- Keep README.md current
- Add examples for new features
- Update installation steps if needed

### API Documentation
- Document new endpoints
- Include request/response examples
- Note any breaking changes

---

## Release Process

### Versioning
We use Semantic Versioning (semver):
- MAJOR: Breaking changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes

### Changelog
Update `CHANGELOG.md` with:
- New features
- Bug fixes
- Breaking changes
- Deprecations

---

## Questions?

- 📖 Read [.github/copilot-instructions.md](.github/copilot-instructions.md)
- 💬 Open a GitHub Discussion
- 📧 Contact maintainers
- 🐛 Create an Issue

---

## Recognition

Contributors will be:
- Listed in `CONTRIBUTORS.md`
- Mentioned in release notes
- Credited in commit messages

Thank you for making BoatRental better! 🚤✨
