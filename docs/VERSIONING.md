# Versioning Scheme

This project uses **Semantic Versioning** adapted for **development stage**.

## Version Format

```
MAJOR.MINOR.PATCH-dev
```

### During Development (`-dev`)

- **MAJOR** (X.0.0-dev): Major feature milestones or breaking changes
  - Example: 1.0.0-dev — first MVP release
  - Example: 2.0.0-dev — major architectural refactor
  
- **MINOR** (0.Y.0-dev): Feature additions and significant improvements
  - Example: 0.3.0-dev — pricing consistency fixes, country price configs
  - Example: 0.4.0-dev — new amenities refresh system
  
- **PATCH** (0.0.Z-dev): Bug fixes and minor corrections
  - Example: 0.3.1-dev — price cache initialization fix

## Current State

- **Current Version**: Read from `VERSION` file in project root
- **Stage**: Development (`-dev` suffix)
- **Increment Timeline**:
  - PATCH: After each bug fix / quick stabilization
  - MINOR: After feature completion (pricing, amenities, UI, API)
  - MAJOR: Reserved for production readiness (1.0.0) or post-MVP major refactor

## Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): short description

Body (optional):
- Line 1
- Line 2

Footer (optional):
BREAKING CHANGE: description
Fixes: #issue-number
```

### Commit Types

- **feat**: New feature (increments MINOR when released)
- **fix**: Bug fix (increments PATCH when released)
- **perf**: Performance improvement (increments PATCH)
- **refactor**: Code refactoring without feature change
- **docs**: Documentation updates
- **ci**: CI/CD configuration changes
- **test**: Test additions/modifications
- **chore**: Dependency updates, build config, etc.

### Scope Examples

- `boats` — boat search, detail, parsing
- `pricing` — price calculation, consensus, caching
- `offers` — offer creation, templates
- `accounts` — user profiles, authentication
- `docker` — Docker, compose, deployment
- `i18n` — localization, translations

## Example Commits

### Feature

```
feat(pricing): implement cache-first lookup for price consensus

- BoataroundAPI.get_price() now checks 6h Redis cache before consensus loop
- Eliminates price jitter symptom for users within cache window
- Reduces API calls for repeated date ranges
- Simplified error handling path when API unavailable

Fixes: KI-001
```

### Bug Fix

```
fix(pricing): add missing cache initialization on price consensus miss

- Previously, consensus loop could fail silently with empty results
- Now returns empty dict explicitly when all 5 requests fail
- Allows fallback handler to use DB price gracefully

Fixes: #42
```

### Performance

```
perf(boats): optimize slug lookup in boat detail view

- Changed from O(n) BoatDescription query to indexed FK lookup
- Detail page loads 40ms faster on average
```

## Release Notes Template

When incrementing version, update `CHANGELOG.md`:

```markdown
## [0.3.0-dev] — 2026-04-02

### Added
- Price cache-first lookup (6-hour TTL per date range)
- Dynamic country pricing via CountryPriceConfig model

### Fixed
- KI-001: Price jitter on detail page now mitigated via cache

### Changed
- `BoataroundAPI.get_price()` checks Redis before consensus loop

### Docs
- Updated TASK_STATE.md: P0 pricing consistency marked RESOLVED
- Updated KNOWN_ISSUES.md: KI-001 severity reduced to medium
```

## Tools & Integration

### Reading Current Version

```bash
cat VERSION
# Output: 0.3.0-dev
```

### Updating Version (manual for now)

```bash
echo "0.4.0-dev" > VERSION
git add VERSION
git commit -m "chore(release): bump to 0.4.0-dev"
```

### Future CI Integration

When moving to production, add automated version bumping:

```bash
# Pseudo-code for CI/CD
if commit_type == 'feat':
    increment MINOR
elif commit_type == 'fix':
    increment PATCH

echo "$MAJOR.$MINOR.$PATCH-dev" > VERSION
```

## Maintenance Notes

- **During development**: Keep `-dev` suffix always
- **Pre-release candidates**: Use `-rc.1`, `-rc.2` etc. before 1.0.0
- **Production ready**: Remove `-dev` suffix (e.g., 1.0.0)
- **Post-production**: Switch to `-prod` suffix or remove suffix entirely for stable releases

## References

- [Semantic Versioning 2.0.0](https://semver.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)
