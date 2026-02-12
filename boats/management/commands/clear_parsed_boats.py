"""
Management command для очистки и переинициализации парсинга лодок
"""
from django.core.management.base import BaseCommand
from boats.models import ParsedBoat

class Command(BaseCommand):
    help = 'Очищает все спарсенные данные лодок для переинициализации'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Подтвердить удаление (нужно указать для реального удаления)'
        )
    
    def handle(self, *args, **options):
        count = ParsedBoat.objects.count()
        
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  Это удалит {count} записей из БД!\n'
                    f'Используйте --confirm для подтверждения'
                )
            )
            return
        
        self.stdout.write(f'🗑️  Удаляю {count} записей...')
        ParsedBoat.objects.all().delete()
        
        new_count = ParsedBoat.objects.count()
        self.stdout.write(
            self.style.SUCCESS(f'✅ Удалено! Остало записей в БД: {new_count}')
        )
