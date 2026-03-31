#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boat_rental.settings')
django.setup()

from boats.models import ParsedBoat, BoatDescription, BoatTechnicalSpecs, BoatDetails, BoatGallery
from django.db.models import Count

total = ParsedBoat.objects.count()
print('=' * 70)
print('  COVERAGE REPORT: Field Fill Rate')
print('=' * 70)
print(f'\nTotal ParsedBoat records: {total}\n')

if total > 0:
    print('📌 ParsedBoat (basic API data):')
    for field in ['category', 'newboat', 'reviews_score']:
        if field == 'reviews_score':
            filled = ParsedBoat.objects.exclude(**{f'{field}__isnull': True}).count()
        elif field == 'newboat':
            filled = ParsedBoat.objects.filter(**{f'{field}': True}).count()
        else:
            filled = ParsedBoat.objects.exclude(**{f'{field}': ''}).count()
        pct = (filled * 100) // total if total > 0 else 0
        print(f'  {field:20} {filled:5d}/{total:5d}  ({pct:3d}%)')

    print('\n📌 BoatDescription (geographical + text):')
    desc_total = BoatDescription.objects.count()
    desc_pct = (desc_total * 100) // total if total > 0 else 0
    print(f'  Total records:     {desc_total:5d}/{total:5d}  ({desc_pct:3d}%)')
    if desc_total > 0:
        desc_filled = BoatDescription.objects.exclude(country='').exclude(region='').exclude(city='').count()
        desc_filled_pct = (desc_filled * 100) // desc_total if desc_total > 0 else 0
        print(f'  With geo (C+R+C):  {desc_filled:5d}/{desc_total:5d}  ({desc_filled_pct:3d}%)')

    print('\n📌 BoatTechnicalSpecs (dimensions + performance):')
    specs_total = BoatTechnicalSpecs.objects.count()
    specs_pct = (specs_total * 100) // total if total > 0 else 0
    print(f'  Total records:     {specs_total:5d}/{total:5d}  ({specs_pct:3d}%)')
    if specs_total > 0:
        for field in ['cabins', 'berths', 'length', 'beam', 'draft', 'toilets', 'engine_power']:
            filled = BoatTechnicalSpecs.objects.exclude(**{f'{field}__isnull': True}).count()
            pct = (filled * 100) // specs_total if specs_total > 0 else 0
            print(f'  {field:20} {filled:5d}/{specs_total:5d}  ({pct:3d}%)')

    print('\n📌 BoatDetails (amenities + services):')
    details_total = BoatDetails.objects.count()
    details_pct = (details_total * 100) // total if total > 0 else 0
    print(f'  Total records:     {details_total:5d}/{total:5d}  ({details_pct:3d}%)')
    if details_total > 0:
        print('  Amenities (HTML-parsed):')
        for field in ['cockpit', 'entertainment', 'equipment']:
            filled = BoatDetails.objects.exclude(**{f'{field}': []}).exclude(**{f'{field}__isnull': True}).count()
            pct = (filled * 100) // details_total if details_total > 0 else 0
            print(f'    {field:18} {filled:5d}/{details_total:5d}  ({pct:3d}%)')
        
        print('  Services (HTML-parsed):')
        for field in ['extras', 'additional_services', 'not_included']:
            filled = BoatDetails.objects.exclude(**{f'{field}': []}).exclude(**{f'{field}__isnull': True}).count()
            pct = (filled * 100) // details_total if details_total > 0 else 0
            print(f'    {field:18} {filled:5d}/{details_total:5d}  ({pct:3d}%)')

    print('\n📌 BoatGallery (photos):')
    photos_total = BoatGallery.objects.count()
    boats_with_photos = BoatGallery.objects.values('boat').distinct().count()
    photo_pct = (boats_with_photos * 100) // total if total > 0 else 0
    print(f'  Total photos:      {photos_total:5d}')
    print(f'  Boats w/ photos:   {boats_with_photos:5d}/{total:5d}  ({photo_pct:3d}%)')
    if boats_with_photos > 0:
        avg_photos = photos_total / boats_with_photos
        print(f'  Avg photos/boat:   {avg_photos:7.1f}')

    print('\n📌 BoatDescription (language coverage):')
    lang_breakdown = BoatDescription.objects.values('language').annotate(count=Count('id')).order_by('language')
    for item in lang_breakdown:
        lang = item['language']
        count = item['count']
        lang_pct = (count * 100) // total
        print(f'  {lang:10} {count:5d}/{total:5d}  ({lang_pct:3d}%)')

print('\n' + '=' * 70)
print('✅ Coverage analysis complete\n')
