"""Management command to clear incorrect cockpit/entertainment/equipment data from BoatDetails."""
from django.core.management.base import BaseCommand
from boats.models import BoatDetails


class Command(BaseCommand):
    help = 'Clears cockpit/entertainment/equipment from BoatDetails (data was from global API counts, not per-boat). Re-parse boats to repopulate correctly.'

    def handle(self, *args, **options):
        count = BoatDetails.objects.count()
        self.stdout.write(f'Clearing equipment data from {count} BoatDetails records...')
        BoatDetails.objects.all().update(cockpit=[], entertainment=[], equipment=[])
        self.stdout.write(self.style.SUCCESS(f'Done. {count} records cleared. Re-parse boats to populate correctly.'))
