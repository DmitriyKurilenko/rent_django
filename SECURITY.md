# Security Policy

## 🔒 Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.2.x   | :white_check_mark: |
| 1.1.x   | :white_check_mark: |
| 1.0.x   | :x:                |
| < 1.0   | :x:                |

---

## 🚨 Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public GitHub issues.**

### How to Report

1. **Email Security Team** (preferred)
   - Send details to: security@yourcompany.com
   - Use PGP encryption if possible
   - Include "SECURITY" in subject line

2. **GitHub Security Advisory**
   - Use GitHub's private vulnerability reporting
   - Navigate to Security tab → Advisories → New draft

### What to Include

- **Description**: Clear explanation of the vulnerability
- **Impact**: What an attacker could achieve
- **Steps to Reproduce**: Detailed steps to reproduce the issue
- **Proof of Concept**: Code or screenshots (if applicable)
- **Suggested Fix**: If you have ideas for remediation
- **Environment**: Version, OS, configuration details

### Example Report Template

```markdown
**Vulnerability Type**: SQL Injection / XSS / CSRF / etc.

**Affected Component**: boats/views.py line 123

**Impact**: High / Medium / Low
- Description of what attacker can do

**Steps to Reproduce**:
1. Navigate to /boat/detail/
2. Enter payload: <script>alert('XSS')</script>
3. Submit form
4. Observe reflected XSS

**Environment**:
- Version: 1.2.0
- Python: 3.10
- Django: 4.2
- OS: Ubuntu 22.04

**Suggested Fix**:
Use Django's built-in escape() function
```

---

## 🛡️ Security Response Process

### Timeline
- **Initial Response**: Within 48 hours
- **Assessment**: Within 7 days
- **Fix Released**: Within 30 days (critical: 7 days)
- **Public Disclosure**: After patch is available

### Severity Classification

**Critical (CVSS 9.0-10.0)**
- Remote code execution
- SQL injection
- Authentication bypass
- Fix within 7 days

**High (CVSS 7.0-8.9)**
- Privilege escalation
- XSS in admin panel
- Sensitive data exposure
- Fix within 14 days

**Medium (CVSS 4.0-6.9)**
- CSRF vulnerabilities
- Information disclosure
- Denial of service
- Fix within 30 days

**Low (CVSS 0.1-3.9)**
- Minor information leaks
- Non-exploitable bugs
- Fix in next release

---

## 🔐 Security Best Practices

### For Developers

#### Django Security Settings
```python
# Production settings.py
DEBUG = False
SECRET_KEY = os.environ.get('SECRET_KEY')  # Never hardcode
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
```

#### Input Validation
```python
# Always validate and sanitize user input
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

validator = URLValidator()
try:
    validator(user_input)
except ValidationError:
    return HttpResponseBadRequest("Invalid URL")
```

#### SQL Injection Prevention
```python
# ✅ GOOD: Use Django ORM
boats = ParsedBoat.objects.filter(slug=user_slug)

# ❌ BAD: Raw SQL with string interpolation
boats = ParsedBoat.objects.raw(f"SELECT * FROM boats WHERE slug='{user_slug}'")

# ✅ ACCEPTABLE: Raw SQL with parameterization
boats = ParsedBoat.objects.raw("SELECT * FROM boats WHERE slug=%s", [user_slug])
```

#### XSS Prevention
```django
{# ✅ GOOD: Auto-escaped #}
{{ boat.title }}

{# ❌ BAD: Unescaped #}
{{ boat.title|safe }}

{# ✅ GOOD: Explicit escaping when needed #}
{{ boat.description|escape }}
```

#### Authentication
```python
from django.contrib.auth.decorators import login_required

@login_required
def sensitive_view(request):
    # Only authenticated users
    pass

# Check permissions
if not request.user.profile.can_create_offers():
    return HttpResponseForbidden()
```

### For Deployers

#### Server Security
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Configure firewall
sudo ufw allow 22/tcp  # SSH
sudo ufw allow 80/tcp  # HTTP
sudo ufw allow 443/tcp # HTTPS
sudo ufw enable

# Disable root login
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Setup fail2ban
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
```

#### Database Security
```bash
# Strong PostgreSQL password
CREATE USER boatuser WITH PASSWORD '<strong-random-password>';

# Restrict connections
# Edit /etc/postgresql/15/main/pg_hba.conf
host    boatdb    boatuser    127.0.0.1/32    md5

# Disable remote root access
# Edit /etc/postgresql/15/main/postgresql.conf
listen_addresses = 'localhost'
```

#### SSL/TLS Configuration
```nginx
# Nginx SSL best practices
ssl_protocols TLSv1.2 TLSv1.3;
ssl_prefer_server_ciphers on;
ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
ssl_session_cache shared:SSL:10m;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

---

## 🔍 Known Security Considerations

### Current Implementation

#### Rate Limiting
- **Status**: ⚠️ Not implemented
- **Risk**: DoS attacks, brute force
- **Mitigation**: Use django-ratelimit or Nginx rate limiting
```python
from django_ratelimit.decorators import ratelimit

@ratelimit(key='ip', rate='5/m')
def boat_search(request):
    pass
```

#### API Keys
- **Status**: ⚠️ External API keys in environment variables
- **Risk**: Exposure if .env file leaked
- **Mitigation**: Use secrets manager (AWS Secrets Manager, HashiCorp Vault)

#### File Uploads
- **Status**: ✅ Images stored on S3 with validation
- **Risk**: Malicious file uploads
- **Mitigation**: Validate file types, use antivirus scanning

#### Session Management
- **Status**: ✅ Django default session handling
- **Risk**: Session hijacking
- **Mitigation**: HTTPS-only cookies, short session timeout
```python
SESSION_COOKIE_AGE = 3600  # 1 hour
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
```

#### Password Storage
- **Status**: ✅ Django's PBKDF2 hashing
- **Risk**: Weak passwords
- **Mitigation**: Enforce strong password policy
```python
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
```

---

## 🛠️ Security Tools

### Recommended Tools

#### SAST (Static Analysis)
```bash
# Bandit - Python security linter
pip install bandit
bandit -r boats/ accounts/ boat_rental/

# Safety - Check dependencies for vulnerabilities
pip install safety
safety check --json
```

#### Dependency Scanning
```bash
# Check for outdated packages
pip list --outdated

# Update packages
pip install --upgrade <package>
```

#### Django Security Check
```bash
# Run Django's security check
python manage.py check --deploy
```

#### SSL Testing
```bash
# Test SSL configuration
https://www.ssllabs.com/ssltest/
```

---

## 📊 Security Checklist

### Development
- [ ] No hardcoded secrets in code
- [ ] Input validation on all user inputs
- [ ] SQL queries use ORM or parameterized
- [ ] XSS protection (auto-escaping enabled)
- [ ] CSRF tokens on all POST forms
- [ ] Authentication on sensitive endpoints
- [ ] Authorization checks (permissions)
- [ ] Error messages don't leak sensitive info

### Production
- [ ] DEBUG = False
- [ ] Strong SECRET_KEY
- [ ] HTTPS enforced
- [ ] Secure cookie flags set
- [ ] HSTS enabled
- [ ] Database credentials secured
- [ ] Firewall configured
- [ ] SSH key-based authentication
- [ ] Regular backups enabled
- [ ] Monitoring/alerting configured
- [ ] Logs reviewed regularly
- [ ] Dependencies updated monthly

---

## 📚 Resources

### Django Security
- [Django Security Documentation](https://docs.djangoproject.com/en/4.2/topics/security/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Django Security Checklist](https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/)

### External Tools
- [Snyk](https://snyk.io/) - Vulnerability scanning
- [Dependabot](https://github.com/dependabot) - Automated dependency updates
- [GitGuardian](https://www.gitguardian.com/) - Secret detection

---

## 🏆 Hall of Thanks

We appreciate responsible disclosure. Security researchers who report valid vulnerabilities will be:

- Listed here (with permission)
- Mentioned in release notes
- Eligible for bug bounty (if program exists)

**Current Contributors:**
- Your name here!

---

## 📞 Contact

- **Security Email**: security@yourcompany.com
- **PGP Key**: [Link to public key]
- **GitHub Security**: [Repository Security Tab]

---

**Last Updated**: 2026-02-01
**Next Review**: 2026-05-01

Thank you for helping keep BoatRental secure! 🔒✨
